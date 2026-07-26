import { describe, expect, it } from 'vitest';
import { RingBuffer, frameQualifies, spectrumStats } from './glassBreak';
import { fitToWindow, resampleTo16k, toPcm16Base64, TARGET_SAMPLES } from './resample';

/** Builds an FFT magnitude-dB array with given dB in the low and high bands. */
function spectrum(lowDb: number, highDb: number, cutoffBin: number, bins = 64): Float32Array {
  const out = new Float32Array(bins);
  for (let i = 0; i < bins; i++) out[i] = i < cutoffBin ? lowDb : highDb;
  return out;
}

const CUTOFF = 32;

describe('spectrumStats', () => {
  it('reports a high high-freq share when energy sits above the cutoff', () => {
    const { hfRatio } = spectrumStats(spectrum(-80, -20, CUTOFF), CUTOFF);
    expect(hfRatio).toBeGreaterThan(0.9);
  });

  it('reports a low high-freq share for speech-like low-band energy', () => {
    const { hfRatio } = spectrumStats(spectrum(-20, -80, CUTOFF), CUTOFF);
    expect(hfRatio).toBeLessThan(0.1);
  });

  it('rises in level as band energy rises', () => {
    const quiet = spectrumStats(spectrum(-80, -80, CUTOFF), CUTOFF).levelDb;
    const loud = spectrumStats(spectrum(-20, -20, CUTOFF), CUTOFF).levelDb;
    expect(loud).toBeGreaterThan(quiet);
  });
});

/**
 * The gate is now a *gate*, not the alarm — it decides when to spend a
 * classifier inference. So these tests pin that it responds to impact shape and
 * that a near-miss reports which condition failed. They deliberately do NOT
 * assert that speech is rejected: the gate cannot do that (a spoken "sss" is
 * genuinely loud, high-frequency and sudden), and pretending otherwise here is
 * how the false alarms happened. Speech rejection is the classifier's job and is
 * tested in server/tests/test_audio_yamnet.py.
 */
describe('frameQualifies (stage 1 gate)', () => {
  it('opens on a loud high-frequency onset', () => {
    expect(frameQualifies(-25, 0.7, 20).ok).toBe(true);
  });

  it('stays shut for a door slam: onset present, but energy is low-frequency', () => {
    const { ok, passed } = frameQualifies(-25, 0.1, 20);
    expect(ok).toBe(false);
    expect(passed).toEqual({ loud: true, highFreq: false, onset: true });
  });

  it('stays shut for steady sound: high-frequency content but no onset', () => {
    const { ok, passed } = frameQualifies(-25, 0.6, 3);
    expect(ok).toBe(false);
    expect(passed).toEqual({ loud: true, highFreq: true, onset: false });
  });

  it('stays shut below the quiet-room floor even if the shape matches', () => {
    const { ok, passed } = frameQualifies(-70, 0.7, 20);
    expect(ok).toBe(false);
    expect(passed.loud).toBe(false);
  });

  it('high sensitivity opens for a speaker-played transient that normal rejects', () => {
    // Rolled-off top end and a softened attack — what playback through laptop
    // speakers does to a real recording.
    const played = [-40, 0.25, 7] as const;
    expect(frameQualifies(...played, 'normal').ok).toBe(false);
    expect(frameQualifies(...played, 'high').ok).toBe(true);
  });

  it('high sensitivity still needs an onset — it loosens, it does not disable', () => {
    expect(frameQualifies(-25, 0.6, 1, 'high').ok).toBe(false);
  });
});

describe('RingBuffer', () => {
  it('returns the most recent samples in order', () => {
    const r = new RingBuffer(8);
    r.push(new Float32Array([1, 2, 3, 4, 5]));
    expect(Array.from(r.latest(3))).toEqual([3, 4, 5]);
  });

  it('keeps order after wrapping past the end', () => {
    const r = new RingBuffer(4);
    r.push(new Float32Array([1, 2, 3, 4, 5, 6]));
    // 1 and 2 have been overwritten; the window must not be rotated.
    expect(Array.from(r.latest(4))).toEqual([3, 4, 5, 6]);
  });

  it('zero-pads at the front when asked for more than it holds', () => {
    const r = new RingBuffer(8);
    r.push(new Float32Array([7, 8]));
    expect(Array.from(r.latest(4))).toEqual([0, 0, 7, 8]);
  });

  it('handles blocks larger than the buffer without losing the newest audio', () => {
    const r = new RingBuffer(3);
    r.push(new Float32Array([1, 2, 3, 4, 5]));
    expect(Array.from(r.latest(3))).toEqual([3, 4, 5]);
  });
});

describe('resampleTo16k', () => {
  it('is a no-op at the target rate', () => {
    const input = new Float32Array([0.1, 0.2, 0.3]);
    expect(resampleTo16k(input, 16_000)).toBe(input);
  });

  it('reduces length by the rate ratio', () => {
    const input = new Float32Array(48_000);
    expect(resampleTo16k(input, 48_000).length).toBe(16_000);
  });

  it('handles the non-integer 44.1kHz ratio', () => {
    const out = resampleTo16k(new Float32Array(44_100), 44_100);
    expect(out.length).toBe(16_000);
  });

  it('preserves a constant signal rather than attenuating it', () => {
    const input = new Float32Array(4800).fill(0.5);
    const out = resampleTo16k(input, 48_000);
    expect(out[0]).toBeCloseTo(0.5, 5);
    expect(out[out.length - 1]).toBeCloseTo(0.5, 5);
  });

  it('averages rather than decimating, so alternating samples do not alias to full scale', () => {
    // A signal at Nyquist. Decimation by 3 would pass it through at full
    // amplitude as a false low-frequency tone; averaging must suppress it.
    const input = new Float32Array(300);
    for (let i = 0; i < input.length; i++) input[i] = i % 2 === 0 ? 1 : -1;
    const out = resampleTo16k(input, 48_000);
    expect(Math.max(...Array.from(out).map(Math.abs))).toBeLessThan(0.5);
  });
});

describe('fitToWindow', () => {
  it('pads a short window to YAMNet input length', () => {
    expect(fitToWindow(new Float32Array(100)).length).toBe(TARGET_SAMPLES);
  });

  it('keeps the most recent audio when trimming, not the oldest', () => {
    const input = new Float32Array(TARGET_SAMPLES + 10);
    input[input.length - 1] = 0.9;
    const out = fitToWindow(input);
    expect(out.length).toBe(TARGET_SAMPLES);
    expect(out[out.length - 1]).toBeCloseTo(0.9, 5);
  });
});

describe('toPcm16Base64', () => {
  it('round-trips samples through int16 within quantisation error', () => {
    const input = new Float32Array([0, 0.5, -0.5, 0.25]);
    const bytes = Uint8Array.from(atob(toPcm16Base64(input)), (c) => c.charCodeAt(0));
    const pcm = new Int16Array(bytes.buffer);
    expect(pcm.length).toBe(4);
    expect(pcm[1] / 0x7fff).toBeCloseTo(0.5, 3);
    expect(pcm[2] / 0x8000).toBeCloseTo(-0.5, 3);
  });

  it('clamps out-of-range samples instead of letting them wrap polarity', () => {
    const bytes = Uint8Array.from(atob(toPcm16Base64(new Float32Array([1.8, -1.8]))), (c) =>
      c.charCodeAt(0),
    );
    const pcm = new Int16Array(bytes.buffer);
    expect(pcm[0]).toBe(0x7fff);
    expect(pcm[1]).toBe(-0x8000);
  });

  it('encodes a full-length window without overflowing the call stack', () => {
    expect(toPcm16Base64(new Float32Array(TARGET_SAMPLES)).length).toBeGreaterThan(40_000);
  });
});
