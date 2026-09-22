import { authFetch } from "@/lib/auth";
import type { DiagnosisHistoryItem, DiagnosisResponse } from "@/lib/types";

/**
 * Screening history is stored server-side, scoped to the signed-in clinician.
 * Every request carries the bearer token; the backend filters by owner, so
 * one account can never read or modify another account's records.
 */
export async function loadHistory(): Promise<DiagnosisHistoryItem[]> {
  const response = await authFetch("/api/history/screenings");
  if (!response.ok) return [];
  const body = (await response.json()) as { items?: DiagnosisHistoryItem[] };
  return body.items ?? [];
}

/** Adds via the /diagnose response (already persisted server-side). */
export function itemFromDiagnosis(result: DiagnosisResponse & { id?: number; createdAt?: string }): DiagnosisHistoryItem {
  return {
    ...result,
    id: result.id,
    createdAt: result.createdAt ?? new Date().toISOString()
  } as DiagnosisHistoryItem;
}

export async function deleteHistoryItem(id: number): Promise<boolean> {
  const response = await authFetch(`/api/history/screenings/${id}`, { method: "DELETE" });
  return response.ok;
}

export async function clearHistory(): Promise<void> {
  await authFetch("/api/history/screenings", { method: "DELETE" });
}

export async function saveConsultation(payload: Record<string, unknown>): Promise<{ id?: number } | null> {
  const response = await authFetch("/api/consultations", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  if (!response.ok) return null;
  const body = (await response.json()) as { item?: { id?: number } };
  return body.item ?? null;
}

export async function loadConsultations<T>(): Promise<T[]> {
  const response = await authFetch("/api/consultations");
  if (!response.ok) return [];
  const body = (await response.json()) as { items?: T[] };
  return body.items ?? [];
}

