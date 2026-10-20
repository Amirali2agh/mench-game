"""Identifier syntax shared by the REST and WebSocket entry points.

Ids are interpolated into Redis keys, so the allowlist is strict on purpose:
no ``:``, no whitespace and no empty value means a client cannot address (or
overwrite) a key it does not own.
"""

import re

#: Player ids travel in URLs, Redis keys and tokens.
PLAYER_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"

#: Room ids are even stricter: they are part of the URL path.
ROOM_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

#: Room ids may be omitted in request bodies, where an empty value means "pick
#: one for me".
OPTIONAL_ROOM_ID_PATTERN = r"^$|" + ROOM_ID_PATTERN

_PLAYER_ID = re.compile(PLAYER_ID_PATTERN)
_ROOM_ID = re.compile(ROOM_ID_PATTERN)


def is_valid_player_id(value: object) -> bool:
    """True when ``value`` is a syntactically valid player id."""
    return isinstance(value, str) and _PLAYER_ID.fullmatch(value) is not None


def is_valid_room_id(value: object) -> bool:
    """True when ``value`` is a syntactically valid room id."""
    return isinstance(value, str) and _ROOM_ID.fullmatch(value) is not None
