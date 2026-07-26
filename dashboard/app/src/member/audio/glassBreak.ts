/**
 * Home Guard acoustic detection — two stages, on real microphone audio.
 *
 * STAGE 1 (here): a transient gate. Sudden, loud, mostly-high-frequency,
 * sustained over consecutive frames. Real DSP over the live mic.
 *
 * STAGE 2 (audio/classify.ts -> server YAMNet): what the sound actually was.
 *
 * WHY THERE ARE TWO STAGES, AND WHY STAGE 1 IS NO LONGER THE ALARM
 * This file used to fire the alarm on its own, and the failure that produced was
 * speech. Fricatives — s, sh, t, f — are sharp broadband bursts with most of
 * their energy above 3 kHz, so they satisfy every condition a frequency
 * heuristic can test. That is not a tuning problem: on the three axes available
 * here, a spoken "sss" and breaking glass genuinely look alike. Separating them
 * needs a model that learned what glass sounds like.
 *
 * So the gate's job changed. It no longer decides that glass broke; it decides
 * that something impact-shaped happened and it is worth spending an inference.
 * That lets it be *looser* than before, because a false gate now costs one
 * classifier call rather than a false alarm on someone's home. The classifier
 * has the veto.
 *
 * WHY A WORKLET TAP AND NOT THE ANALYSER FOR THE CAPTURED WINDOW
 * The gate reads the AnalyserNode's spectrum, which is fine for a per-frame
 * decision. But the classifier needs a real, contiguous second of audio, and
 * repeated analyser reads cannot give you that: they return the latest fftSize
 * samples each time, so at 60 fps on a 48 kHz context consecutive reads overlap
 * by ~60% and concatenating them would produce audio that stutters and repeats.
 * An AudioWorklet delivers each block exactly once, in order, which is what a
 * ring buffer needs to be truthful.
 *
 * PRIVACY
 * The ring buffer is ~1.5 s and lives in memory only. On a gate, one window is
 * sent for classification and dropped; nothing is recorded, written to disk, or
 * attached to an incident. Only the label and score persist.
 */
import { TARGET_SAMPLES } from './resample';

/** Frequency above which we treat energy as impact-like rather than voice. */
const HF_CUTOFF_HZ = 3200;

/**
 * Gate sensitivity. These are looser than they were when this file fired the
 * alarm directly, and deliberately so — see the two-stage note above. `high`
 * exists for testing with played-back recordings: small laptop speakers roll
 * off the top octaves and compress the attack, so a genuine clip arrives with a
 * lower high-frequency share and softer onset than real glass in the room.
 */
export type Sensitivity = 'normal' | 'high';

export const THRESHOLDS = {
  normal: { hfRatioMin: 0.35, onsetDb: 9, levelFloorDb: -58 },
  high: { hfRatioMin: 0.22, onsetDb: 6, levelFloorDb: -64 },
} as const;

/** Consecutive qualifying frames before the gate opens. */
const FRAMES_TO_CONFIRM = 2;
/** Smoothing for the running baseline. Slow enough that the event can't raise it. */
const BASELINE_ALPHA = 0.02;

/**
 * How long to keep collecting after the gate opens before capturing the window.
 * Glass is defined as much by its decay — the scatter of fragments — as by its
 * onset, and the classifier needs to hear both. Capturing at the instant of the
 * onset would hand YAMNet a window that is almost entirely pre-event room noise.
 */
const POST_ROLL_MS = 320;

/** Ring buffer length. One YAMNet window plus the post-roll, with headroom. */
const RING_SECONDS = 1.6;

/**
 * Minimum spacing between classifier calls. Without it, one long transient (or a
 * noisy room at `high`) would post continuously.
 */
const CLASSIFY_COOLDOWN_MS = 1500;

export interface AudioFrame {
  /** Broadband level in dBFS. */
  levelDb: number;
  /** Share of spectral energy above HF_CUTOFF_HZ, 0..1. */
  hfRatio: number;
  /** dB above the running room baseline. */
  onsetDb: number;
  /** True on the frame the gate opens — a candidate, NOT a confirmed detection. */
  gated: boolean;
  /** Which of the three gate conditions this frame met, so a near-miss is diagnosable. */
  passed: { loud: boolean; highFreq: boolean; onset: boolean };
}

export interface DetectorHandle {
  stop: () => void;
}

export interface DetectorCallbacks {
  /** Every analysis frame — drives the live meter and the condition readout. */
  onFrame: (frame: AudioFrame) => void;
  /**
   * A captured window, POST_ROLL_MS after the gate opened. The caller sends this
   * to the classifier; only its verdict may raise an alarm.
   */
  onCandidate: (samples: Float32Array, sampleRate: number) => void;
}

/**
 * The gate decision, separated from the audio plumbing so it can be tested
 * against known spectra rather than against whatever the room is doing.
 * Confirmation across consecutive frames is the caller's job.
 */
export function frameQualifies(
  levelDb: number,
  hfRatio: number,
  onsetDb: number,
  sensitivity: Sensitivity = 'normal',
): { ok: boolean; passed: { loud: boolean; highFreq: boolean; onset: boolean } } {
  const t = THRESHOLDS[sensitivity];
  const passed = {
    loud: levelDb > t.levelFloorDb,
    highFreq: hfRatio > t.hfRatioMin,
    onset: onsetDb > t.onsetDb,
  };
  return { ok: passed.loud && passed.highFreq && passed.onset, passed };
}

/** Splits an FFT magnitude-dB array into broadband level and high-freq share. */
export function spectrumStats(
  bins: Float32Array,
  cutoffBin: number,
): { levelDb: number; hfRatio: number } {
  let total = 0;
  let high = 0;
  for (let i = 0; i < bins.length; i++) {
    // dB -> linear power before summing. Averaging dB values directly is a
    // different quantity and would skew the ratio.
    const power = Math.pow(10, bins[i] / 10);
    total += power;
    if (i >= cutoffBin) high += power;
  }
  return {
    levelDb: 10 * Math.log10(total + 1e-12),
    hfRatio: total > 0 ? high / total : 0,
  };
}

/**
 * A fixed-size ring of the most recent audio. Exported for testing because the
 * read order is easy to get wrong and a silently mis-ordered window would make
 * the classifier look broken rather than the buffer.
 */
export class RingBuffer {
  private buf: Float32Array;
  private write = 0;
  private filled = 0;

  constructor(length: number) {
    this.buf = new Float32Array(length);
  }

  push(block: Float32Array): void {
    for (let i = 0; i < block.length; i++) {
      this.buf[this.write] = block[i];
      this.write = (this.write + 1) % this.buf.length;
      if (this.filled < this.buf.length) this.filled++;
    }
  }

  /** The most recent `n` samples, oldest first. Short-buffer reads are zero-padded at the front. */
  latest(n: number): Float32Array {
    const out = new Float32Array(n);
    const available = Math.min(n, this.filled);
    for (let i = 0; i < available; i++) {
      // Walk backwards from the write head, filling the output back to front.
      const idx = (this.write - 1 - i + this.buf.length * 2) % this.buf.length;
      out[n - 1 - i] = this.buf[idx];
    }
    return out;
  }
}

/**
 * An AudioWorklet that forwards raw blocks to the main thread, batched to reduce
 * postMessage traffic (128-sample render quanta would be ~375 messages/second).
 * Inlined as a Blob URL so it needs no separate asset or Vite worklet config.
 */
const TAP_WORKLET = `
class PcmTap extends AudioWorkletProcessor {
  constructor() { super(); this.acc = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.acc[this.n++] = ch[i];
      if (this.n === this.acc.length) {
        this.port.postMessage(this.acc.slice(0));
        this.n = 0;
      }
    }
    return true;
  }
}
registerProcessor('pcm-tap', PcmTap);
`;

/**
 * Starts listening. Calls `onFrame` each analysis frame for the live readout,
 * and `onCandidate` with a captured window whenever the gate opens.
 * Throws if microphone permission is refused.
 */
export async function startGlassBreakDetector(
  callbacks: DetectorCallbacks,
  sensitivity: Sensitivity = 'normal',
): Promise<DetectorHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      // Every one of these would fight the detector: AGC flattens the onset, and
      // noise suppression is tuned to preserve speech, which means it removes
      // exactly the broadband transient being looked for.
      autoGainControl: false,
      echoCancellation: false,
      noiseSuppression: false,
    },
  });

  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);

  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0; // smoothing would hide the onset
  source.connect(analyser);

  // Raw tap for the classifier window, in parallel with the analyser.
  const ring = new RingBuffer(Math.ceil(ctx.sampleRate * RING_SECONDS));
  const workletUrl = URL.createObjectURL(new Blob([TAP_WORKLET], { type: 'text/javascript' }));
  let tap: AudioWorkletNode | null = null;
  try {
    await ctx.audioWorklet.addModule(workletUrl);
    tap = new AudioWorkletNode(ctx, 'pcm-tap');
    tap.port.onmessage = (e: MessageEvent<Float32Array>) => ring.push(e.data);
    source.connect(tap);
  } finally {
    URL.revokeObjectURL(workletUrl);
  }

  const bins = new Float32Array(analyser.frequencyBinCount);
  const hzPerBin = ctx.sampleRate / analyser.fftSize;
  const cutoffBin = Math.floor(HF_CUTOFF_HZ / hzPerBin);
  // The captured window is one YAMNet window at 16 kHz, expressed in this
  // context's own rate; resampling happens at the point of sending.
  const captureSamples = Math.ceil((TARGET_SAMPLES / 16_000) * ctx.sampleRate);

  let baselineDb = -60;
  let qualifying = 0;
  let raf = 0;
  let stopped = false;
  let lastClassifyAt = 0;
  const timers: number[] = [];

  function tick() {
    if (stopped) return;
    analyser.getFloatFrequencyData(bins);

    const { levelDb, hfRatio } = spectrumStats(bins, cutoffBin);
    const onsetDb = levelDb - baselineDb;
    const { ok: isTransient, passed } = frameQualifies(levelDb, hfRatio, onsetDb, sensitivity);

    qualifying = isTransient ? qualifying + 1 : 0;
    const now = performance.now();
    const gated =
      qualifying === FRAMES_TO_CONFIRM && now - lastClassifyAt > CLASSIFY_COOLDOWN_MS;

    if (gated) {
      lastClassifyAt = now;
      // Wait for the decay before capturing — see POST_ROLL_MS.
      timers.push(
        window.setTimeout(() => {
          if (!stopped) callbacks.onCandidate(ring.latest(captureSamples), ctx.sampleRate);
        }, POST_ROLL_MS),
      );
    }

    // Only let non-qualifying frames move the baseline. If the event trained the
    // baseline upward, a sustained noise would silence the gate.
    if (!isTransient) {
      baselineDb = baselineDb * (1 - BASELINE_ALPHA) + levelDb * BASELINE_ALPHA;
    }

    callbacks.onFrame({ levelDb, hfRatio, onsetDb, gated, passed });
    raf = requestAnimationFrame(tick);
  }
  raf = requestAnimationFrame(tick);

  return {
    stop() {
      stopped = true;
      cancelAnimationFrame(raf);
      timers.forEach(clearTimeout);
      tap?.port.close();
      tap?.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
