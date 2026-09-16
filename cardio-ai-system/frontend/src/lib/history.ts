import type { DiagnosisHistoryItem, DiagnosisResponse } from "@/lib/types";

const HISTORY_KEY = "cardio_ai_history";

export function loadHistory(): DiagnosisHistoryItem[] {
  const raw = localStorage.getItem(HISTORY_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as DiagnosisHistoryItem[];
  } catch {
    return [];
  }
}

export function saveHistory(items: DiagnosisHistoryItem[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
}

export function addHistoryItem(result: DiagnosisResponse): DiagnosisHistoryItem[] {
  const existing = loadHistory();
  const updated = [{ ...result, createdAt: new Date().toISOString() }, ...existing].slice(0, 20);
  saveHistory(updated);
  return updated;
}
