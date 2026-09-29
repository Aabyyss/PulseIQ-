import { useCallback, useEffect, useState } from "react";
import { Brain, Check, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  clearLearnedVocabulary,
  fetchLearnedVocabulary,
  forgetLearnedPhrase,
  forgetLearnedSuppression,
  teachPhrase,
  teachSuppression,
} from "@/lib/api";
import type { LearnedPhrase, LearnedSuppression } from "@/lib/types";
import { cn } from "@/lib/utils";

const DEFAULT_CONCEPTS = [
  "chest pain",
  "shortness of breath",
  "dizziness",
  "palpitations",
  "fatigue",
  "nausea",
  "sweating",
  "leg swelling",
  "cough",
];

/** Matches the field style used across the consultation pages. */
const inputClass =
  "h-10 w-full rounded-lg border border-line bg-inset px-3 text-sm text-fg transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45";

/** Small confirm affordance shown next to a concept chip. */
export function ConceptFeedbackHint({ className }: { className?: string }) {
  return <Brain className={cn("h-3 w-3", className)} strokeWidth={1.75} />;
}

/**
 * Clinician-in-the-loop learning surface: teach PulseIQ a patient's own
 * words for a concept, or a pattern that must never count as a symptom.
 * Everything applies from the next captured line — no restart.
 */
export function LearningPanel({ className }: { className?: string }) {
  const [phrases, setPhrases] = useState<LearnedPhrase[]>([]);
  const [suppressions, setSuppressions] = useState<LearnedSuppression[]>([]);
  const [concepts, setConcepts] = useState<string[]>(DEFAULT_CONCEPTS);
  const [concept, setConcept] = useState(DEFAULT_CONCEPTS[0]);
  const [phrase, setPhrase] = useState("");
  const [pattern, setPattern] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const vocab = await fetchLearnedVocabulary();
      setPhrases(vocab.phrases);
      setSuppressions(vocab.suppressions);
      if (vocab.valid_concepts.length) setConcepts(vocab.valid_concepts);
    } catch {
      setError("Could not load what PulseIQ has learned.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!notice && !error) return;
    const timer = window.setTimeout(() => {
      setNotice("");
      setError("");
    }, 3500);
    return () => window.clearTimeout(timer);
  }, [notice, error]);

  async function handleTeach() {
    if (!phrase.trim()) return;
    setBusy(true);
    setError("");
    try {
      await teachPhrase(concept, phrase.trim(), "manual");
      setNotice(`Learned: "${phrase.trim()}" → ${concept}`);
      setPhrase("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Teaching failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSuppress() {
    if (!pattern.trim()) return;
    setBusy(true);
    setError("");
    try {
      await teachSuppression(pattern.trim(), note.trim());
      setNotice(`Lines matching /${pattern.trim()}/ will be ignored.`);
      setPattern("");
      setNote("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the pattern.");
    } finally {
      setBusy(false);
    }
  }

  async function handleForget(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove that entry.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className={className}>
      <CardHeader className="border-b border-line pb-4">
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-accent" strokeWidth={1.75} />
          Teach PulseIQ your patients' words
        </CardTitle>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          When the copilot misses how your patients actually describe a symptom, teach it once —
          it remembers for your account and applies from the very next line. Nothing is shared
          between clinicians or leaves this machine.
        </p>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_170px_auto]">
          <input
            className={inputClass}
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleTeach();
            }}
            placeholder='e.g. "mera seena ghutan bharta hai"'
            aria-label="Phrase to teach"
          />
          <select
            className={inputClass}
            value={concept}
            onChange={(e) => setConcept(e.target.value)}
            aria-label="Concept this phrase means"
          >
            {concepts.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <Button type="button" onClick={() => void handleTeach()} disabled={busy || !phrase.trim()}>
            <Check className="h-4 w-4" strokeWidth={1.9} />
            Teach
          </Button>
        </div>

        <details className="text-xs text-muted">
          <summary className="cursor-pointer select-none text-faint hover:text-muted">
            Advanced: ignore a phrasing entirely (regex)
          </summary>
          <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <input
              className={inputClass}
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="regex, e.g. hospital.*discharge"
              aria-label="Suppression pattern"
            />
            <input
              className={inputClass}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="note (optional)"
              aria-label="Suppression note"
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleSuppress()}
              disabled={busy || !pattern.trim()}
            >
              Ignore
            </Button>
          </div>
        </details>

        {notice ? <p className="text-xs font-medium text-ok-strong">{notice}</p> : null}
        {error ? <p className="text-xs font-medium text-danger-strong">{error}</p> : null}

        {phrases.length === 0 && suppressions.length === 0 ? (
          <p className="text-2xs leading-relaxed text-faint">
            Nothing learned yet. Teach a phrase above, or use the “not a symptom” correction on a
            captured line during a consultation.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {phrases.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-line bg-inset/60 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-xs text-fg">“{item.phrase}”</p>
                  <p className="mt-0.5 text-2xs text-faint">
                    means <span className="font-medium text-accent">{item.concept}</span>
                    {item.origin === "feedback" ? " · from a line correction" : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => void handleForget(() => forgetLearnedPhrase(item.id))}
                  aria-label={`Forget ${item.phrase}`}
                >
                  <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
              </li>
            ))}
            {suppressions.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-line bg-inset/60 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-xs text-fg">/{item.pattern}/</p>
                  <p className="mt-0.5 text-2xs text-faint">ignored{item.note ? ` · ${item.note}` : ""}</p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => void handleForget(() => forgetLearnedSuppression(item.id))}
                  aria-label={`Forget pattern ${item.pattern}`}
                >
                  <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
              </li>
            ))}
            <li className="pt-1 text-right">
              <button
                type="button"
                className="text-2xs text-faint hover:text-danger-strong"
                disabled={busy}
                onClick={() => void handleForget(() => clearLearnedVocabulary())}
              >
                Forget everything
              </button>
            </li>
          </ul>
        )}

        <p className="flex items-center gap-1.5 text-2xs text-faint">
          <Badge variant="outline">{phrases.length + suppressions.length} learned</Badge>
          applies to capture, screening and reports — instantly
        </p>
      </CardContent>
    </Card>
  );
}
