export type ProgressSample = { t: number; p: number }; // elapsed seconds, progress 0..1
export type Eta = { seconds: number; finishAt: number }; // finishAt: epoch ms

const MIN_ELAPSED = 10; // short jobs finish before an estimate is useful
const MIN_PROGRESS = 0.03;
const WINDOW = 60;

/**
 * Seconds remaining, or null while there is not enough signal.
 * Blends the recent rate (last 60 s, follows stage changes) with the overall average (stable).
 */
export function estimateRemaining(samples: ProgressSample[]): number | null {
  const last = samples[samples.length - 1];
  if (!last || last.t < MIN_ELAPSED || last.p < MIN_PROGRESS || last.p >= 1) return null;
  const overall = last.p / last.t;
  const start = samples.find((s) => s.t >= last.t - WINDOW);
  let rate = overall;
  if (start && last.t - start.t >= 5) {
    const recent = (last.p - start.p) / (last.t - start.t);
    rate = recent > 0 ? 0.5 * recent + 0.5 * overall : overall;
  }
  return rate > 0 ? (1 - last.p) / rate : null;
}

/** Rounded so the number does not jitter: to the minute above 2 min, else to 10 s. */
export function roundEta(seconds: number): number {
  if (seconds > 120) return Math.ceil(seconds / 60) * 60;
  return Math.max(10, Math.ceil(seconds / 10) * 10);
}
