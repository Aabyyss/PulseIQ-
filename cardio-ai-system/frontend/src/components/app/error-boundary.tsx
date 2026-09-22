import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/**
 * Catches render-time crashes anywhere in the workspace and shows a recovery
 * screen instead of a white page. "Reload workspace" remounts the tree;
 * "Sign out" is offered because a corrupted cached session is a common cause.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Local-only app: keep the signal on the console, never send it anywhere.
    console.error("Workspace crash caught by boundary:", error, info.componentStack);
  }

  private handleReload = () => {
    this.setState({ error: null });
    window.location.assign("/");
  };

  private handleSignOut = () => {
    localStorage.removeItem("pulseiq_token");
    localStorage.removeItem("pulseiq_user");
    window.location.assign("/login");
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="w-full max-w-md rounded-2xl border border-line bg-panel p-8 text-center shadow-panel">
          <p className="label mb-2">SOMETHING WENT WRONG</p>
          <h1 className="text-lg font-semibold text-fg">The workspace hit an unexpected error</h1>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Your records are safe on the local server. Reload to continue where you left off.
          </p>
          {this.state.error.message ? (
            <pre className="mt-4 max-h-28 overflow-auto rounded-lg border border-line bg-inset p-3 text-left text-2xs text-faint">
              {this.state.error.message}
            </pre>
          ) : null}
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={this.handleReload}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-canvas transition-opacity hover:opacity-90"
            >
              Reload workspace
            </button>
            <button
              type="button"
              onClick={this.handleSignOut}
              className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition-colors hover:text-fg"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }
}
