import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  History as HistoryIcon,
  KeyRound,
  LoaderCircle,
  LogOut,
  MonitorSmartphone,
  ShieldCheck
} from "lucide-react";
import { PageHeader } from "@/components/app/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { authFetch } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Session = {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
};

type AuditEntry = {
  action: string;
  detail: string;
  created_at: string;
};

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const response = await authFetch(url);
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

const ACTION_LABELS: Record<string, string> = {
  "account.created": "Account created",
  "auth.login": "Signed in",
  "auth.logout": "Signed out",
  "auth.password_changed": "Password changed",
  "auth.session_revoked": "A session was revoked",
  "auth.others_revoked": "Other sessions revoked"
};

function formatStamp(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit"
      });
}

export function SecurityPage() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState("");
  const [pwOk, setPwOk] = useState(false);

  const load = useCallback(async () => {
    const [s, a] = await Promise.all([
      getJSON<{ items: Session[] }>("/api/auth/sessions", { items: [] }),
      getJSON<{ items: AuditEntry[] }>("/api/auth/audit", { items: [] })
    ]);
    setSessions(s.items);
    setAudit(a.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleChangePassword(event: React.FormEvent) {
    event.preventDefault();
    setPwBusy(true);
    setPwError("");
    setPwOk(false);
    try {
      const response = await authFetch("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPw, new_password: newPw })
      });
      if (response.status === 401) {
        setPwError("Current password is incorrect.");
        return;
      }
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        setPwError(detail?.detail ?? "Could not change the password.");
        return;
      }
      // The backend rotated every token; adopt the fresh session token.
      const payload = (await response.json()) as { token?: string };
      if (payload.token) {
        try {
          localStorage.setItem("pulseiq.token", payload.token);
        } catch {
          /* storage unavailable */
        }
      }
      setPwOk(true);
      setCurrentPw("");
      setNewPw("");
      await load();
    } finally {
      setPwBusy(false);
    }
  }

  async function revoke(id: string) {
    await authFetch(`/api/auth/sessions/${id}`, { method: "DELETE" });
    await load();
  }

  async function revokeOthers() {
    await authFetch("/api/auth/sessions/revoke-others", { method: "POST" });
    await load();
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Settings"
        icon={ShieldCheck}
        title="Security"
        description="Your password, your active sessions, and the record of what happened in your account."
      />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <KeyRound className="h-4 w-4 text-accent" strokeWidth={1.75} />
              Change password
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pwOk ? (
              <Alert className="mb-4">
                <Check />
                <AlertTitle>Password updated</AlertTitle>
                <AlertDescription>
                  All other sessions were signed out automatically.
                </AlertDescription>
              </Alert>
            ) : null}
            {pwError ? (
              <Alert variant="destructive" className="mb-4">
                <AlertCircle />
                <AlertTitle>Could not change the password</AlertTitle>
                <AlertDescription>{pwError}</AlertDescription>
              </Alert>
            ) : null}
            <form onSubmit={handleChangePassword} className="space-y-3">
              <Input
                type="password"
                required
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                placeholder="Current password"
                autoComplete="current-password"
              />
              <Input
                type="password"
                required
                minLength={8}
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                placeholder="New password (at least 8 characters)"
                autoComplete="new-password"
              />
              <Button type="submit" size="sm" disabled={pwBusy}>
                {pwBusy ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" strokeWidth={1.75} />}
                {pwBusy ? "Updating…" : "Update password"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <MonitorSmartphone className="h-4 w-4 text-accent" strokeWidth={1.75} />
              Active sessions
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {sessions === null ? (
              <Skeleton className="h-20 w-full" />
            ) : sessions.length === 0 ? (
              <p className="text-xs text-faint">No active sessions.</p>
            ) : (
              <>
                <ul className="space-y-2">
                  {sessions.map((session) => (
                    <li
                      key={session.id}
                      className={cn(
                        "flex items-center gap-3 rounded-lg border px-3 py-2",
                        session.current ? "border-accent/40 bg-accent/5" : "border-line bg-inset/60"
                      )}
                    >
                      <span className="num flex-1 text-xs text-muted">…{session.id}</span>
                      <span className="text-2xs text-faint">since {formatStamp(session.created_at)}</span>
                      {session.current ? (
                        <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-px text-2xs font-medium text-accent">
                          This device
                        </span>
                      ) : (
                        <Button variant="ghost" size="sm" onClick={() => void revoke(session.id)}>
                          <LogOut className="h-3 w-3" strokeWidth={1.75} />
                          Revoke
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
                {sessions.length > 1 ? (
                  <Button variant="outline" size="sm" onClick={() => void revokeOthers()}>
                    Sign out everywhere else
                  </Button>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <HistoryIcon className="h-4 w-4 text-accent" strokeWidth={1.75} />
            Recent activity
          </CardTitle>
        </CardHeader>
        <CardContent>
          {audit === null ? (
            <Skeleton className="h-24 w-full" />
          ) : audit.length === 0 ? (
            <p className="text-xs text-faint">
              Nothing recorded yet. Sign-ins, sign-outs and password changes appear here.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {audit.map((entry, index) => (
                <li key={index} className="flex items-center gap-3 text-xs">
                  <span className="w-44 shrink-0 text-faint">{formatStamp(entry.created_at)}</span>
                  <span className="font-medium text-fg">{ACTION_LABELS[entry.action] ?? entry.action}</span>
                  {entry.detail ? <span className="truncate text-faint">{entry.detail}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
