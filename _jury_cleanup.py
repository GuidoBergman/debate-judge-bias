"""One-off: count and (optionally) delete empty jury sessions on Heroku.

An "empty" jury session is one whose Player rows produced zero Turn rows
— i.e. nobody actually deliberated. These accumulate when a participant
opens a jury room URL but never starts a deliberation; with the old
POOL_SIZE=10000 each first-hit also created 10k empty Participant rows
on top of the empty session.

Run modes:
    python _jury_cleanup.py count     # dry run — counts only, no writes
    python _jury_cleanup.py delete    # actually delete the empty sessions

Safe to delete after the cleanup run is verified.
"""
import sys
from otree.main import setup; setup()
from sqlalchemy import inspect, text
from otree.database import engine


def fetch_empty_ids(conn):
    return [r[0] for r in conn.execute(text("""
        SELECT s.id FROM otree_session s
        JOIN otree_session_config sc ON sc.id = s.config_id
        LEFT JOIN jury_player p ON p.session_id = s.id
        LEFT JOIN jury_turn t ON t.player_id = p.id
        WHERE sc.name LIKE 'jury_%'
        GROUP BY s.id
        HAVING COUNT(t.id) = 0
    """)).fetchall()]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'count'
    print('Mode:', mode)
    print('Tables present:', sorted(
        t for t in inspect(engine).get_table_names()
        if t.startswith(('jury_', 'otree_'))
    ))

    with engine.connect() as conn:
        total = conn.execute(text("""
            SELECT COUNT(*) FROM otree_session s
            JOIN otree_session_config sc ON sc.id = s.config_id
            WHERE sc.name LIKE 'jury_%'
        """)).scalar()
        empty_ids = fetch_empty_ids(conn)
        print(f'Total jury sessions:    {total}')
        print(f'Empty (to delete):       {len(empty_ids)}')
        print(f'Populated (keep):        {total - len(empty_ids)}')

        if mode != 'delete':
            print('Dry run only. Re-run with `delete` to actually remove.')
            return

        if not empty_ids:
            return

        placeholders = ','.join(f':id{i}' for i in range(len(empty_ids)))
        params = {f'id{i}': v for i, v in enumerate(empty_ids)}

        # Unbind rooms whose currently-bound session is being deleted.
        # The schema differs between oTree versions; try the dedicated
        # binding table first, fall back to a column on otree_session.
        try:
            conn.execute(text(
                f"UPDATE otree_room_to_session SET session_id = NULL "
                f"WHERE session_id IN ({placeholders})"
            ), params)
        except Exception as e:
            print('otree_room_to_session not present; falling back to '
                  'otree_session.room_name:', e)
            conn.execute(text(
                f"UPDATE otree_session SET room_name = NULL "
                f"WHERE id IN ({placeholders})"
            ), params)

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
