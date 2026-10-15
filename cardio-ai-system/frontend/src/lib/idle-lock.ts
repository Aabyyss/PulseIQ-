import { useEffect, useRef } from "react";

const ACTIVITY_EVENTS: (keyof WindowEventMap)[] = [
  "mousemove",
  "mousedown",
  "keydown",
  "scroll",
  "touchstart"
];

/**
 * How often the idle deadline may be pushed back. `mousemove` fires hundreds of
 * times a second, and the handler used to clear and re-arm the timeout on every
 * one of them — thousands of timer allocations and re-arms per minute of moving
 * the mouse, for a deadline measured in fifteen minutes. Pushing it back at most
 * once a second costs at most a second of extra idle time and removes the churn.
 */
export const ACTIVITY_RESET_THROTTLE_MS = 1000;

/**
 * Fires `onLock` after `timeoutMs` without user activity. Timers reset on
 * any real interaction, at most once per `ACTIVITY_RESET_THROTTLE_MS`. Disabled
 * when `enabled` is false (e.g. signed out).
 */
export function useIdleAutoLock(timeoutMs: number, enabled: boolean, onLock: () => void) {
  const onLockRef = useRef(onLock);
  onLockRef.current = onLock;

  useEffect(() => {
    if (!enabled) return;

    let timer = 0;
    let lastReset = 0;

    function arm() {
      timer = window.setTimeout(() => onLockRef.current(), timeoutMs);
    }

    function reset() {
      const now = Date.now();
      if (now - lastReset < ACTIVITY_RESET_THROTTLE_MS) return;
      lastReset = now;
      window.clearTimeout(timer);
      arm();
    }

    arm();

    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, reset, { passive: true });
    }

    return () => {
      window.clearTimeout(timer);
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, reset);
      }
    };
  }, [timeoutMs, enabled]);
}

export const IDLE_LOCK_MS = 15 * 60 * 1000; // 15 minutes
