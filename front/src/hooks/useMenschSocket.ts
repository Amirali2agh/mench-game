/**
 * Custom React hook to manage real-time game connections via WebSockets.
 * Handles matchmaking queue connection, active game room synchronization,
 * postMessage bridge to parent (porteghal-app), and direct room mode.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { GameState, ServerMessage, ClientAction, GameInfoMessage } from '../types';
import { sendToParent, getQueryParams, getWsBaseUrl } from '../utils/bridge';
import { createPlayerId } from '../utils/playerIdentity';
import type { ConnectionHealth } from '../components/OwnConnectionOverlay';

// Connection state types for tracking the exact network status.
export type SocketConnectionState =
  | 'idle'
  | 'connecting_queue'
  | 'queue_waiting'
  | 'connecting_room'
  | 'playing'
  | 'finished';

export interface DisconnectedPlayerInfo {
  id: string;
  name: string;
  timeLeft: number;
}

export interface ChatMessage {
  player_id: string;
  player_name: string;
  message: string;
  timestamp: number;
}

/** Newest messages kept in memory; older chat is dropped. */
const CHAT_HISTORY_LIMIT = 50;

export function useMenschSocket() {
  const queryParams = getQueryParams();
  const directRoomId = queryParams.roomId || null;
  const externalPlayerId = queryParams.playerId || '';
  const externalPlayerName = queryParams.playerName || '';
  const externalPlayerAvatar = queryParams.playerAvatar || '';

  const [connectionState, setConnectionState] = useState<SocketConnectionState>(
    directRoomId ? 'connecting_room' : 'idle'
  );
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [disconnectedPlayer, setDisconnectedPlayer] = useState<DisconnectedPlayerInfo | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [gameInfo, setGameInfo] = useState<GameInfoMessage | null>(null);
  const [connectionHealth, setConnectionHealth] = useState<ConnectionHealth>('stable');

  const queueSocketRef = useRef<WebSocket | null>(null);
  const roomSocketRef = useRef<WebSocket | null>(null);
  const diceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptedRef = useRef(false);

  const [playerId, _setPlayerId] = useState<string>(
    externalPlayerId || createPlayerId()
  );
  const [playerName, setPlayerName] = useState<string>(externalPlayerName);
  const [playerAvatar, setPlayerAvatar] = useState<string>(externalPlayerAvatar);
  const [roomId, setRoomId] = useState<string | null>(directRoomId);

  const wsBaseUrl = getWsBaseUrl();

  // Post GAME_FINISHED to parent when game ends
  useEffect(() => {
    if (gameState?.status === 'finished') {
      sendToParent('GAME_FINISHED', {
        winner: gameState.winner_id,
        winType: 'normal',
        playerWon: gameState.winner_id === playerId,
        roomId,
      });
    }
  }, [gameState?.status, gameState?.winner_id, playerId, roomId]);

  const disconnectAll = useCallback(() => {
    if (queueSocketRef.current) {
      queueSocketRef.current.close();
      queueSocketRef.current = null;
    }
    if (roomSocketRef.current) {
      roomSocketRef.current.close();
      roomSocketRef.current = null;
    }
  }, []);

  const clearDiceTimeout = useCallback(() => {
    if (diceTimeoutRef.current) {
      clearTimeout(diceTimeoutRef.current);
      diceTimeoutRef.current = null;
    }
  }, []);

  const connectToRoom = useCallback((rId: string, pId: string, pName: string) => {
    setConnectionState('connecting_room');
    setRoomId(rId);
    disconnectAll();
    reconnectAttemptedRef.current = false;

    const wsUrl = `${wsBaseUrl}/ws/room/${rId}?playerId=${pId}&playerName=${encodeURIComponent(pName)}`;
    const ws = new WebSocket(wsUrl);
    roomSocketRef.current = ws;

    ws.onopen = () => {
      setConnectionState('playing');
      setError(null);
      setConnectionHealth('stable');
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as ServerMessage;

        if (message.type === 'sync_state') {
          setGameState(message.game);
          // Clear dice timeout when server responds
          clearDiceTimeout();
          if (message.game.status === 'finished') {
            setConnectionState('finished');
          }
        } else if (message.type === 'player_disconnected' || message.type === 'opponent_disconnected') {
          const targetId = message.player_id;
          const targetName = message.player_name || 'حریف';
          setDisconnectedPlayer({ id: targetId, name: targetName, timeLeft: 60 });
        } else if (message.type === 'player_reconnected') {
          setDisconnectedPlayer(null);
        } else if (message.type === 'chat') {
          const chatMsg: ChatMessage = {
            player_id: message.player_id,
            player_name: message.player_name || 'کاربر',
            message: message.message,
            timestamp: Date.now(),
          };
          setChatMessages((prev) => [...prev, chatMsg].slice(-CHAT_HISTORY_LIMIT));
        } else if (message.type === 'waiting_for_players') {
          // The roster is still incomplete; the room cancels itself on timeout.
          setConnectionState('connecting_room');
        } else if (message.type === 'room_timeout') {
          setError('زمان انتظار برای تکمیل بازیکنان به پایان رسید.');
          setConnectionState('idle');
        } else if (message.type === 'game_info') {
          setGameInfo(message);
          // Update player info from porteghal-provided metadata
          if (message.players) {
            const playerMeta = message.players[String(message.player_num)];
            if (playerMeta) {
              _setPlayerId(playerMeta.id);
              setPlayerName(playerMeta.name);
              setPlayerAvatar(playerMeta.avatar);
            }
          }
        }
      } catch (err) {
        console.error('Failed to parse room WebSocket message:', err);
      }
    };

    ws.onerror = () => {
      setError('خطا در برقراری ارتباط با اتاق بازی.');
      setConnectionState('idle');
    };

    ws.onclose = () => {
      setConnectionHealth('disconnected');
      setConnectionState((prev) => (prev === 'finished' ? 'finished' : 'idle'));
    };
  }, [wsBaseUrl, disconnectAll, clearDiceTimeout]);

  useEffect(() => {
    if (directRoomId && externalPlayerId) {
      // Connect directly to the existing room WebSocket with player metadata.
      // The server incrementally builds game state as players join.
      connectToRoom(directRoomId, externalPlayerId, externalPlayerName || 'بازیکن');
    }
    return disconnectAll;
  }, [connectToRoom, directRoomId, externalPlayerId, externalPlayerName, disconnectAll]);

  const joinQueue = useCallback((name: string, avatar: string, playerCount: number, piecesCount: number) => {
    setPlayerName(name);
    setPlayerAvatar(avatar);
    setConnectionState('connecting_queue');
    setError(null);
    disconnectAll();

    const params = new URLSearchParams({
      playerId,
      playerName: name,
      playerAvatarUrl: "",
      playerCount: playerCount.toString(),
      piecesCount: piecesCount.toString()
    });

    const wsUrl = `${wsBaseUrl}/ws/queue?${params.toString()}`;
    const ws = new WebSocket(wsUrl);
    queueSocketRef.current = ws;

    ws.onopen = () => setConnectionState('queue_waiting');
    ws.onmessage = (event) => {
      try {
        const message: ServerMessage = JSON.parse(event.data);
        if (message.type === 'match_found') {
          disconnectAll();
          connectToRoom(message.room_id, playerId, name);
        } else if (message.type === 'queue_timeout') {
          setError('زمان انتظار در صف به پایان رسید. لطفاً دوباره تلاش کنید.');
          setConnectionState('idle');
          queueSocketRef.current = null;
          ws.close();
        }
      } catch (err) {
        console.error('Failed to parse queue WebSocket message:', err);
      }
    };
    ws.onerror = () => {
      setError('خطا در اتصال به صف بازی. مطمئن شوید بک‌اند روشن است.');
      setConnectionState('idle');
    };
    ws.onclose = () => {
      setConnectionState((prev) => (prev === 'queue_waiting' ? 'idle' : prev));
    };
  }, [playerId, wsBaseUrl, connectToRoom, disconnectAll]);

  const sendAction = useCallback((actionPayload: ClientAction) => {
    if (roomSocketRef.current && roomSocketRef.current.readyState === WebSocket.OPEN) {
      roomSocketRef.current.send(JSON.stringify(actionPayload));
    } else {
      console.warn('Cannot send action. Room WebSocket is not active.');
    }
  }, []);

  // rollDice with a 10-second timeout: if the server doesn't respond,
  // mark connection as unstable so the overlay shows
  const rollDice = useCallback(() => {
    sendAction({ action: 'roll_dice' });
    clearDiceTimeout();
    diceTimeoutRef.current = setTimeout(() => {
      setConnectionHealth('unstable');
    }, 10000);
  }, [sendAction, clearDiceTimeout]);

  const movePiece = useCallback((pieceIndex: number) => {
    sendAction({ action: 'move_piece', piece_index: pieceIndex });
  }, [sendAction]);
  const nextRound = useCallback(() => sendAction({ action: 'next_round' }), [sendAction]);
  const passTurn = useCallback(() => sendAction({ action: 'pass_turn' }), [sendAction]);
  const leaveGame = useCallback(() => {
    disconnectAll();
    setGameState(null);
    setConnectionState('idle');
    setDisconnectedPlayer(null);
    setChatMessages([]);
    setConnectionHealth('stable');
    sendToParent('GAME_FINISHED', { reason: 'player_left' });
  }, [disconnectAll]);

  const sendChatMessage = useCallback((text: string) => {
    if (roomSocketRef.current && roomSocketRef.current.readyState === WebSocket.OPEN) {
      roomSocketRef.current.send(JSON.stringify({
        action: 'chat',
        message: text,
        playerName: playerName,
      }));
    }
  }, [playerName]);

  // Handle local countdown timer when an opponent is disconnected
  useEffect(() => {
    if (!disconnectedPlayer) return;
    const interval = setInterval(() => {
      setDisconnectedPlayer((prev) => {
        if (!prev) return null;
        if (prev.timeLeft <= 1) {
          clearInterval(interval);
          return null;
        }
        return { ...prev, timeLeft: prev.timeLeft - 1 };
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [disconnectedPlayer]);

  // ═══ Connection health monitoring ═══

  // Listen to browser online/offline events
  useEffect(() => {
    const handleOnline = () => {
      setConnectionHealth('stable');
    };
    const handleOffline = () => {
      setConnectionHealth('disconnected');
    };
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Periodic 15s health check: detect stale sockets
  useEffect(() => {
    const interval = setInterval(() => {
      const sock = roomSocketRef.current;
      if (connectionState === 'playing') {
        if (!sock || sock.readyState !== WebSocket.OPEN) {
          if (!navigator.onLine) {
            setConnectionHealth('disconnected');
          } else if (!reconnectAttemptedRef.current) {
            // Socket is closed but browser is online — could be a transient issue
            setConnectionHealth('unstable');
            // Attempt one reconnect
            reconnectAttemptedRef.current = true;
            if (roomId && playerId && playerName) {
              connectToRoom(roomId, playerId, playerName);
            }
          }
        } else {
          // Socket is open — recover from disconnected state
          if (connectionHealth === 'disconnected' || connectionHealth === 'unstable') {
            setConnectionHealth('stable');
          }
          reconnectAttemptedRef.current = false;
        }
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [connectionState, connectionHealth, roomId, playerId, playerName, connectToRoom]);

  return {
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
    directRoomId,
    gameInfo,
    connectionHealth,
  };
}
