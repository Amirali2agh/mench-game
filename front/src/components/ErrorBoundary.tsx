/**
 * @file src/components/ErrorBoundary.tsx
 * @description Last-resort UI for render failures. Reports the error to the
 * Porteghal host and offers a reload instead of leaving a blank WebView.
 */

import React from 'react';
import { sendToParent } from '../utils/bridge';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error): void {
    // The host app can surface this in its own logs; the fallback below is
    // what the player sees.
    console.error('[ErrorBoundary]', error);
    sendToParent('APP_ERROR', { message: error.message });
  }

  render(): React.ReactNode {
    if (!this.state.error) return this.props.children;

    return (
      <div
        dir="rtl"
        className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950 p-4 text-center text-slate-100"
      >
        <div className="w-full max-w-sm rounded-3xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-rose-500/10 text-rose-400">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            </svg>
          </div>

          <h1 className="mb-2 text-xl font-extrabold">مشکلی پیش آمد</h1>
          <p className="mb-6 text-sm leading-relaxed text-slate-400">
            اجرای بازی با خطا متوقف شد. با بارگذاری مجدد ادامه دهید؛ اگر مشکل
            تکرار شد با پشتیبانی تماس بگیرید.
          </p>

          <button
            type="button"
            onClick={() => window.location.reload()}
            className="w-full rounded-xl bg-amber-500 py-3 text-sm font-bold text-slate-950 transition-colors hover:bg-amber-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
          >
            بارگذاری مجدد
          </button>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
