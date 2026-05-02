"""One-off: count and (optionally) delete empty jury sessions on Heroku.

An "empty" jury session is one whose Player rows produced zero Turn rows
— i.e. nobody actually deliberated. These accumulate when a participant
opens a jury room URL but never starts a deliberation; with the old
POOL_SIZE=10000 each first-hit also created 10k empty Participant rows
on top of the empty session.

Run modes:
    python _jury_cleanup.py count     # dry run — counts only, no writes
    python _jury_cleanup.py delete    # actually delete the empty sessions

A "jury session" is identified as any session that has rows in
jury_player (instead of joining session_config — that table doesn't
exist in oTree 6.x; the config is a JSON column on otree_session).

Safe to delete after the cleanup run is verified.
"""
import sys
from otree.main import setup; setup()
from sqlalchemy import inspect, text
from otree.database import engine


def fetch_jury_session_ids(conn):
    return [r[0] for r in conn.execute(text("""
        SELECT DISTINCT session_id FROM jury_player
    """)).fetchall()]


def fetch_empty_ids(conn):
    return [r[0] for r in conn.execute(text("""
        SELECT p.session_id
        FROM jury_player p
        LEFT JOIN jury_turn t ON t.player_id = p.id
        GROUP BY p.session_id
        HAVING COUNT(t.id) = 0
    """)).fetchall()]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'count'
    print('Mode:', mode)
    tables = sorted(
        t for t in inspect(engine).get_table_names()
        if t.startswith(('jury_', 'otree_'))
    )
    print('Tables present:', tables)

    with engine.connect() as conn:
        total_ids = fetch_jury_session_ids(conn)
        empty_ids = fetch_empty_ids(conn)
        print(f'Total jury sessions:    {len(total_ids)}')
        print(f'Empty (to delete):       {len(empty_ids)}')
        print(f'Populated (keep):        {len(total_ids) - len(empty_ids)}')

        if mode != 'delete':
            print('Dry run only. Re-run with `delete` to actually remove.')
            return

        if not empty_ids:
            return

        placeholders = ','.join(f':id{i}' for i in range(len(empty_ids)))
        params = {f'id{i}': v for i, v in enumerate(empty_ids)}

        # Unbind rooms whose currently-bound session is being deleted.
        # oTree 6.x uses `otree_roomtosession`; older versions used
        # `otree_room_to_session`; some forks store room_name on
        # otree_session itself. Try them in order.
        room_table = next(
            (t for t in ('otree_roomtosession', 'otree_room_to_session')
             if t in tables),
            None,
        )
        if room_table is not None:
            conn.execute(text(
                f"DELETE FROM {room_table} "
                f"WHERE session_id IN ({placeholders})"
            ), params)
            print(f'Cleared {room_table} bindings for the empty sessions.')
        else:
            # Fall back to a column-based binding if it exists.
            cols = {c['name'] for c in inspect(engine).get_columns('otree_session')}
            if 'room_name' in cols:
                conn.execute(text(
                    f"UPDATE otree_session SET room_name = NULL "
                    f"WHERE id IN ({placeholders})"
                ), params)
                print('Nulled otree_session.room_name for the empty sessions.')
            else:
                print('No room-binding table or column found; skipping unbind.')

        # Delete in FK-safe order: children first, then their parents.
        conn.execute(text(
            f"DELETE FROM jury_turn WHERE player_id IN ("
            f"SELECT id FROM jury_player WHERE session_id IN ({placeholders}))"
        ), params)
        conn.execute(text(
            f"DELETE FROM jury_player WHERE session_id IN ({placeholders})"
        ), params)
        conn.execute(text(
            f"DELETE FROM jury_subsession WHERE session_id IN ({placeholders})"
        ), params)
        conn.execute(text(
            f"DELETE FROM jury_group WHERE session_id IN ({placeholders})"
        ), params)
        conn.execute(text(
            f"DELETE FROM otree_participant WHERE session_id IN ({placeholders})"
        ), params)
        conn.execute(text(
            f"DELETE FROM otree_session WHERE id IN ({placeholders})"
        ), params)
        conn.commit()

    print('Done.')


if __name__ == '__main__':
    main()
