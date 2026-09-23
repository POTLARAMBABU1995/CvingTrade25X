import { Component, type ErrorInfo, type ReactNode } from 'react';
import { formatDiagnosticForCopy, recordBoundaryError, type DiagnosticEntry } from '../lib/diagnostics';
import { CopyTextButton } from './ui/CopyTextButton';

type ErrorBoundaryProps = {
  children: ReactNode;
  page?: string;
  shell?: ReactNode;
};

type ErrorBoundaryState = {
  diagnostic: DiagnosticEntry | null;
  failed: boolean;
  message: string;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    diagnostic: null,
    failed: false,
    message: '',
  };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      failed: true,
      message: error?.message || 'Unexpected frontend error',
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const diagnostic = recordBoundaryError(error, info.componentStack || '', this.props.page);
    this.setState({ diagnostic });
  }

  render() {
    if (!this.state.failed) {
      return this.props.children;
    }
    const copyPayload = formatDiagnosticForCopy(this.state.diagnostic, this.state.message);
    return (
      <>
        {this.props.shell || null}
        <main className="mx-auto w-full max-w-[1280px] px-4 py-6">
          <section className="card ema-error-card cving-boundary-error" role="alert">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.08em] text-rose-700">UI Error Boundary</p>
              <h2 className="mt-2 text-xl font-black text-rose-900">Something went wrong while rendering this page</h2>
              <p className="mt-2 text-sm font-semibold text-rose-800">{this.state.message}</p>
              <p className="mt-2 text-xs font-bold text-rose-700">
                Error ID: {this.state.diagnostic?.id || 'CVT25X-UNAVAILABLE'}
              </p>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <CopyTextButton text={copyPayload} label="Copy details" />
              <button
                type="button"
                className="rounded-full border border-rose-300 bg-white px-4 py-2 text-xs font-black uppercase tracking-[0.08em] text-rose-700"
                onClick={() => window.location.reload()}
              >
                Reload
              </button>
            </div>
          </section>
        </main>
      </>
    );
  }
}
