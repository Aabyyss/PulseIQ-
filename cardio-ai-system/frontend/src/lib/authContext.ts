import { createContext, useContext } from "react";
import type { User } from "@/lib/authSession";

/**
 * The session context and the hook that reads it, kept apart from the provider.
 *
 * A file that exports a component and a hook cannot be hot-reloaded — Fast
 * Refresh only reloads modules whose exports are all components — so the
 * provider lives alone in `auth.tsx` and the hook lives here, where there is no
 * component to invalidate.
 */
export type AuthState = {
  user: User | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
