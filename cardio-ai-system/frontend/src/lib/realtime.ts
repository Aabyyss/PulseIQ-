/**
 * Shared realtime connection helpers for the live consultation feature.
 * Tries localhost first, then 127.0.0.1, then the current hostname, so the
 * app works across browsers/hosts that resolve localhost differently.
 */
export function getConsultationSocketCandidates(): string[] {
  const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
  const hostname = window.location.hostname;
  const candidates = [
    `${wsProtocol}://localhost:8000/ws/consultation`,
    `${wsProtocol}://127.0.0.1:8000/ws/consultation`,
  ];
  if (hostname && hostname !== "localhost" && hostname !== "127.0.0.1") {
    candidates.push(`${wsProtocol}://${hostname}:8000/ws/consultation`);
  }
  return candidates;
}

export function getConsultationSocketUrl(): string {
  return getConsultationSocketCandidates()[0];
}
