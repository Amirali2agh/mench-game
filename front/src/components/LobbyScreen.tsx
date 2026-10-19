/**
 * @file src/components/LobbyScreen.tsx
 * @description Lobby registration form in Persian with premium styling.
 * Supports Unicode inputs (like Persian characters) natively.
 */

import React, { useState } from 'react';

interface LobbyScreenProps {
  /**
   * Callback triggered when the player submits the form to join the matchmaking queue.
   */
  onJoinQueue: (
    name: string,
    avatar: string,
    playerCount: number,
    piecesCount: number
  ) => void;
  /**
   * Indicates if the system is currently connecting to the matchmaking queue socket.
   */
  isConnecting: boolean;
}

export const LobbyScreen: React.FC<LobbyScreenProps> = ({ onJoinQueue, isConnecting }) => {
  // Local state for the player's name input (supports Persian typing seamlessly)
  const [name, setName] = useState<string>('');
  
  // Game size configuration (2 or 4 players)
  const [playerCount, setPlayerCount] = useState<2 | 4>(2);
  
  // Piece count per player (2, 3, or 4 pieces)
  const [piecesCount, setPiecesCount] = useState<2 | 3 | 4>(4);

  /**
   * Handles the form submission event.
   */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // Fallback default name if the input is left blank
    const finalName = name.trim() || 'بازیکن';
    
    // Generate a beautiful robot avatar based on the name seed
    const finalAvatar = `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(finalName)}`;
    
    // Pass parameters up to the parent App component
    onJoinQueue(finalName, finalAvatar, playerCount, piecesCount);
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4 bg-slate-950 text-slate-100 font-sans">
      
      {/* Glassmorphic card container */}
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md p-6 md:p-8 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-2xl backdrop-blur-md"
      >
        {/* Header Section */}
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-wide bg-gradient-to-r from-red-500 via-blue-500 to-yellow-500 bg-clip-text text-transparent">
            منچ آنلاین
          </h1>
          <p className="text-sm text-slate-400 mt-2">
            برای ورود به صف بازی اطلاعات خود را وارد کنید
          </p>
        </div>

        {/* Input Field (Supports Persian characters and input methods natively) */}
        <div className="mb-6">
          <label className="block text-sm font-semibold text-slate-300 mb-2">
            نام شما
          </label>
          <input
            type="text"
            maxLength={15}
            placeholder="نام خود را وارد کنید..."
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isConnecting}
            className="w-full px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700/50 text-slate-100 placeholder-slate-500 text-center outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all duration-200"
          />
        </div>

        {/* Player Count Selection (2 or 4) */}
        <div className="mb-6">
          <label className="block text-sm font-semibold text-slate-300 mb-2">
            تعداد بازیکنان
          </label>
          <div className="grid grid-cols-2 gap-3">
            {[2, 4].map((count) => (
              <button
                key={count}
                type="button"
                disabled={isConnecting}
                onClick={() => setPlayerCount(count as 2 | 4)}
                className={`py-3 rounded-xl font-medium border transition-all duration-200 ${
                  playerCount === count
                    ? 'bg-indigo-600 border-indigo-500 text-white shadow-lg shadow-indigo-600/30 scale-[1.02]'
                    : 'bg-slate-800/40 border-slate-700/50 text-slate-400 hover:bg-slate-800/80'
                }`}
              >
                {count} نفره
              </button>
            ))}
          </div>
        </div>

        {/* Pieces Count Selection (2, 3, or 4) */}
        <div className="mb-8">
          <label className="block text-sm font-semibold text-slate-300 mb-2">
            تعداد مهره
          </label>
          <div className="grid grid-cols-3 gap-3">
            {[2, 3, 4].map((count) => (
              <button
                key={count}
                type="button"
                disabled={isConnecting}
                onClick={() => setPiecesCount(count as 2 | 3 | 4)}
                className={`py-3 rounded-xl font-medium border transition-all duration-200 ${
                  piecesCount === count
                    ? 'bg-emerald-600 border-emerald-500 text-white shadow-lg shadow-emerald-600/30 scale-[1.02]'
                    : 'bg-slate-800/40 border-slate-700/50 text-slate-400 hover:bg-slate-800/80'
                }`}
              >
                {count} مهره
              </button>
            ))}
          </div>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isConnecting}
          className={`w-full py-4 rounded-xl font-bold text-lg tracking-wider transition-all duration-300 shadow-xl ${
            isConnecting
              ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white hover:from-indigo-600 hover:to-violet-700 hover:shadow-indigo-500/20 active:scale-[0.98]'
          }`}
        >
          {isConnecting ? (
            <div className="flex items-center justify-center gap-2">
              <span className="w-5 h-5 border-2 border-slate-500 border-t-indigo-500 rounded-full animate-spin"></span>
              در حال اتصال...
            </div>
          ) : (
            'جستجوی بازی'
          )}
        </button>

      </form>
    </div>
  );
};