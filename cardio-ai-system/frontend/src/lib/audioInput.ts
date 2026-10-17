/**
 * Microphone input for the consultation capture.
 *
 * Everything here that can be pure is pure, because jsdom has no
 * `AudioContext`: the level arithmetic is unit-tested, and the browser-only
 * calls sit in two thin functions at the bottom.
 *
 * Why the constraints matter: `getUserMedia({ audio: true })` asks for the
 * raw device feed. A clinic room is a fan, a keyboard and a second person
 * talking; without echo cancellation the recogniser hears the app's own
 * prompts, and without automatic gain control a clinician speaking away from
 * the laptop arrives so quiet that the recogniser drops the line entirely.
 * Asking for the processed feed is what makes the transcript hold up away
 * from a quiet desk.
 */

export type MicState = "silent" | "quiet" | "good" | "hot";

export type MicFrame = {
  /** Smoothed 0–1 level for the meter (already perceptually scaled). */
  level: number;
  /** Instantaneous 0–1 peak of this frame, before smoothing. */
  peak: number;
  /** Frame loudness in dBFS (0 is full scale); clamped, never -Infinity. */
  dbfs: number;
  /** What the frame means for the clinician watching the meter. */
  state: MicState;
};

/** Processed mono feed — the three flags are the reason this file exists. */
export const MIC_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  channelCount: 1
};

/** Below this the frame is treated as room noise, not speech. */
export const NOISE_FLOOR_DBFS = -55;
/** At or above this the clinician is clearly speaking. */
export const SPEECH_DBFS = -38;
/** Within 6 dB of full scale the input is too hot and will clip. */
export const HOT_DBFS = -6;
/** dBFS is meaningless below this; clamp instead of returning -Infinity. */
export const MIN_DBFS = -100;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * RMS and peak of a time-domain `AnalyserNode` buffer.
 *
 * Samples are unsigned bytes around 128, so silence reads 128 and the
 * distance from the midpoint is the signal. Peak is what catches a plosive
 * that an average would hide; RMS is what tracks sustained speech.
 */
export function sampleFrame(buffer: ArrayLike<number>): { rms: number; peak: number } {
  if (buffer.length === 0) return { rms: 0, peak: 0 };
  let sumSquares = 0;
  let peak = 0;
  for (let i = 0; i < buffer.length; i++) {
    const centred = (buffer[i] - 128) / 128;
    sumSquares += centred * centred;
    const magnitude = Math.abs(centred);
    if (magnitude > peak) peak = magnitude;
  }
  return { rms: Math.sqrt(sumSquares / buffer.length), peak: clamp(peak, 0, 1) };
}

/** Linear amplitude → dBFS, clamped so an all-silent frame is not -Infinity. */
export function dbfsOf(amplitude: number): number {
  if (!(amplitude > 0)) return MIN_DBFS;
  return Math.max(MIN_DBFS, 20 * Math.log10(amplitude));
}

/**
 * Map dBFS onto the meter's 0–1 range, with the noise floor at 0 and
 * `HOT_DBFS` at 1. The curve is tweaked with a square root so quiet speech
 * moves the bar instead of leaving it pinned to the first pixel — a meter
 * that only reacts to shouting tells the clinician nothing.
 */
export function levelFromDbfs(dbfs: number): number {
  const span = HOT_DBFS - NOISE_FLOOR_DBFS;
  const normalized = clamp((dbfs - NOISE_FLOOR_DBFS) / span, 0, 1);
  return Math.sqrt(normalized);
}

/** Classify a frame so the UI can name the problem instead of showing a bar. */
export function micStateOf(dbfs: number): MicState {
  if (dbfs <= NOISE_FLOOR_DBFS) return "silent";
  if (dbfs < SPEECH_DBFS) return "quiet";
  if (dbfs >= HOT_DBFS) return "hot";
  return "good";
}

/** One analyser frame → everything the capture UI needs. */
export function readMicFrame(buffer: ArrayLike<number>): MicFrame {
  const { rms, peak } = sampleFrame(buffer);
  const dbfs = dbfsOf(rms);
  return { level: levelFromDbfs(dbfs), peak, dbfs, state: micStateOf(dbfs) };
}

/** How long without a speech-level frame before the meter offers help. */
export const QUIET_HINT_MS = 8000;

/**
 * What the meter should say, in the clinician's words.
 *
 * A quiet room is the normal state between sentences, so a low frame on its
 * own must not raise a warning — otherwise the hint is on screen for the whole
 * consultation and means nothing. The quiet/silent hint waits until no
 * speech-level frame has arrived for `QUIET_HINT_MS`, which is the point where
 * "is this thing hearing me?" is a fair question; clipping is reported at
 * once, because it is corrupting the line being captured right now.
 */
export function meterHint(frame: MicFrame, silentForMs = 0): string {
  if (frame.state === "hot") return "Input is clipping — move back from the microphone.";
  if (frame.state === "good") return "";
  if (silentForMs >= QUIET_HINT_MS) {
    return "No speech reaching the microphone yet — move closer, or check the input device.";
  }
  return "";
}

/**
 * Ask for the processed microphone feed.
 *
 * A machine with one stubborn device can refuse the constraint set with
 * `OverconstrainedError` (a virtual cable that advertises no processing, for
 * example), so the request is retried unconstrained rather than failing the
 * consultation over a device capability the clinician cannot change.
 */
export async function openMicStream(
  constraints: MediaTrackConstraints = MIC_CONSTRAINTS
): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new DOMException("This browser cannot open the microphone.", "NotSupportedError");
  }
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: constraints });
  } catch (error) {
    const name = (error as { name?: string } | null)?.name;
    if (name === "OverconstrainedError" || name === "NotSupportedError") {
      return navigator.mediaDevices.getUserMedia({ audio: true });
    }
    throw error;
  }
}

/**
 * Turn a `getUserMedia` rejection into the sentence the clinician needs. The
 * three failures have three different fixes, and "microphone error" serves
 * none of them.
 */
export function describeMicError(error: unknown): { message: string; denied: boolean } {
  const name = (error as { name?: string } | null)?.name ?? "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return {
        denied: true,
        message:
          "Microphone blocked. Click the lock (or site settings) icon in the address bar, allow Microphone, then start listening again."
      };
    case "NotFoundError":
    case "OverconstrainedError":
      return {
        denied: false,
        message: "No microphone found. Connect one and start listening again."
      };
    case "NotReadableError":
    case "AbortError":
      return {
        denied: false,
        message: "The microphone is busy in another app. Close it and start listening again."
      };
    default:
      return {
        denied: false,
        message: "Could not open the microphone. Check the selected input device and try again."
      };
  }
}
