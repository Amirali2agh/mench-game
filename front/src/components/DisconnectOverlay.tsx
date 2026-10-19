/**
 * @file src/components/DisconnectOverlay.tsx
 * @description Modal overlay that alerts players when an opponent disconnects.
 * Displays a 60-second real-time countdown forfeit timer in Persian.
 */

import React from 'react';

interface DisconnectOverlayProps {
  /**
   * Controls the visibility of the overlay.
   */
  isOpen: boolean;
  /**
   * Name of the player who disconnected (supports Unicode/Persian names).
   */
  playerName: string;
  /**
   * Remaining seconds before the match is forfeited (usually starts at 60).
   */
  timeLeft: number;
}

export const DisconnectOverlay: React.FC<DisconnectOverlayProps> = ({
  isOpen,
  playerName,
  timeLeft,
}) => {
  // If no player is disconnected or timer is inactive, do not render
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[45] flex items-center justify-center p-4 bg-slate-950/90 backdrop-blur-md animate-fade-in">
      
      {/* Alert Card Box designed mobile-first */}
      <div className="w-full max-w-sm p-8 rounded-3xl bg-slate-900 border border-red-500/30 text-center shadow-2xl shadow-red-500/5 backdrop-blur-md">
        
        {/* Glowing Alert/Warning Icon with pulse animations */}
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center text-red-500 animate-pulse">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-8 h-8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
        </div>

        {/* Alarm Headers */}
        <h3 className="text-xl font-extrabold tracking-wider text-red-500 uppercase mb-2">
          قطع ارتباط
        </h3>
        
        {/* Dynamic description displaying the disconnected player's nickname */}
        <p className="text-sm text-slate-400 mb-6">
          <span className="font-bold text-slate-200">{playerName}</span> قطع ارتباط شد. در انتظار بازگشت...
        </p>

        {/* Circular/Large Countdown Timer display block */}
        <div className="relative flex items-center justify-center w-28 h-28 mx-auto mb-6 bg-slate-950/60 rounded-full border border-slate-800">
          
          {/* Subtle outer warning circle ring */}
          <div className="absolute inset-1 rounded-full border border-red-500/10 animate-ping"></div>

          {/* Numbers block displaying seconds left */}
          <div className="text-center">
            <span className="block text-4xl font-black text-red-500 leading-none">
              {timeLeft}
            </span>
            <span className="block text-[10px] uppercase tracking-widest text-slate-500 mt-1 font-semibold">
              ثانیه
            </span>
          </div>
        </div>

        {/* Explanatory subtitle regarding the forfeit rules */}
        <p className="text-[11px] text-slate-500 max-w-[240px] mx-auto leading-relaxed">
          بازی به صورت خودکار واگذار می‌شود اگر تا ۶۰ ثانیه دیگر متصل نشود.
        </p>

      </div>
    </div>
  );
};