import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Rendering the recovery screen is safer than allowing a blank desktop shell.
  }

  private reload = () => {
    window.location.reload();
  };

  private openCases = () => {
    window.location.assign("/cases");
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="flex min-h-[100dvh] items-center justify-center bg-[var(--surface-1)] p-6">
        <section className="w-full max-w-xl rounded-lg border border-[var(--status-danger)]/40 bg-[var(--surface-2)] p-6 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--status-danger)]">
            Workstation interface stopped
          </p>
          <h1 className="mt-2 text-[22px] font-semibold text-[var(--text-primary)]">
            Pramaan could not render this screen
          </h1>
          <p className="mt-2 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Your case data remains in the local engine. Reload the interface, or
            return to the case registry.
          </p>
          <pre className="mt-4 max-h-40 overflow-auto rounded-md bg-[var(--surface-3)] p-3 font-mono text-[11px] text-[var(--text-secondary)]">
            {this.state.error.message}
          </pre>
          <div className="mt-5 flex gap-2">
            <button type="button" className="btn-primary" onClick={this.reload}>
              Reload interface
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={this.openCases}
            >
              Open case registry
            </button>
          </div>
        </section>
      </main>
    );
  }
}
