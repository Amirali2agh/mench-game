/**
 * @file src/types.ts
 * @description Contains all TypeScript type definitions and interfaces 
 * used across the Mensch (Ludo-style) multiplayer game.
 */

/**
 * Represents a single player registered in the game session.
 * This matches the player schema sent in both matchmaking and room syncing.
 */
export interface Player {
  id: string;       // Unique identifier generated for the player (e.g., UUID)
  name: string;     // Display name chosen by the player (supports Persian characters)
  avatar: string;   // URL pointing to the player's profile picture or avatar
}

/**
 * Represents the status of the current game session.
 * 'playing': The game is actively being played.
 * 'finished': A player has won and the game has completed.
 */
export type GameStatus = 'playing' | 'finished';

/**
 * Maps player IDs to their respective pieces' current positions.
 * Key: The player's unique ID (string).
 * Value: An array of numbers where each number represents the index of a piece.
 * The length of the array is determined by "pieces_count" (usually 2, 3, or 4).
 */
export interface PiecesState {
  [playerId: string]: number[];
}

/**
 * Represents the full, synchronized state of an active game room.
 * This directly matches the "game" object nested inside the backend's "sync_state" message.
 */
export interface GameState {
  room_id: string;          // Unique room UUID where the match takes place
  player_count: number;     // Total players required for this match (2 or 4)
  pieces_count: number;     // Number of pieces each player starts with (2, 3, or 4)
  players: Player[];        // Array of connected players, sorted in turn order
  current_turn: number;     // Index of the active player in the "players" array (0 to player_count - 1)
  dice: number | null;      // Last rolled dice value (1 to 6) or null if not yet rolled in this turn
  dice_rolled: boolean;     // True if the current player has already rolled the dice and must now move
  last_roll?: { player_id: string; value: number; roll_id?: number } | null;
  pieces: PiecesState;      // Absolute/Relative coordinates of all pieces per player
  status: GameStatus;       // The current status of the game ('playing' or 'finished')
  winner_id: string | null;  // The ID of the winner if the game has finished, otherwise null
}

/**
 * Message schema received from the queue WebSocket when a match is found.
 * Directs the frontend to switch from the matchmaking view to the active room.
 */
export interface MatchFoundMessage {
  type: 'match_found';
  room_id: string;          // UUID of the newly allocated game room
  players: Player[];        // List of matched players
  pieces_count: number;     // Selected piece count configuration
}

/**
 * Message schema received from the room WebSocket representing a board sync event.
 * Keeps the frontend UI completely updated in real-time with the server's state.
 */
export interface SyncStateMessage {
  type: 'sync_state';
  game: GameState;          // The complete up-to-date state of the game
}

export interface PlayerMeta {
  id: string;
  name: string;
  avatar: string;
}

/**
 * Message schema received from the porteghal WebSocket endpoint /ws/game/{room_id}/{player_num}.
 * Provides player metadata (names, avatars) from the porteghal platform.
 */
export interface GameInfoMessage {
  type: 'game_info';
  room_id: string;
  player_num: number;
  players: Record<string, PlayerMeta>;  // {"1": {id, name, avatar}, "2": {...}}
  coin_bet?: number;
}

/**
 * Message received from the queue WebSocket when no match was found within
 * MATCHMAKING_TIMEOUT. The player has already been removed from the queue.
 */
export interface QueueTimeoutMessage {
  type: 'queue_timeout';
  player_id: string;
}

/**
 * Message received from a room WebSocket while the roster is still incomplete.
 * The match starts as soon as `required` players are seated.
 */
export interface WaitingForPlayersMessage {
  type: 'waiting_for_players';
  room_id: string;
  joined: number;
  required: number;
  players: Player[];
}

/**
 * Message received when a room could not fill its roster in time and was
 * cancelled, so the player has to join a new room.
 */
export interface RoomTimeoutMessage {
  type: 'room_timeout';
  room_id: string;
  joined: number;
  required: number;
}

/**
 * Union type representing all possible server-to-client messages.
 * Makes handling incoming WebSocket payloads robust and type-safe.
 */
export type ServerMessage =
  | MatchFoundMessage
  | SyncStateMessage
  | GameInfoMessage
  | QueueTimeoutMessage
  | WaitingForPlayersMessage
  | RoomTimeoutMessage;

/**
 * Strongly typed payloads sent from the client to the server via Room WebSocket.
 * Includes rolling the dice, moving a piece, starting the next match, and passing
 * a turn the player cannot play.
 */
export type ClientAction =
  | { action: 'roll_dice' }
  | { action: 'move_piece'; piece_index: number }
  | { action: 'next_round' }
  /** @deprecated Server-side alias of `next_round`; kept for older clients. */
  | { action: 'restart_game' }
  | { action: 'pass_turn' };
