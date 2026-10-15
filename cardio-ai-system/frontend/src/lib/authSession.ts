/**
 * Session primitives — everything about the clinician's session that is not
 * React: where the token lives, how a request carries it, and the three calls
 * that create or end one.
 *
 * These used to sit in `auth.tsx` beside the provider, which meant that module
 * exported both a component and a dozen functions; Fast Refresh can only reload
 * a module that exports components alone, so every edit to the provider during
 * development threw away the page state. Splitting the boundary fixes that and
 * lets the API helpers be imported without pulling React in.
 */

export type User = {
  id: number;
  email: string;
  name: string;
};

type SessionResponse = { token?: string; user?: User; detail?: string };

const TOKEN_KEY = "pulseiq_token";
const USER_KEY = "pulseiq_user";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function getStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function persistSession(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function parseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    /* non-JSON error */
  }
  return fallback;
}

const FETCH_TIMEOUT_MS = 15000;

/**
 * Endpoints that call the local LLM (final report, insights, image reading)
 * legitimately take 30-90s on CPU, so callers may raise the timeout via
 * `timeoutMs` — the default stays tight for ordinary API calls.
 */
async function fetchWithTimeout(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  return fetch(path, { ...init, signal: AbortSignal.timeout(timeoutMs) });
}

/**
 * Fetch with the bearer token attached, a 15s timeout and one automatic retry
 * for transient network failures (backend restart, momentary drop). On 401
 * the local session is cleared so the app returns to the sign-in screen.
 */
export async function authFetch(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<Response> {
  const { timeoutMs = FETCH_TIMEOUT_MS, ...restInit } = init;
  const token = getToken();
  const headers = new Headers(restInit.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (restInit.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const requestInit = { ...restInit, headers };
  let response: Response;
  try {
    response = await fetchWithTimeout(path, requestInit, timeoutMs);
  } catch (firstError) {
    // One retry for network-level failures only (not HTTP errors).
    await new Promise((resolve) => setTimeout(resolve, 400));
    try {
      response = await fetchWithTimeout(path, requestInit, timeoutMs);
    } catch {
      throw firstError instanceof Error ? firstError : new Error("Network request failed.");
    }
  }

  if (response.status === 401 && token) {
    // Expired/revoked session — sign out locally. Best-effort server revoke skipped.
    clearSession();
  }
  return response;
}

async function authRequest(path: string, body: unknown, fallback: string): Promise<{ token: string; user: User }> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await parseError(response, fallback));
  }
  const data = (await response.json()) as SessionResponse;
  if (!data.token || !data.user) {
    throw new Error(fallback);
  }
  persistSession(data.token, data.user);
  return { token: data.token, user: data.user };
}

export function login(email: string, password: string) {
  return authRequest("/api/auth/login", { email, password }, "Sign-in failed. Check your credentials.");
}

export function register(email: string, password: string, name: string) {
  return authRequest("/api/auth/register", { email, password, name }, "Registration failed.");
}

export async function logout() {
  const token = getToken();
  clearSession();
  if (!token) return;
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` }
    });
  } catch {
    /* local sign-out already done */
  }
}

export function initialsOf(user: User | null): string {
  if (!user) return "?";
  const source = user.name.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").concat(parts[1]?.[0] ?? "").toUpperCase();
}
