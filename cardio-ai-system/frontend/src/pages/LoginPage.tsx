import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { AlertCircle, Clock, LoaderCircle, Lock, Mail, Stethoscope, UserRound } from "lucide-react";
import { EcgTrace } from "@/components/app/ecg-trace";
import { LogoMark, Wordmark } from "@/components/app/logo";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Mode = "signin" | "signup";

const inputClass =
  "h-10 w-full rounded-lg border border-line bg-inset pl-9 pr-3 text-sm text-fg shadow-[inset_0_1px_2px_rgba(0,0,0,0.35)] transition-colors placeholder:text-faint hover:border-line2 focus:border-accent/45";

export function LoginPage() {
  const { user, ready, signIn, signUp } = useAuth();
  const { state } = useLocation() as { state?: { from?: string; idle?: boolean } };
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (ready && user) {
    return <Navigate to={state?.from ?? "/"} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "signin") {
        await signIn(email.trim(), password);
      } else {
        await signUp(email.trim(), password, name.trim());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-[46%] flex-col justify-between overflow-hidden border-r border-line bg-canvas/60 p-10 lg:flex">
        <div className="flex items-center gap-2.5">
          <LogoMark />
          <Wordmark />
        </div>
        <div className="max-w-md space-y-6">
          <div>
            <p className="label mb-3">CARDIAC SCREENING WORKSPACE</p>
            <h1 className="text-3xl font-semibold leading-tight tracking-[-0.02em] text-fg">
              Read the signal behind a symptom description.
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Each cardiologist signs in to a private workspace: their screenings, their consultations,
              their patients — never anyone else's.
            </p>
          </div>
          <EcgTrace className="h-10 w-full opacity-70" speed="7s" />
        </div>
        <ul className="space-y-2.5 text-xs text-muted">
          {[
            "Per-account history — screenings stay with their clinician",
            "All inference on-device; no data leaves this machine",
            "No API keys required"
          ].map((item) => (
            <li key={item} className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-accent" />
              {item}
            </li>
          ))}
        </ul>
        <div className="absolute right-6 top-6">
          <ThemeToggle />
        </div>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-7 flex items-center gap-2.5 lg:hidden">
            <LogoMark className="h-7 w-7" />
            <span className="text-sm font-semibold tracking-[-0.01em]">PulseIQ</span>
          </div>

          <p className="label mb-1.5">{mode === "signin" ? "WELCOME BACK" : "NEW CLINICIAN"}</p>
          <h2 className="text-xl font-semibold tracking-[-0.01em] text-fg">
            {mode === "signin" ? "Sign in to your workspace" : "Create your workspace"}
          </h2>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            {mode === "signin"
              ? "Your screening and consultation history is scoped to your account."
              : "Set up an account to keep your records private to you."}
          </p>

          {state?.idle ? (
            <Alert className="mt-5">
              <Clock />
              <AlertTitle>Locked after inactivity</AlertTitle>
              <AlertDescription>
                You were signed out after 15 minutes without activity. Your records stayed safe.
              </AlertDescription>
            </Alert>
          ) : null}

          {error ? (
            <Alert variant="destructive" className="mt-5">
              <AlertCircle />
              <AlertTitle>{mode === "signin" ? "Sign-in failed" : "Registration failed"}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {mode === "signup" ? (
              <div className="relative">
                <UserRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" strokeWidth={1.75} />
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Dr. Full name"
                  autoComplete="name"
                  className={inputClass}
                />
              </div>
            ) : null}

            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" strokeWidth={1.75} />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@hospital.org"
                autoComplete="email"
                className={inputClass}
              />
            </div>

            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" strokeWidth={1.75} />
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "signup" ? "At least 8 characters" : "Password"}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                className={inputClass}
              />
            </div>

            <Button type="submit" size="lg" disabled={busy} className="w-full">
              {busy ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Stethoscope className="h-4 w-4" strokeWidth={1.9} />
              )}
              {busy ? "One moment…" : mode === "signin" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <div className="mt-6 border-t border-line pt-4 text-center text-xs text-muted">
            {mode === "signin" ? (
              <>
                New here?{" "}
                <button type="button" onClick={() => switchMode("signup")} className="font-medium text-accent hover:underline">
                  Create an account
                </button>
              </>
            ) : (
              <>
                Already registered?{" "}
                <button type="button" onClick={() => switchMode("signin")} className="font-medium text-accent hover:underline">
                  Sign in instead
                </button>
              </>
            )}
          </div>

          <p className="mt-6 text-center text-2xs leading-relaxed text-faint">
            First time here? Read the{" "}
            <Link to="/guidance" className="font-medium text-accent hover:underline">
              guidance page
            </Link>{" "}
            before your first screening.
          </p>
        </div>
      </div>
    </div>
  );
}
