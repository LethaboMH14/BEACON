/**
 * Sample-rate conversion and PCM packing for the YAMNet classifier hop.
 *
 * WHY THIS IS NEEDED
 * An AudioContext runs at the device rate — 48 kHz on most laptops, 44.1 kHz on
 * some. YAMNet's input tensor is a fixed 15,600 samples of 16 kHz mono. So the
 * captured window has to be rate-converted client-side; the server rejects
 * anything that is not 16 kHz rather than guessing what a client meant.
 *
 * WHY SPAN AVERAGING RATHER THAN PICKING NEAREST SAMPLES
 * Downsampling by simply taking every Nth sample folds everything above 8 kHz
 * back down into the band as alias — and the sound being classified is defined
 * by its high-frequency content, so that is the worst possible place to corrupt.
 * Averaging each output sample over the whole source span it covers is a crude
 * box lowpass, which is not as good as a designed FIR but does suppress the
 * out-of-band energy instead of folding it. It also handles non-integer ratios
 * like 44100/16000 without special-casing them.
 */

/** YAMNet's rate. The server enforces this. */
export const TARGET_RATE = 16_000;

/** YAMNet's fixed input length — 0.975 s at 16 kHz. */
export const TARGET_SAMPLES = 15_600;

/**
 * Converts mono float samples to `TARGET_RATE`, averaging over each source span.
 * Upsampling is not the use case here (device rates are all above 16 kHz), but
 * a ratio below 1 still degrades gracefully to nearest-sample.
 */
export function resampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === TARGET_RATE) return input;

  const ratio = inputRate / TARGET_RATE;
  const outLength = Math.floor(input.length / ratio);
  const out = new Float32Array(outLength);

  for (let i = 0; i < outLength; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.max(Math.floor((i + 1) * ratio), start + 1), input.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / (end - start);
  }
  return out;
}

/**
 * Packs float samples in [-1, 1] as 16-bit PCM, base64-encoded.
 *
 * 16-bit rather than float32 because the same window is ~31 KB instead of
 * ~200 KB of JSON, and 16 bits is already finer than the microphone resolves.
 * Clamping matters: a sample slightly outside the range would otherwise wrap to
 * the opposite polarity and inject a click exactly where a transient is being
 * measured.
 */
export function toPcm16Base64(samples: Float32Array): string {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }

  const bytes = new Uint8Array(pcm.buffer);
  // Chunked because String.fromCharCode(...spread) overflows the call stack on
  // an array this size.
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

/** Trims or zero-pads to YAMNet's exact input length, keeping the most recent audio. */
export function fitToWindow(samples: Float32Array): Float32Array {
  if (samples.length === TARGET_SAMPLES) return samples;
  const out = new Float32Array(TARGET_SAMPLES);
  if (samples.length > TARGET_SAMPLES) {
    out.set(samples.subarray(samples.length - TARGET_SAMPLES));
  } else {
    out.set(samples);
  }
  return out;
}
