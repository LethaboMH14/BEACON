import { describe, expect, it } from 'vitest';
import { frameQualifies, spectrumStats } from './glassBreak';

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

describe('frameQualifies', () => {
  it('fires on a loud high-frequency onset — the glass-break shape', () => {
    expect(frameQualifies(-25, 0.7, 20)).toBe(true);
  });

  it('rejects a door slam: onset present, but energy is low-frequency', () => {
    expect(frameQualifies(-25, 0.1, 20)).toBe(false);
  });

  it('rejects steady speech or music: high-frequency content but no onset', () => {
    expect(frameQualifies(-25, 0.6, 3)).toBe(false);
  });

  it('rejects anything below the quiet-room floor even if the shape matches', () => {
    expect(frameQualifies(-70, 0.7, 20)).toBe(false);
  });
});
