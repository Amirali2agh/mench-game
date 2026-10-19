/**
 * @file src/components/OwnConnectionOverlay.tsx
 * @description Connection status overlay for the player's own internet/WebSocket health.
 * Two-tier: amber banner for unstable connection, full-screen overlay for disconnected.
 * This is distinct from the existing DisconnectOverlay (which shows opponent-disconnect + 60s forfeit).
 */
import React, { useEffect, useState } from 'react';

export type ConnectionHealth = 'stable' | 'unstable' | 'disconnected';

interface OwnConnectionOverlayProps {
  status: ConnectionHealth;
}

export const OwnConnectionOverlay: React.FC<OwnConnectionOverlayProps> = ({ status }) => {
  const [visibleBanner, setVisibleBanner] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  // Show the banner as soon as the connection weakens.
  useEffect(() => {
    if (status !== 'unstable') return;
    setVisibleBanner(true);
    setBannerDismissed(false);
  }, [status]);

  // Hide it a few seconds after the connection is stable again.
  useEffect(() => {
    if (status !== 'stable' || !visibleBanner) return;
    const timer = setTimeout(() => setVisibleBanner(false), 3000);
    return () => clearTimeout(timer);
  }, [status, visibleBanner]);

  // Nothing to show when stable and no lingering banner
  if (status === 'stable' && !visibleBanner) return null;

  // ═══ Full-screen disconnected overlay ═══
  if (status === 'disconnected') {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-slate-950/95 backdrop-blur-md animate-fade-in">
        {/* Wi-Fi off icon */}
        <div className="mb-8 relative">
          <div className="w-24 h-24 rounded-full bg-red-500/10 flex items-center justify-center animate-pulse">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#EF4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="2" y1="2" x2="22" y2="22" />
              <path d="M8.5 16.5a5 5 0 0 1 7 0" />
              <path d="M2 8.82a15 15 0 0 1 4.17-2.65" />
              <path d="M10.66 5.69a15 15 0 0 1 12.34 2.92" />
              <path d="M22 12.17a10 10 0 0 1-2.38 2.95" />
              <path d="M5.66 12.16a10 10 0 0 1 2.38-2.94" />
            </svg>
          </div>
          {/* Pulsing ring */}
          <div className="absolute inset-0 rounded-full border-2 border-red-500/20 animate-ping" />
        </div>

        {/* Headers */}
        <h2 className="text-2xl font-extrabold text-slate-100 mb-3">
          اتصال قطع شد
        </h2>
        <p className="text-sm text-slate-400 mb-8 text-center max-w-xs leading-relaxed">
          در حال تلاش برای اتصال مجدد...
        </p>

        {/* Spinner */}
        <div className="w-10 h-10 border-[3px] border-slate-700 border-t-amber-500 rounded-full animate-spin mb-6" />

        <p className="text-[11px] text-slate-500 max-w-[260px] text-center leading-relaxed">
          پس از بازگشت اتصال، بازی به صورت خودکار ادامه پیدا می‌کند.
        </p>
      </div>
    );
  }

  // ═══ Unstable banner (show unless manually dismissed) ═══
  if (bannerDismissed) return null;

  return (
    <div
      className={`fixed top-0 left-0 right-0 z-40 px-4 py-3 flex items-center justify-between gap-3
        bg-amber-500/90 backdrop-blur-md shadow-lg shadow-amber-500/10
        text-slate-900 text-sm font-semibold
        transition-all duration-500 ease-out
        ${visibleBanner ? 'translate-y-0 opacity-100' : '-translate-y-full opacity-0'}`}
    >
      <div className="flex items-center gap-2">
        {/* Warning icon */}
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span>اتصال اینترنت ضعیف است</span>
      </div>
      <button
        onClick={() => setBannerDismissed(true)}
        className="flex-shrink-0 w-7 h-7 rounded-full bg-slate-900/10 hover:bg-slate-900/20 flex items-center justify-center transition-colors"
        aria-label="بستن"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
};

export default OwnConnectionOverlay;