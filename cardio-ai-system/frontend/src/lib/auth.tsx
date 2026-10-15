import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AuthContext, type AuthState } from "@/lib/authContext";
import {
  clearSession,
  getStoredUser,
  getToken,
  login,
  logout,
  persistSession,
  register,
  type User
} from "@/lib/authSession";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  // Restore an existing session, verifying the token with the backend.
  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      const token = getToken();
      const stored = getStoredUser();
      if (!token || !stored) {
        setReady(true);
        return;
      }
      // This check is in flight while the sign-in form is usable, so its answer
      // may belong to a session that no longer exists. Everything below is
      // applied only while the token it verified is still the stored one:
      // otherwise a reply for the clinician who was signed in before would
      // re-apply them over whoever just signed in (or signed out).
      const stillCurrent = () => !cancelled && getToken() === token;
      try {
        const response = await fetch("/api/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(5000)
        });
        if (!stillCurrent()) return;
        if (response.ok) {
          const body = (await response.json()) as { user: User };
          if (stillCurrent()) {
            persistSession(token, body.user);
            setUser(body.user);
          }
        } else {
          clearSession();
        }
      } catch {
        // Backend unreachable: keep the cached session so the UI still works
        // for a local-first product; a 401 on any API call will clear it.
        if (stillCurrent()) setUser(stored);
      }
      if (!cancelled) setReady(true);
    };
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { user: signedIn } = await login(email, password);
    setUser(signedIn);
  }, []);

  const signUp = useCallback(async (email: string, password: string, name: string) => {
    const { user: created } = await register(email, password, name);
    setUser(created);
  }, []);

  const signOut = useCallback(async () => {
    await logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, ready, signIn, signUp, signOut }),
    [user, ready, signIn, signUp, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
