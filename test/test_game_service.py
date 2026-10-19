from app.services.game_service import GameService


def test_rotate_turn_uses_requested_four_player_order():
    state = {
        "player_count": 4,
        "players": [{"id": str(index)} for index in range(4)],
        "current_turn": 0,
        "dice_rolled": True,
        "consecutive_sixes": 2,
    }

    order = []
    for _ in range(4):
        order.append(state["current_turn"])
        GameService._rotate_turn(state)

    assert order == [0, 3, 1, 2]
    assert state["current_turn"] == 0


def test_rotate_turn_keeps_sequential_order_for_two_players():
    state = {
        "player_count": 2,
        "players": [{"id": "0"}, {"id": "1"}],
        "current_turn": 0,
        "dice_rolled": True,
        "consecutive_sixes": 2,
    }

    GameService._rotate_turn(state)

    assert state["current_turn"] == 1


def test_piece_cannot_move_into_the_center_goal():
    assert GameService._calculate_new_position(43, 1) == (False, 43)


def test_piece_can_move_to_the_last_colored_home_cell():
    assert GameService._calculate_new_position(42, 1) == (True, 43)


def test_home_cell_cannot_be_occupied_by_two_pieces():
    pieces = [40, 42, -1, -1]

    assert not GameService._is_home_position_available(pieces, 1, 40)
    assert GameService._is_home_position_available(pieces, 1, 43)


def test_blocked_home_cells_leave_no_valid_move():
    state = {"pieces": {"player": [42, 43, -1, -1]}}

    assert not GameService._player_has_valid_moves(state, "player", 2)


def test_center_position_is_not_a_valid_follow_up_move():
    state = {"pieces": {"player": [44, 44, -1, -1]}}

    assert not GameService._player_has_valid_moves(state, "player", 2)


def test_landing_on_an_opponent_piece_sends_it_back_to_base():
    state = {
        "player_count": 4,
        "players": [{"id": "red"}, {"id": "blue"}],
        "pieces": {
            "red": [10, -1, -1, -1],
            "blue": [0, -1, -1, -1],
        },
    }

    captured = GameService._handle_captures(state, "red", 10)

    assert captured
    assert state["pieces"]["blue"][0] == -1


def test_landing_on_an_opponent_home_or_base_piece_does_not_capture_it():
    state = {
        "player_count": 4,
        "players": [{"id": "red"}, {"id": "blue"}],
        "pieces": {
            "red": [40, -1, -1, -1],
            "blue": [-1, 40, -1, -1],
        },
    }

    captured = GameService._handle_captures(state, "red", 40)

    assert not captured
    assert state["pieces"]["blue"][1] == 40


def test_landing_can_capture_all_opponents_on_the_same_track_cell():
    state = {
        "player_count": 4,
        "players": [{"id": "red"}, {"id": "blue"}, {"id": "green"}],
        "pieces": {
            "red": [10, -1, -1, -1],
            "blue": [0, -1, -1, -1],
            "green": [30, -1, -1, -1],
        },
    }

    captured = GameService._handle_captures(state, "red", 10)

    assert captured
    assert state["pieces"]["blue"][0] == -1
    assert state["pieces"]["green"][0] == -1
