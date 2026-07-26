/**
 * Real acoustic transient detection from the device microphone.
 *
 * WHAT THIS IS, HONESTLY
 * This is real signal processing on real microphone audio — not a scripted
 * trigger, and not a trained classifier either. It detects the *acoustic
 * signature* of breaking glass rather than recognising glass as a learned
 * class: a sudden broadband onset whose energy is concentrated well above
 * speech, sustained across more than one analysis frame.
 *
 * Those three conditions are what separates glass from the two things that
 * otherwise dominate a home mic. A door slam has the onset but its energy sits
 * low. Speech and music have high-frequency content but no sharp onset against
 * their own running baseline. Requiring both, then requiring agreement across
 * consecutive frames, is why a cough or a chair scrape does not fire this.
 *
 * The honest limit, and the UI says so: without a trained model this cannot
 * distinguish breaking glass from other sharp high-frequency transients — a
 * dropped plate would also fire it. It is a detector, not a classifier.
 *
 * PRIVACY
 * Audio is analysed in-frame and discarded. Nothing is recorded, buffered
 * beyond the analyser's own window, or sent anywhere — only the derived
 * decision leaves this module.
 */

/** Frequency above which we treat energy as "transient/shatter" rather than voice. */
const HF_CUTOFF_HZ = 3200;

/**
 * Sensitivity presets. `normal` is the tuning described above. `high` exists
 * for a real reason rather than as a slider for its own sake: a glass-break
 * sound replayed through laptop speakers is not the same signal as real glass.
 * Small drivers roll off the top octaves and compress the attack, so the same
 * event arrives with a lower high-frequency share and a softer onset. Testing
 * with recorded playback needs the looser thresholds to be a fair test.
 */
export type Sensitivity = 'normal' | 'high';

export const THRESHOLDS = {
  normal: { hfRatioMin: 0.45, onsetDb: 12, levelFloorDb: -55 },
  high: { hfRatioMin: 0.28, onsetDb: 8, levelFloorDb: -62 },
} as const;
/** Consecutive qualifying frames required before we call it. */
const FRAMES_TO_CONFIRM = 2;
/** Smoothing for the running baseline. Slow enough that the event can't raise it. */
const BASELINE_ALPHA = 0.02;

export interface AudioFrame {
  /** Broadband level in dBFS. */
  levelDb: number;
  /** Share of spectral energy above HF_CUTOFF_HZ, 0..1. */
  hfRatio: number;
  /** dB above the running room baseline. */
  onsetDb: number;
  /** True on the frame a confirmed transient fires. */
  detected: boolean;
  /** Which of the three conditions this frame met — so a near-miss is diagnosable. */
  passed: { loud: boolean; highFreq: boolean; onset: boolean };
}

export interface DetectorHandle {
  stop: () => void;
}

/**
 * The decision itself, separated from the audio plumbing so it can be tested
 * against known spectra rather than only against whatever the room happens to
 * be doing. Returns whether this single frame qualifies; confirmation across
 * consecutive frames is the caller's job.
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
export function spectrumStats(bins: Float32Array, cutoffBin: number): { levelDb: number; hfRatio: number } {
  let total = 0;
  let high = 0;
  for (let i = 0; i < bins.length; i++) {
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
 * Starts listening. Calls `onFrame` roughly every analysis frame (~monitor
 * refresh) so the UI can show a live meter, and sets `detected` on the frame
 * a transient is confirmed. Throws if mic permission is refused.
 */
export async function startGlassBreakDetector(
  onFrame: (frame: AudioFrame) => void,
  sensitivity: Sensitivity = 'normal',
): Promise<DetectorHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      // Every one of these would fight the detector: AGC flattens the onset,
      // noise suppression is tuned to preserve speech and removes exactly the
      // broadband transient we are looking for.
      autoGainControl: false,
      echoCancellation: false,
      noiseSuppression: false,
    },
  });

  const ctx = new AudioContext();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0; // no smoothing — smoothing hides onsets
  source.connect(analyser);

  const bins = new Float32Array(analyser.frequencyBinCount);
  const hzPerBin = ctx.sampleRate / analyser.fftSize;
  const cutoffBin = Math.floor(HF_CUTOFF_HZ / hzPerBin);

  let baselineDb = -60;
  let qualifying = 0;
  let raf = 0;
  let stopped = false;

  function tick() {
    if (stopped) return;
    analyser.getFloatFrequencyData(bins);

    const { levelDb, hfRatio } = spectrumStats(bins, cutoffBin);
    const onsetDb = levelDb - baselineDb;
    const { ok: isTransient, passed } = frameQualifies(levelDb, hfRatio, onsetDb, sensitivity);

    qualifying = isTransient ? qualifying + 1 : 0;
    const detected = qualifying === FRAMES_TO_CONFIRM;

    // Only let quiet frames move the baseline. If the event itself trained the
    // baseline upward, a sustained noise would silence the detector.
    if (!isTransient) {
      baselineDb = baselineDb * (1 - BASELINE_ALPHA) + levelDb * BASELINE_ALPHA;
    }

    onFrame({ levelDb, hfRatio, onsetDb, detected, passed });
    raf = requestAnimationFrame(tick);
  }
  raf = requestAnimationFrame(tick);

  return {
    stop() {
      stopped = true;
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
