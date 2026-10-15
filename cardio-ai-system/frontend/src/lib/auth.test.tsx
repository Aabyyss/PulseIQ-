import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/lib/auth";
import { useAuth, type AuthState } from "@/lib/authContext";
import { getStoredUser, getToken, persistSession } from "@/lib/authSession";

/**
 * Switching clinician is the one flow that replaces a signed-in session, and it
 * has a race that review cannot see: the provider verifies the stored token
 * against `/auth/me` when it mounts, and that reply can land *after* the new
 * sign-in has already been accepted. A reply that is applied regardless of what
 * happened meanwhile re-applies the previous clinician — the account the user
 * just left — over the one they just signed into, which is exactly what it
 * looks like from the outside when signing in as a second account "signs into
 * the previous one".
 *
 * The two accounts are pinned here by the requests the provider makes, so the
 * test asserts the outcome the user sees, not the shape of the fix.
 */
const USER_A = { id: 1, email: "a@hospital.org", name: "Dr A" };
const USER_B = { id: 2, email: "b@hospital.org", name: "Dr B" };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

describe("AuthProvider", () => {
  let container: HTMLDivElement;
  let root: Root;
  let auth: AuthState | null;

  beforeEach(() => {
    localStorage.clear();
    auth = null;
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  function Probe() {
    auth = useAuth();
    return null;
  }

  it("keeps the clinician who just signed in when the previous session's check answers late", async () => {
    // The previous clinician's session is what the browser had on disk.
    persistSession("token-a", USER_A);

    const meReply = deferred<Response>();
    const fetchMock = vi.fn((path: string) => {
      if (path === "/api/auth/me") return meReply.promise;
      if (path === "/api/auth/login") {
        return Promise.resolve(
          new Response(JSON.stringify({ token: "token-b", user: USER_B }), { status: 200 })
        );
      }
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      root.render(
        <AuthProvider>
          <Probe />
        </AuthProvider>
      );
    });
    // The provider is still verifying the stored token at this point.
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/me", expect.anything());

    await act(async () => {
      await auth!.signIn("b@hospital.org", "password-b");
    });
    expect(auth!.user?.email).toBe(USER_B.email);

    // The verification of the clinician who was here before finally answers.
    await act(async () => {
      meReply.resolve(new Response(JSON.stringify({ user: USER_A }), { status: 200 }));
      await Promise.resolve();
    });

    expect(auth!.user?.email).toBe(USER_B.email);
    expect(getToken()).toBe("token-b");
    expect(getStoredUser()?.email).toBe(USER_B.email);
  });
});
