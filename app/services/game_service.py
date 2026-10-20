from dataclasses import dataclass
import json
import random
from app.redis_client import redis_client
from app.services.board_layout import (
    TRACK_LENGTH,
    track_offsets,
    track_offsets_for_state,
)
from app.utils.redis_keys import RedisKeys
from app.utils.room_lock import room_lock

HOME_START_POSITION = 40
HOME_END_POSITION = 43

@dataclass(frozen=True)
class RollResult:
    """New state after a roll plus whether the turn auto-advances."""

    state: dict
    auto_pass: bool


class GameService:
    """
    Core game engine service managing Mensch (Ludo) board logic,
    piece movements, dice rolling, capturing, and turn propagation.
    Supports dynamic piece counts per player.
    """

    @staticmethod
    async def create_game_for_players(
        room_id: str,
        player1_meta: dict,
        player2_meta: dict,
        pieces_count: int = 4,
        player_count: int = 2,
        coin_bet: int = 0,
    ) -> dict:
        """
        Pre-create game state with both players populated (for porteghal direct room mode).
        Unlike create_game which accepts a flexible list, this ensures exactly 2 players.
        """
        players = [player1_meta, player2_meta]
        return await GameService.create_game(
            room_id, players, pieces_count, player_count, coin_bet
        )

    @staticmethod
    async def create_game(
        room_id: str,
        players: list[dict],
        pieces_count: int = 4,
        player_count: int | None = None,
        coin_bet: int = 0,
    ) -> dict:
        if player_count is None:
            player_count = len(players)

        pieces = {p["id"]: [-1] * pieces_count for p in players}

        state = {
            "room_id": room_id,
            "player_count": player_count,
            "pieces_count": pieces_count,
            "players": players,
            "current_turn": 0,
            "dice": None,
            "dice_rolled": False,
            "consecutive_sixes": 0,
            "roll_sequence": 0,
            "pieces": pieces,
            "status": "playing",
            "winner_id": None,
            "eliminated_players": [],
            "last_roll": None,
            "coin_bet": coin_bet,
            "version": 0,
            # Seat -> absolute track offset, so clients never re-implement the
            # seat plan shared by both player counts.
            "track_offsets": list(track_offsets(player_count)),
        }

        await GameService.save_game(room_id, state)
        return state

    @staticmethod
    async def get_game(room_id: str) -> dict | None:
        data = await redis_client.get(RedisKeys.room_state(room_id))
        if data:
            return json.loads(data)
        return None

    @staticmethod
    async def save_game(room_id: str, state: dict) -> None:
        # Bump the version on every write so clients can drop out-of-order
        # sync_state messages.
        state["version"] = int(state.get("version", 0)) + 1
        await redis_client.set(RedisKeys.room_state(room_id), json.dumps(state), ex=7200)

    @staticmethod
    async def roll_dice(room_id: str, player_id: str) -> RollResult:
        async with room_lock(room_id):
            state = await GameService.get_game(room_id)
            if not state:
                raise ValueError("Game not active")
            GameService._ensure_can_act(state, player_id)

            if state["dice_rolled"]:
                raise ValueError("Dice already rolled")

            rolled = random.randint(1, 6)
            state["roll_sequence"] = state.get("roll_sequence", 0) + 1
            state["dice"] = rolled
            state["last_roll"] = {
                "player_id": player_id,
                "value": rolled,
                "roll_id": state["roll_sequence"],
            }
            state["dice_rolled"] = True

            # Three consecutive sixes burn the turn.
            pass_turn = False
            if rolled == 6:
                consecutive = state.get("consecutive_sixes", 0) + 1
                state["consecutive_sixes"] = consecutive
                if consecutive == 3:
                    pass_turn = True
            else:
                state["consecutive_sixes"] = 0

            # A player without a legal move cannot keep the turn.
            if not pass_turn and not GameService._player_has_valid_moves(
                state, player_id, rolled
            ):
                pass_turn = True

            await GameService.save_game(room_id, state)

        # The turn advance is scheduled by the transport layer after the dice
        # animation; the engine only reports whether it is due.
        return RollResult(state=state, auto_pass=pass_turn)

    @staticmethod
    async def advance_after_roll(room_id: str, rolled_state: dict) -> dict | None:
        """
        Hand the turn on after the dice animation, unless another action did.

        The check-and-rotate runs under the room lock, so a pass_turn that
        landed during the animation can never rotate the turn twice.
        """
        async with room_lock(room_id):
            latest_state = await GameService.get_game(room_id)
            if latest_state is None:
                # The room was cancelled or expired; nothing to advance.
                return None
            if (
                latest_state["current_turn"] != rolled_state["current_turn"]
                or not latest_state["dice_rolled"]
            ):
                # Another action already ended this turn.
                return latest_state
            rotated = GameService._rotate_turn(latest_state or rolled_state)
            await GameService.save_game(room_id, rotated)
            return rotated

    @staticmethod
    async def move_piece(
        room_id: str,
        player_id: str,
        piece_index: int,
    ) -> dict:
        async with room_lock(room_id):
            state = await GameService.get_game(room_id)
            if not state:
                raise ValueError("Game not active")
            GameService._ensure_can_act(state, player_id)

            if not state["dice_rolled"]:
                raise ValueError("Must roll dice first")

            pieces_count = state.get("pieces_count", 4)
            if piece_index < 0 or piece_index >= pieces_count:
                raise ValueError("Invalid piece index")

            dice = state["dice"]
            if dice is None:
                raise ValueError("Dice result is unavailable")
            player_pieces = state["pieces"][player_id]
            current_pos = player_pieces[piece_index]

            is_valid, new_pos = GameService._calculate_new_position(current_pos, dice)
            if not is_valid:
                raise ValueError("Invalid move selection")
            if not GameService._is_home_position_available(
                player_pieces, piece_index, new_pos
            ):
                raise ValueError("Home cell is already occupied")

            player_pieces[piece_index] = new_pos

            captured = False
            if 0 <= new_pos <= 39:
                captured = GameService._handle_captures(state, player_id, new_pos)

            if all(
                HOME_START_POSITION <= pos <= HOME_END_POSITION for pos in player_pieces
            ):
                state["status"] = "finished"
                state["winner_id"] = player_id
            else:
                if dice == 6 or captured:
                    state["dice"] = None
                    state["dice_rolled"] = False
                else:
                    state = GameService._rotate_turn(state)

            await GameService.save_game(room_id, state)
            return state

    @staticmethod
    async def pass_turn(room_id: str, player_id: str) -> dict:
        """
        Hand the turn over, but only for the active player who cannot move.

        The client runs a turn timer, so a blocked or idle player must be able to
        pass. Passing while a legal move is still on the board is refused: it
        would let a player skip a turn instead of playing it.
        """
        async with room_lock(room_id):
            state = await GameService.get_game(room_id)
            if not state:
                raise ValueError("Game not active")
            GameService._ensure_can_act(state, player_id)

            dice = state.get("dice")
            if state.get("dice_rolled") and dice is not None:
                if GameService._player_has_valid_moves(state, player_id, dice):
                    raise ValueError("You still have a legal move")

            state = GameService._rotate_turn(state)
            await GameService.save_game(room_id, state)
            return state

    @staticmethod
    def _player_has_valid_moves(state: dict, player_id: str, dice: int) -> bool:
        pieces = state["pieces"][player_id]
        for piece_index, pos in enumerate(pieces):
            is_valid, _ = GameService._calculate_new_position(pos, dice)
            new_pos = pos + dice if pos >= 0 else 0
            if is_valid and GameService._is_home_position_available(
                pieces, piece_index, new_pos
            ):
                return True
        return False

    @staticmethod
    def _is_home_position_available(
        player_pieces: list[int], piece_index: int, position: int
    ) -> bool:
        if not HOME_START_POSITION <= position <= HOME_END_POSITION:
            return True
        return all(
            index == piece_index or piece_position != position
            for index, piece_position in enumerate(player_pieces)
        )

    @staticmethod
    def _calculate_new_position(current_pos: int, dice: int) -> tuple[bool, int]:
        if current_pos == -1:
            if dice == 6:
                return True, 0
            return False, -1

        new_pos = current_pos + dice
        if new_pos <= HOME_END_POSITION:
            return True, new_pos

        return False, current_pos

    @staticmethod
    def _handle_captures(state: dict, moving_player_id: str, relative_pos: int) -> bool:
        players = state["players"]
        player_ids = [p["id"] for p in players]

        seat_offsets = track_offsets_for_state(state)
        moving_idx = player_ids.index(moving_player_id)
        moving_abs = (seat_offsets[moving_idx % len(seat_offsets)] + relative_pos) % TRACK_LENGTH
        
        captured_any = False

        for idx, pid in enumerate(player_ids):
            if pid == moving_player_id:
                continue

            opponent_pieces = state["pieces"][pid]

            for piece_idx, opp_rel_pos in enumerate(opponent_pieces):
                if 0 <= opp_rel_pos <= 39:
                    opp_abs = (seat_offsets[idx % len(seat_offsets)] + opp_rel_pos) % TRACK_LENGTH
                    if moving_abs == opp_abs:
                        opponent_pieces[piece_idx] = -1
                        captured_any = True

        return captured_any

    @staticmethod
    def _ensure_can_act(state: dict, player_id: str) -> None:
        """Reject actions from finished games, eliminated players and idle seats."""
        if state.get("status") != "playing":
            raise ValueError("Game not active")
        if player_id in (state.get("eliminated_players") or []):
            raise ValueError("You are no longer playing this match")

        active_player = state["players"][GameService._current_player_index(state)]
        if active_player["id"] != player_id:
            raise ValueError("Not your turn")

    @staticmethod
    def _current_player_index(state: dict) -> int:
        """
        Return the index of the active seat, clamping a stale ``current_turn``.

        The roster can shrink (a player is removed) or a state can be restored
        with an out-of-range turn, so every seat lookup goes through here
        instead of indexing ``state["players"]`` directly.
        """
        players = state.get("players") or []
        if not players:
            raise ValueError("Game has no players")

        current = state.get("current_turn", 0)
        if not isinstance(current, int) or not 0 <= current < len(players):
            current = 0
            state["current_turn"] = current
        return current

    @staticmethod
    def _rotate_turn(state: dict) -> dict:
        """
        Advance the turn and reset the per-turn dice state.

        Rotation is driven by the *actual* roster length, never by the
        configured ``player_count``: the four-player non-diagonal seat order
        only applies while all four seats are occupied.
        """
        players = state.get("players") or []
        joined_count = len(players)
        current_idx = state.get("current_turn", 0)

        if joined_count:
            if state.get("player_count") == 4:
                turn_order = [seat for seat in (0, 3, 1, 2) if seat < joined_count]
            else:
                turn_order = list(range(joined_count))

            # Eliminated players (forfeit) are skipped instead of stalling the
            # match on a seat nobody owns any more.
            eliminated = set(state.get("eliminated_players") or [])
            active_seats = [
                seat for seat in turn_order if players[seat].get("id") not in eliminated
            ] or turn_order

            if not isinstance(current_idx, int) or not 0 <= current_idx < joined_count:
                # Player removed or roster restored out of range: land on the
                # first active seat instead of raising from turn_order.index().
                state["current_turn"] = active_seats[0]
            elif current_idx in active_seats:
                state["current_turn"] = active_seats[
                    (active_seats.index(current_idx) + 1) % len(active_seats)
                ]
            else:
                # The seat that just dropped out: continue after its position.
                position = (
                    turn_order.index(current_idx)
                    if current_idx in turn_order
                    else -1
                )
                following = [
                    seat for seat in active_seats if turn_order.index(seat) > position
                ]
                state["current_turn"] = following[0] if following else active_seats[0]

        # Issue #13: the previous player's roll must never leak into this turn.
        # ``last_roll`` is intentionally kept: clients replay it as history.
        state["dice"] = None
        state["dice_rolled"] = False
        state["consecutive_sixes"] = 0
        return state
