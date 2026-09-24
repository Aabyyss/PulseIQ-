import { useEffect, useRef } from "react";

const ACTIVITY_EVENTS: (keyof WindowEventMap)[] = [
  "mousemove",
  "mousedown",
  "keydown",
  "scroll",
  "touchstart"
];

/**
 * Fires `onLock` after `timeoutMs` without user activity. Timers reset on
 * any real interaction. Disabled when `enabled` is false (e.g. signed out).
 */
export function useIdleAutoLock(timeoutMs: number, enabled: boolean, onLock: () => void) {
  const onLockRef = useRef(onLock);
  onLockRef.current = onLock;

  useEffect(() => {
    if (!enabled) return;

    let timer = window.setTimeout(() => onLockRef.current(), timeoutMs);

    function reset() {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => onLockRef.current(), timeoutMs);
    }

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
