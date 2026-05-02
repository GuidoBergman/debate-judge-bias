"""Auto-create and auto-bind a session for each jury_room_* room on first hit.

Eliminates the admin step of pre-creating one session per topic. Patches
oTree's AssignVisitorToRoom.get so that when a participant arrives at a
jury room URL we make sure the room has a session bound (and if the
currently-bound session is filling up, we rotate to a fresh one).

POOL_SIZE is the per-session participant slot count. Each Session create
inserts that many Participant rows synchronously, so a large pool makes
the first-hit page slow and stresses Heroku Postgres under any kind of
concurrent traffic. We keep it small (10) and rotate to a fresh session
once the current one fills. Old in-flight participants keep their
existing Player record (Participant.code is stable across rotation; only
brand-new arrivals after rotation land in the new session).
"""
from otree.database import db
from otree.room import ROOM_DICT
from otree.session import create_session
from otree.views.participant import AssignVisitorToRoom


# Slots per auto-created session. Keep small — each create_session call
# does N synchronous Participant INSERTs and an upfront `creating_session`
# pass. Large values were observed to overload the web dyno and stack up
# duplicate sessions when concurrent first-hits raced before any single
# create_session committed.
POOL_SIZE = 10

# Rotate only when literally no slots remain. With POOL_SIZE=10, a higher
# threshold would force rotation on every visit (a brand-new session has
# 10 free slots, which is < any threshold > 10), defeating reuse.
ROTATE_WHEN_FREE_BELOW = 1

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
