/**
 * @file src/components/GameOverModal.tsx
 * @description Modal overlay displayed at the end of the game match.
 * Renders victory/defeat messaging based on local player ID, and exposes action buttons.
 */

import React from 'react';
import { Player } from '../types';

interface GameOverModalProps {
  /**
   * Controls the visibility of the overlay.
   */
  isOpen: boolean;
  /**
   * Player ID of the match winner sent from the server.
   */
  winnerId: string | null;
  /**
   * List of players registered in the current active room.
   */
  players: Player[];
  /**
   * Player ID of the current local player to evaluate Victory or Defeat.
   */
  localPlayerId: string;
  /**
   * Callback to start the next match with the same players and settings.
   */
  onNextRound: () => void;
  /**
   * Callback to exit the session and return to the registration lobby screen.
   */
  onLeave: () => void;
}

export const GameOverModal: React.FC<GameOverModalProps> = ({
  isOpen,
  winnerId,
  players,
  localPlayerId,
  onNextRound,
  onLeave,
}) => {
  // If the game status is not finished, do not render anything
  if (!isOpen) return null;

  // Locate the winner object in the players list to read their nickname and avatar
  const winner = players.find((p) => p.id === winnerId);
  
  // Verify if the local player is the actual winner of this match
  const isLocalWinner = winnerId === localPlayerId;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-fade-in">
      
      {/* Centered Modal Container */}
      <div 
        className={`w-full max-w-sm p-8 rounded-3xl border-2 text-center shadow-2xl transition-all duration-300 transform scale-100 ${
          isLocalWinner 
            ? 'bg-slate-900 border-amber-500/50 shadow-amber-500/10' 
            : 'bg-slate-900 border-slate-800 shadow-slate-950/50'
        }`}
      >
        {/* Victory/Defeat Headline Icon */}
        <div className="flex justify-center mb-6">
          {isLocalWinner ? (
            // Golden Trophy SVG for Victory
            <div className="w-20 h-20 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-500 shadow-lg shadow-amber-500/20 animate-bounce">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-12 h-12">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-6.75a1.125 1.125 0 0 0-1.125 1.125v3.375m9 0H7.5m10.125-13.5A3 3 0 0 0 15 1.5H9a3 3 0 0 0-3 3M18 10.5h.75a2.25 2.25 0 0 0 2.25-2.25V6a2.25 2.25 0 0 0-2.25-2.25H18M6 10.5h-.75A2.25 2.25 0 0 1 3 8.25V6a2.25 2.25 0 0 1 2.25-2.25H6M18 10.5v1.25A2.25 2.25 0 0 1 15.75 14H8.25A2.25 2.25 0 0 1 6 11.75V10.5" />
              </svg>
            </div>
          ) : (
            // Silver Flag/Lost Icon
            <div className="w-20 h-20 rounded-full bg-slate-800 flex items-center justify-center text-slate-400">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-12 h-12">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0 2.77-.693a9 9 0 0 1 6.208.682l.108.054a9 9 0 0 0 6.086.71l3.114-.732a4.859 4.859 0 0 0 3.413-3.875V4.702a4.859 4.859 0 0 0-4.026-4.78C16.906.14 14.505.5 12 .5a8.96 8.96 0 0 0-5.025 1.521L3 3m0 12V3" />
              </svg>
            </div>
          )}
        </div>

        {/* Dynamic Title */}
        <h2 className={`text-4xl font-black tracking-widest mb-2 ${
          isLocalWinner ? 'text-amber-500 animate-pulse' : 'text-rose-500'
        }`}>
          {isLocalWinner ? 'پیروزی' : 'شکست'}
        </h2>
        
        <p className="text-sm text-slate-400 mb-6">
          {isLocalWinner 
            ? 'تبریک! شما برنده شدید.' 
            : 'حریف شما برنده شد. دوباره تلاش کنید!'}
        </p>

        {/* Winner Profile Presentation (Supports Unicode/Persian Nicknames perfectly) */}
        {winner && (
          <div className="flex items-center justify-center gap-3 p-4 mb-8 rounded-2xl bg-slate-950/60 border border-slate-800">
            <img
              src={winner.avatar}
              alt={winner.name}
              className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 object-cover"
            />
            <div className="text-right">
              <span className="block text-[10px] uppercase tracking-widest text-slate-500">برنده</span>
              <span className="block text-base font-bold text-white truncate max-w-[160px]">
                {winner.name}
              </span>
            </div>
          </div>
        )}

        {/* Action Button Grid */}
        <div className="flex flex-col gap-3">
          {/* Rematch Button - Primary Action */}
          <button
            type="button"
            onClick={onNextRound}
            className="w-full py-3.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white font-bold text-sm tracking-wider shadow-lg hover:shadow-emerald-500/15 transition-all duration-200 active:scale-[0.98]"
          >
            دور بعد
          </button>

          {/* Leave Button - Neutral/Exit Action */}
          <button
            type="button"
            onClick={onLeave}
            className="w-full py-3 rounded-xl text-rose-400 font-semibold text-xs hover:bg-rose-500/10 transition-all duration-200 mt-2"
          >
            خروج
          </button>
        </div>

      </div>
    </div>
  );
};