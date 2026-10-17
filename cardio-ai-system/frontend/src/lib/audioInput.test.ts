import { describe, expect, it } from "vitest";
import {
  HOT_DBFS,
  MIC_CONSTRAINTS,
  MIN_DBFS,
  NOISE_FLOOR_DBFS,
  QUIET_HINT_MS,
  SPEECH_DBFS,
  dbfsOf,
  describeMicError,
  levelFromDbfs,
  meterHint,
  micStateOf,
  readMicFrame,
  sampleFrame
} from "@/lib/audioInput";

/** A time-domain frame of `length` samples at a constant signed amplitude. */
function frame(amplitude: number, length = 32): number[] {
  return Array.from({ length }, () => 128 + Math.round(amplitude * 128));
}

describe("sampleFrame", () => {
  it("reads an untouched buffer as silence", () => {
    expect(sampleFrame(frame(0))).toEqual({ rms: 0, peak: 0 });
  });

  it("returns the RMS for a steady tone and the peak for a transient", () => {
    const steady = sampleFrame(frame(0.5));
    expect(steady.rms).toBeCloseTo(0.5, 5);
    expect(steady.peak).toBeCloseTo(0.5, 2);

    // One loud sample in an otherwise quiet frame: RMS stays low, peak does not.
    const spike = [...frame(0.01), ...frame(0.9, 2), ...frame(0.01)];
    const { rms, peak } = sampleFrame(spike);
    expect(rms).toBeLessThan(0.3);
    expect(peak).toBeGreaterThan(0.8);
  });

  it("tolerates an empty buffer rather than dividing by zero", () => {
    expect(sampleFrame([])).toEqual({ rms: 0, peak: 0 });
  });
});

describe("dbfsOf", () => {
  it("clamps silence to the floor instead of returning -Infinity", () => {
    expect(dbfsOf(0)).toBe(MIN_DBFS);
    expect(Number.isFinite(dbfsOf(0))).toBe(true);
  });

  it("is 0 dBFS at full scale and -20 dB at a tenth of it", () => {
    expect(dbfsOf(1)).toBeCloseTo(0, 5);
    expect(dbfsOf(0.1)).toBeCloseTo(-20, 5);
  });
});

describe("levelFromDbfs", () => {
  it("maps the noise floor to 0 and full scale to 1", () => {
    expect(levelFromDbfs(NOISE_FLOOR_DBFS)).toBe(0);
    expect(levelFromDbfs(0)).toBe(1);
    expect(levelFromDbfs(0)).toBeGreaterThan(levelFromDbfs(-20));
  });

  it("never leaves the 0–1 range, however loud or quiet the frame", () => {
    expect(levelFromDbfs(-400)).toBe(0);
    expect(levelFromDbfs(40)).toBe(1);
  });

  it("gives quiet speech a visible bar instead of pinning it to zero", () => {
    // -45 dBFS is a soft-spoken room; a linear meter would sit at ~18%.
    expect(levelFromDbfs(-45)).toBeGreaterThan(0.25);
  });
});

describe("micStateOf", () => {
  it("separates room noise, soft speech, speech and clipping", () => {
    expect(micStateOf(NOISE_FLOOR_DBFS - 5)).toBe("silent");
    expect(micStateOf(-45)).toBe("quiet");
    expect(micStateOf(-25)).toBe("good");
    expect(micStateOf(HOT_DBFS)).toBe("hot");
  });

  it("treats the documented boundaries as speech", () => {
    expect(micStateOf(SPEECH_DBFS)).toBe("good");
    expect(micStateOf(NOISE_FLOOR_DBFS + 0.1)).toBe("quiet");
  });
});

describe("readMicFrame", () => {
  it("bundles level, peak, dBFS and state for one frame", () => {
    const reading = readMicFrame(frame(0.2));
    // 0.2 amplitude quantises to 26/255 on a byte frame — about -13.8 dBFS:
    // audible speech, well below clipping.
    expect(reading.state).toBe("good");
    expect(reading.dbfs).toBeCloseTo(20 * Math.log10(26 / 128), 5);
    expect(reading.peak).toBeCloseTo(26 / 128, 5);
    expect(reading.level).toBeGreaterThan(0.5);
  });

  it("reports a silent frame as silent with a zero level", () => {
    const reading = readMicFrame(frame(0));
    expect(reading).toMatchObject({ level: 0, peak: 0, state: "silent" });
  });
});

describe("meterHint", () => {
  it("says nothing while speech is arriving, however quiet the room is", () => {
    expect(meterHint(readMicFrame(frame(0.5)))).toBe("");
    // A pause between sentences is the normal state, not a fault.
    expect(meterHint(readMicFrame(frame(0.01)), 900)).toBe("");
    expect(meterHint(readMicFrame(frame(0)), 2000)).toBe("");
  });

  it("asks about the input after a sustained stretch without speech", () => {
    expect(meterHint(readMicFrame(frame(0.01)), QUIET_HINT_MS)).toMatch(/No speech reaching/);
    expect(meterHint(readMicFrame(frame(0)), QUIET_HINT_MS + 1000)).toMatch(/No speech reaching/);
  });

  it("reports clipping immediately, because it is corrupting this line", () => {
    expect(meterHint(readMicFrame(frame(1)), 0)).toMatch(/clipping/);
  });
});

describe("constraints", () => {
  it("asks for the processed mono feed rather than the raw device", () => {
    expect(MIC_CONSTRAINTS).toMatchObject({
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1
    });
  });
});

describe("describeMicError", () => {
  it("gives each browser failure its own instruction", () => {
    expect(describeMicError({ name: "NotAllowedError" })).toMatchObject({ denied: true });
    expect(describeMicError({ name: "NotAllowedError" }).message).toMatch(/address bar/);
    expect(describeMicError({ name: "NotFoundError" }).message).toMatch(/No microphone/);
    expect(describeMicError({ name: "NotReadableError" }).message).toMatch(/another app/);
    expect(describeMicError(new Error("boom"))).toMatchObject({ denied: false });
  });
});
