/**
 * The browser's view of connectivity, wrapped so the component and its test use
 * the same two functions.
 *
 * `navigator.onLine` is a hint, not a truth: it reports the browser's link
 * state, not whether the local API answers (the engine badge covers that). Here
 * it answers one question — is the device offline, so the installed app should
 * say it is showing what it already has rather than let a save fail silently.
 */
export function isOnline(): boolean {
  if (typeof navigator === "undefined") return true;
  return navigator.onLine !== false;
}

/** Subscribe to the two events that change the answer; returns an unsubscribe. */
export function subscribeToConnectivity(handler: (online: boolean) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onOnline = () => handler(true);
  const onOffline = () => handler(false);
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  return () => {
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
  };
}
