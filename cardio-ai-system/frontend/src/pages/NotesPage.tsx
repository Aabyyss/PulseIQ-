import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { LoaderCircle, NotebookPen, Plus, Save, Search } from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState } from "@/components/app/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { authFetch } from "@/lib/auth";
import { cn } from "@/lib/utils";

export type ClinicianNote = {
  patient_name: string;
  body: string;
  updated_at: string;
};

async function fetchNotes(): Promise<ClinicianNote[]> {
  const response = await authFetch("/api/notes");
  if (!response.ok) throw new Error("Failed to load notes.");
  const payload = (await response.json()) as { items?: ClinicianNote[] };
  return payload.items ?? [];
}

async function saveNote(patientName: string, body: string): Promise<ClinicianNote> {
  const response = await authFetch("/api/notes", {
    method: "POST",
    body: JSON.stringify({ patient_name: patientName, body })
  });
  if (response.status === 422) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail?.[0]?.msg ?? "Invalid patient name.");
  }
  if (!response.ok) throw new Error("Failed to save the note.");
  return (await response.json()) as ClinicianNote;
}

function formatStamp(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function NotesPage() {
  const [notes, setNotes] = useState<ClinicianNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const refresh = useCallback(async () => {
    try {
      const items = await fetchNotes();
      setNotes(items);
    } catch {
      setError("Notes could not be loaded. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return notes;
    return notes.filter(
      (note) =>
        note.patient_name.toLowerCase().includes(q) || note.body.toLowerCase().includes(q)
    );
  }, [notes, query]);

  function selectNote(note: ClinicianNote) {
    setSelected(note.patient_name);
    setDraft(note.body);
    setSavedAt(note.updated_at);
    setCreating(false);
    setNewName("");
    setError("");
  }

  function startCreate() {
    setCreating(true);
    setSelected(null);
    setDraft("");
    setSavedAt(null);
    setError("");
    setNewName("");
  }

  async function handleSave() {
    const name = creating ? newName.trim() : (selected ?? "");
    if (!name) {
      setError("Enter the patient name first.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const saved = await saveNote(name, draft);
      setNotes((prev) => {
        const others = prev.filter(
          (n) => n.patient_name.toLowerCase() !== saved.patient_name.toLowerCase()
        );
        return [saved, ...others];
      });
      setSelected(saved.patient_name);
      setCreating(false);
      setSavedAt(saved.updated_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the note.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Personal"
        icon={NotebookPen}
        title="My notes"
        description="A private note per patient, visible only to your account. Tag screenings with the same patient name to keep the story and the score together."
        actions={
          <Button size="sm" onClick={startCreate}>
            <Plus className="h-3.5 w-3.5" strokeWidth={2} />
            New note
          </Button>
        }
      />

      {loading ? (
        <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
          <Skeleton className="h-48 w-full" />
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[300px_1fr]">
          {/* Patient list */}
          <Card className="overflow-hidden">
            <CardContent className="space-y-3 p-3">
              <div className="relative">
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint"
                  strokeWidth={1.75}
                />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search patients…"
                  className="pl-8"
                />
              </div>

              {creating ? (
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Patient name, e.g. John Doe"
                  autoFocus
                  maxLength={120}
                />
              ) : null}

              <div className="max-h-[52vh] space-y-1 overflow-y-auto">
                {filtered.length === 0 ? (
                  <EmptyState
                    icon={NotebookPen}
                    title={notes.length === 0 ? "No notes yet" : "No matches"}
                    description={
                      notes.length === 0
                        ? "Create your first note with New note, or save one from a screening."
                        : "Try a different search."
                    }
                    className="border-0 py-8"
                  />
                ) : (
                  filtered.map((note) => (
                    <button
                      key={note.patient_name}
                      type="button"
                      onClick={() => selectNote(note)}
                      className={cn(
                        "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                        selected === note.patient_name && !creating
                          ? "border-accent/40 bg-elev"
                          : "border-transparent hover:bg-elev/60"
                      )}
                    >
                      <span className="block truncate text-xs font-medium text-fg">
                        {note.patient_name}
                      </span>
                      <span className="mt-0.5 block truncate text-2xs text-faint">
                        {note.body ? note.body.split("\n")[0] : "Empty note"} · {formatStamp(note.updated_at)}
                      </span>
                    </button>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          {/* Editor */}
          <Card>
            <CardContent className="space-y-3 p-4">
              {creating || selected ? (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-fg">
                      {creating ? "New note" : selected}
                    </h3>
                    <div className="flex items-center gap-2">
                      {savedAt ? (
                        <span className="text-2xs text-faint">Saved {formatStamp(savedAt)}</span>
                      ) : null}
                      <Button size="sm" onClick={handleSave} disabled={saving}>
                        {saving ? (
                          <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="h-3.5 w-3.5" strokeWidth={1.75} />
                        )}
                        {saving ? "Saving…" : "Save note"}
                      </Button>
                    </div>
                  </div>

                  {error ? <p className="text-xs font-medium text-danger">{error}</p> : null}

                  <Textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="e.g. Known beta-blocker intolerance. Prefers morning appointments. Previous echo 12 Mar — mild LVH, follow-up due."
                    className="min-h-[260px]"
                  />

                  <p className="text-2xs leading-relaxed text-faint">
                    Stored in your account on this machine — no other clinician can read it. Tag a
                    screening with the same patient name on the{" "}
                    <Link to="/diagnose" className="text-accent hover:underline">
                      screening page
                    </Link>{" "}
                    to link the trail.
                  </p>
                </>
              ) : (
                <EmptyState
                  icon={NotebookPen}
                  title="Select a patient note"
                  description="Pick a note on the left, or create a new one. Notes save instantly to your account."
                  className="border-0 py-16"
                />
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
