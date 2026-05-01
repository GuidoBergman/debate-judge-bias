"""Auto-create and auto-bind a session for each jury_room_* room on first hit.

Eliminates the admin step of pre-creating one session per topic. Patches
oTree's AssignVisitorToRoom.get so that when a participant arrives at a
jury room URL we make sure the room has a session bound (and if the
currently-bound session is filling up, we rotate to a fresh one).

Per-room pool size is set very high (POOL_SIZE) so a single auto-created
session covers all expected arrivals without rotation. Rotation kicks in
defensively when fewer than ROTATE_WHEN_FREE_BELOW slots remain — new
arrivals after that point land in the new session, while in-flight
participants keep their existing player record (each Player.id and
Participant.code is stable across rotation; the only thing rotation
changes is which session NEW visitors get assigned to).
"""
from otree.database import db
from otree.room import ROOM_DICT
from otree.session import create_session
from otree.views.participant import AssignVisitorToRoom


# Effectively-unlimited pool per session — 10k slots cost negligible DB
# space and removes the practical ceiling on participants per room.
POOL_SIZE = 10_000

# Spare slots maintained as headroom: when the active session has fewer
# than this many free slots, the next arrival triggers a rotation so we
# never hand out the literal last slot under contention.
ROTATE_WHEN_FREE_BELOW = 50

JURY_ROOM_PREFIX = 'jury_room_'


def _free_slots(session) -> int:
    used = sum(1 for p in session.pp_set if p.visited)
    return session.num_participants - used


def _ensure_session_bound(room_name: str) -> None:
    room = ROOM_DICT.get(room_name)
    if room is None:
        return
    session = room.get_session()
    if session is not None and _free_slots(session) >= ROTATE_WHEN_FREE_BELOW:
        return  # Plenty of headroom — keep current binding.
    slug = room_name[len(JURY_ROOM_PREFIX):]
    create_session(
        session_config_name=f'jury_{slug}',
        num_participants=POOL_SIZE,
        room_name=room_name,
    )
    db.commit()


_orig_get = AssignVisitorToRoom.get


def _patched_get(self, request):
    room_name = request.path_params.get('room_name', '')
    if room_name.startswith(JURY_ROOM_PREFIX):
        _ensure_session_bound(room_name)
    return _orig_get(self, request)


AssignVisitorToRoom.get = _patched_get
