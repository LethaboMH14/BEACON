/**
 * Client for POST /v1/audio/classify — the trained-classifier half of Home Guard.
 *
 * The browser's transient detector decides *when* to ask; this asks *what it
 * was*. Keeping the two apart is what lets the gate stay loose: a false gate
 * now costs one inference, not a false alarm.
 */
import { apiUrl } from '../../api/base';
import { fitToWindow, resampleTo16k, TARGET_RATE, toPcm16Base64 } from './resample';

export interface ClassifyResult {
  /** 'glass_break' or 'other'. */
  verdict: string;
  /** Best-scoring glass-family class and its score. */
  glass_label: string;
  glass_score: number;
  /** The everyday sound that scored highest — this is the "why not" answer. */
  competing_label: string;
  competing_score: number;
  clears_floor: boolean;
  beats_competing: boolean;
  top: { label: string; score: number }[];
}

export class ClassifierOffline extends Error {}

/**
 * Rate-converts, packs and posts one captured window.
 *
 * Throws `ClassifierOffline` when the server or its model is unavailable, which
 * the caller must treat as "cannot confirm" — never as confirmation. Failing
 * open here would reintroduce exactly the false alarms this replaced.
 */
export async function classifyWindow(
  samples: Float32Array,
  sampleRate: number,
): Promise<ClassifyResult> {
  const window = fitToWindow(resampleTo16k(samples, sampleRate));

  let res: Response;
  try {
    res = await fetch(apiUrl('/v1/audio/classify'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pcm16: toPcm16Base64(window), sample_rate: TARGET_RATE }),
    });
  } catch (e) {
    throw new ClassifierOffline(e instanceof Error ? e.message : 'network error');
  }

  if (res.status === 503) throw new ClassifierOffline('classifier not available on the server');
  if (!res.ok) throw new ClassifierOffline(`classifier returned ${res.status}`);
  return (await res.json()) as ClassifyResult;
}
