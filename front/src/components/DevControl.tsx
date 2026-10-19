/**
 * DevControl — dev-only board helper.
 *
 * Opens with ?dev=1&roomId=<room_id>. Lets you click any player's piece to
 * instantly place it on its starting cell (position 0) without rolling dice.
 * Changes are persisted via the backend and broadcast to all connected tabs.
 */
import { useEffect, useState, useCallback } from 'react';
import { GameState } from '../types';
import { getApiBaseUrl, getQueryParams } from '../utils/bridge';

const COLOR_MAP: Record<number, string> = {
  0: '#F94144', // red
  1: '#277DA1', // blue
  2: '#43AA8B', // green
  3: '#F9C74F', // yellow
};

// Mirrors the board's backend-index -> visual-corner mapping so colors match.
function getVisualIdx(backendIdx: number, playerCount: number): number {
  if (playerCount === 4) {
    if (backendIdx === 0) return 0;
    if (backendIdx === 1) return 3;
    if (backendIdx === 2) return 1;
    if (backendIdx === 3) return 2;
  }
  return backendIdx;
}

function posLabel(pos: number): string {
  if (pos === -1) return 'پایه';
  if (pos >= 0 && pos <= 39) return String(pos);
  if (pos >= 40 && pos <= 43) return `خانه ${pos - 39}`;
  return 'پایان';
}

export function DevControl() {
  const queryParams = getQueryParams();
  const [roomId, setRoomId] = useState<string>(queryParams.roomId || '');
  const [game, setGame] = useState<GameState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [stepAmount, setStepAmount] = useState(1);

  const fetchState = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/dev/room/${encodeURIComponent(id)}`);
      if (res.status === 404) {
        setGame(null);
        setError(`اتاق "${id}" پیدا نشد.`);
        return;
      }
      if (!res.ok) {
        setError(`خطا ${res.status} در دریافت وضعیت اتاق.`);
        return;
      }
      const data = await res.json();
      setGame(data);
      setError(null);
    } catch {
      setError('عدم دسترسی به بک‌اند. آدرس بک‌اند را بررسی کنید.');
    }
  }, []);

  useEffect(() => {
    if (!roomId) return;
    fetchState(roomId);
    const interval = setInterval(() => fetchState(roomId), 1000);
    return () => clearInterval(interval);
  }, [roomId, fetchState]);

  const placePiece = useCallback(
    async (playerId: string, pieceIndex: number, position: number) => {
      if (!roomId) return;
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/dev/room/${encodeURIComponent(roomId)}/place`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ player_id: playerId, piece_index: pieceIndex, position }),
        });
        if (!res.ok) {
          setError(`خطا ${res.status} در جابه‌جایی مهره.`);
          return;
        }
        const data = await res.json();
        setGame(data);
        setLastAction(`مهره ${pieceIndex + 1} ${position === -1 ? 'به پایه' : `به خانه ${position}`} رفت`);
        setTimeout(() => setLastAction(null), 2000);
      } catch {
        setError('عدم دسترسی به بک‌اند. آدرس بک‌اند را بررسی کنید.');
      }
    },
    [roomId]
  );

  const placeAll = useCallback(
    (playerId: string, position: number) => {
      if (!game) return;
      game.pieces[playerId].forEach((_, idx) => placePiece(playerId, idx, position));
    },
    [game, placePiece]
  );

  const advancePiece = useCallback(
    (playerId: string, pieceIndex: number, currentPosition: number) => {
      const nextPosition = currentPosition + stepAmount;
      if (nextPosition > 43) {
        setError('حرکت از آخرین خانه رنگی ممکن نیست.');
        return;
      }
      placePiece(playerId, pieceIndex, nextPosition);
    },
    [placePiece, stepAmount]
  );

  return (
    <div className="min-h-screen bg-[#101418] text-white p-6 flex flex-col items-center" dir="rtl">
      <div className="w-full max-w-3xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-amber-400">🧪 Dev Board</h1>
          <span className="text-xs text-gray-400">
            {game
              ? `نوبت: ${game.players[game.current_turn]?.name ?? game.current_turn} ${
                  game.dice != null ? `| تاس: ${game.dice}` : ''
                }`
              : 'در انتظار اتاق...'}
          </span>
        </div>

        <div className="flex gap-2 mb-4">
          <input
            value={roomId}
            onChange={(e) => setRoomId(e.target.value.trim())}
            placeholder="room_id"
            className="flex-1 px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-sm placeholder:text-gray-500 outline-none focus:border-amber-400"
          />
          <button
            onClick={() => roomId && fetchState(roomId)}
            className="px-4 py-2 rounded-lg bg-amber-500 text-black text-sm font-semibold hover:bg-amber-400"
          >
            اتصال
          </button>
        </div>

        <div className="flex items-center gap-2 mb-4 text-sm">
          <label htmlFor="step-amount" className="text-gray-300">
            مقدار پیشروی هر مهره
          </label>
          <input
            id="step-amount"
            type="number"
            min={1}
            max={43}
            value={stepAmount}
            onChange={(e) =>
              setStepAmount(Math.min(43, Math.max(1, Number(e.target.value) || 1)))
            }
            className="w-20 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white outline-none focus:border-amber-400"
          />
        </div>

        {error && (
          <div className="mb-4 px-4 py-2 rounded-lg bg-rose-500/20 border border-rose-500 text-rose-300 text-sm">
            {error}
          </div>
        )}
        {lastAction && (
          <div className="mb-4 px-4 py-2 rounded-lg bg-emerald-500/20 border border-emerald-500 text-emerald-300 text-sm">
            {lastAction}
          </div>
        )}

        {game && (
          <div className="space-y-3">
            {game.players.map((player, pIdx) => {
              const vIdx = getVisualIdx(pIdx, game.player_count);
              const color = COLOR_MAP[vIdx] || '#999';
              const pieces = game.pieces[player.id] || [];
              const isTurn = pIdx === game.current_turn;
              return (
                <div
                  key={player.id}
                  className={`rounded-xl border p-4 bg-white/5 ${
                    isTurn ? 'border-amber-400/60' : 'border-white/10'
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-4 h-4 rounded-full inline-block"
                        style={{ backgroundColor: color }}
                      />
                      <span className="font-semibold">
                        {player.name || player.id}
                        {isTurn && <span className="text-amber-400 text-xs mr-2">● نوبت</span>}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => placeAll(player.id, 0)}
                        className="px-3 py-1 rounded-lg bg-white/10 border border-white/20 text-xs hover:bg-white/20"
                      >
                        همه به خانه ۰
                      </button>
                      <button
                        onClick={() => placeAll(player.id, -1)}
                        className="px-3 py-1 rounded-lg bg-white/10 border border-white/20 text-xs hover:bg-white/20"
                      >
                        همه به پایه
                      </button>
                    </div>
                  </div>
                    <div className="flex flex-wrap gap-2">
                      {pieces.map((pos, i) => (
                        <div key={`${player.id}-${i}`} className="flex items-stretch">
                          <button
                            onClick={() => placePiece(player.id, i, 0)}
                            title="برای بازگشت به پایه راست کلیک کنید"
                            onContextMenu={(e) => {
                              e.preventDefault();
                              placePiece(player.id, i, -1);
                            }}
                            className="group relative flex items-center gap-2 px-3 py-2 rounded-r-lg border text-xs transition-colors"
                            style={{
                              backgroundColor: `${color}22`,
                              borderColor: `${color}88`,
                            }}
                          >
                            <span
                              className="w-3.5 h-3.5 rounded-full"
                              style={{ backgroundColor: color }}
                            />
                            <span>مهره {i + 1}</span>
                            <span className="text-gray-300">
                              {posLabel(pos)}
                            </span>
                          </button>
                          <button
                            onClick={() => advancePiece(player.id, i, pos)}
                            className="px-2 rounded-l-lg border border-r-0 border-amber-400/50 bg-amber-400/20 text-amber-300 text-xs font-semibold hover:bg-amber-400/30"
                            title={`پیشروی ${stepAmount} خانه`}
                          >
                            +{stepAmount}
                          </button>
                        </div>
                      ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
