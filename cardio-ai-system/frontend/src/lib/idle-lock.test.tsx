import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ACTIVITY_RESET_THROTTLE_MS, useIdleAutoLock } from "@/lib/idle-lock";

/**
 * The auto-lock is a clinical-safety control (an unattended workstation locks
 * itself), and its failure modes are invisible in review: a handler that never
 * fires locks a working clinician out mid-consultation, and one that fires too
 * often burns a timer per mouse event. Both are asserted here by rendering the
 * hook and driving real events at it.
 */
function Probe({ onLock, enabled = true }: { onLock: () => void; enabled?: boolean }) {
  useIdleAutoLock(60_000, enabled, onLock);
  return <div data-testid="probe" />;
}

/**
 * Real interaction, through jsdom's own event type. Node also exports a global
 * `Event` now, and dispatching one of those at the window reaches no listener at
 * all — a test that used it would assert against a handler that never ran.
 */
function fire(type: string) {
  window.dispatchEvent(new window.Event(type, { bubbles: true }));
}

describe("useIdleAutoLock", () => {
  let container: HTMLDivElement;
  let root: Root;
  let locks: number;

  beforeEach(() => {
    // Date is faked as well as the timers: the hook throttles its resets against
    // the wall clock, so a test that only advances the timers would look like a
    // clinician who never moved and never had their deadline pushed back.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    locks = 0;
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function render(enabled = true) {
    act(() => {
      root.render(<Probe onLock={() => (locks += 1)} enabled={enabled} />);
    });
  }

  it("locks after the timeout with no activity", () => {
    render();
    act(() => {
      vi.advanceTimersByTime(59_000);
    });
    expect(locks).toBe(0);
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(locks).toBe(1);
  });

  it("pushes the deadline back when the clinician is working", () => {
    render();
    act(() => {
      vi.advanceTimersByTime(50_000);
      fire("keydown");
    });
    act(() => {
      vi.advanceTimersByTime(50_000);
    });
    expect(locks).toBe(0);
    act(() => {
      vi.advanceTimersByTime(11_000);
    });
    expect(locks).toBe(1);
  });

  it("re-arms at most once per throttle window, however many events arrive", () => {
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    render();
    const armedOnMount = setTimeoutSpy.mock.calls.length;
    act(() => {
      // A second of a moving mouse: hundreds of events, one re-arm. The count is
      // checked against a handler that provably runs (the event below reaches
      // it), because a non-firing handler would also "pass" a ceiling.
      for (let index = 0; index < 200; index += 1) {
        fire("mousemove");
        vi.advanceTimersByTime(5);
      }
    });
    const perSecondOfMotion = setTimeoutSpy.mock.calls.length - armedOnMount;
    expect(perSecondOfMotion).toBeLessThanOrEqual(1000 / ACTIVITY_RESET_THROTTLE_MS + 1);
    expect(perSecondOfMotion).toBeGreaterThanOrEqual(1);

    // And with the throttle removed the same second would cost one timer per
    // event, which is what the count above is protecting against.
    const withoutThrottle = 200;
    expect(perSecondOfMotion).toBeLessThan(withoutThrottle);
  });

  it("does nothing while disabled", () => {
    render(false);
    act(() => {
      vi.advanceTimersByTime(600_000);
    });
    expect(locks).toBe(0);
  });

  it("stops listening once unmounted", () => {
    const removeSpy = vi.spyOn(window, "removeEventListener");
    render();
    act(() => root.unmount());
    expect(removeSpy.mock.calls.map(([type]) => type)).toEqual(
      expect.arrayContaining(["mousemove", "mousedown", "keydown", "scroll", "touchstart"])
    );
  });
});
