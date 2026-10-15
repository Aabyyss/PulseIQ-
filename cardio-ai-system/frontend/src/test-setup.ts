/**
 * A `localStorage` the tests can rely on.
 *
 * Node 26 ships an experimental `localStorage` global that is inert unless the
 * process was started with `--localstorage-file` ("localStorage is not available
 * because --localstorage-file was not provided" is the warning it prints), and it
 * is the global the tests see — so `localStorage` is undefined inside a test and
 * the session tests would fail on a missing global rather than on the code that
 * writes to it. A working Storage is used if one is really there; otherwise this
 * installs the same contract the browser gives (string keys and values, `length`,
 * `key(i)`, `clear()`).
 */
class MemoryStorage {
  private entries = new Map<string, string>();

  get length(): number {
    return this.entries.size;
  }

  clear(): void {
    this.entries.clear();
  }

  getItem(key: string): string | null {
    return this.entries.has(String(key)) ? (this.entries.get(String(key)) as string) : null;
  }

  key(index: number): string | null {
    return Array.from(this.entries.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.entries.delete(String(key));
  }

  setItem(key: string, value: string): void {
    this.entries.set(String(key), String(value));
  }
}

function workingStorage(scope: Record<string, unknown> | undefined): Storage | undefined {
  try {
    const candidate = scope?.localStorage as Storage | undefined;
    if (candidate && typeof candidate.setItem === "function" && typeof candidate.getItem === "function") {
      return candidate;
    }
  } catch {
    /* the getter exists but refuses to serve storage */
  }
  return undefined;
}

function ensureStorage(scope: Record<string, unknown> | undefined) {
  if (!scope || workingStorage(scope)) return;
  Object.defineProperty(scope, "localStorage", {
    value: new MemoryStorage(),
    configurable: true,
    writable: false
  });
}

ensureStorage(globalThis as unknown as Record<string, unknown>);
ensureStorage(globalThis.window as unknown as Record<string, unknown> | undefined);
