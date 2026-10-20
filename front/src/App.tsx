/**
 * Root application component.
 * Routes between lobby, queue and board, and hosts the global overlays.
 * Supports direct room mode for porteghal-app WebView integration.
 */
import { useMemo } from 'react';
import { useMenschSocket } from './hooks/useMenschSocket';
import { LobbyScreen } from './components/LobbyScreen';
import { QueueScreen } from './components/QueueScreen';
import { GameBoard } from './components/GameBoard';
import { DevControl } from './components/DevControl';
import { DisconnectOverlay } from './components/DisconnectOverlay';
import { GameOverModal } from './components/GameOverModal';
import { OwnConnectionOverlay } from './components/OwnConnectionOverlay';
import { getQueryParams } from './utils/bridge';

export function App() {
  // The URL never changes while the page is open, so parse it once.
  const queryParams = useMemo(() => getQueryParams(), []);
  const isDirectMode = !!queryParams.roomId;

  const {
    playerId,
    playerName,
    playerAvatar,
    connectionState,
    gameState,
    disconnectedPlayer,
    chatMessages,
        error,
        joinQueue,
        rollDice,
        movePiece,
        nextRound,
        leaveGame,
        passTurn,
        sendChatMessage,
        connectionHealth,
      } = useMenschSocket();

  const renderGameContent = () => {
    // Dev-only board helper page: ?dev=1&roomId=<room_id>
    if (queryParams.dev === '1') {
      return <DevControl />;
    }

    // If we have an active game state, render the board
    if (gameState) {
      return (
        <GameBoard
          gameState={gameState}
          localPlayerId={playerId}
          onRollDice={rollDice}
          onMovePiece={movePiece}
          onLeave={leaveGame}
          chatMessages={chatMessages}
          onSendChat={sendChatMessage}
          onPassTurn={passTurn}
        />
      );
    }

    const stateStr = connectionState as string;

    // Direct room mode: show loading while connecting
    if (isDirectMode && (stateStr === 'connecting_room' || stateStr === 'connecting_queue')) {
      return (
        <div className="flex items-center justify-center min-h-screen bg-backgroundPrimary">
          <div className="text-center">
            <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-textSecondary text-sm font-semibold">در حال اتصال به بازی...</p>
          </div>
        </div>
      );
    }

    const inQueue = stateStr === 'connecting_queue' || stateStr === 'queue_waiting';
    if (inQueue) {
      return (
        <QueueScreen
          playerName={playerName}
          playerAvatar={playerAvatar}
          onLeaveQueue={leaveGame}
        />
      );
    }

    // Default to lobby screen
    return (
      <LobbyScreen
        onJoinQueue={joinQueue}
        isConnecting={stateStr === 'connecting_queue'}
      />
    );
  };

  return (
    <div className="bg-backgroundPrimary text-textPrimary min-h-screen relative">
      {renderGameContent()}

      {error && (
        <div className="fixed top-20 left-1/2 transform -translate-x-1/2 z-50 px-6 py-3 rounded-xl bg-rose-500/20 border border-rose-500 text-rose-300 text-xs font-semibold shadow-lg shadow-rose-500/10 backdrop-blur-md animate-fade-in">
          {error}
        </div>
      )}

      <DisconnectOverlay
              isOpen={!!disconnectedPlayer}
              playerName={disconnectedPlayer?.name || ''}
              timeLeft={disconnectedPlayer?.timeLeft || 60}
            />

            <OwnConnectionOverlay status={connectionHealth} />

            {gameState?.status === 'finished' && (
        <GameOverModal
          isOpen={gameState.status === 'finished'}
          winnerId={gameState.winner_id}
          players={gameState.players}
          localPlayerId={playerId}
          onNextRound={nextRound}
          onLeave={leaveGame}
        />
      )}
    </div>
  );
}
