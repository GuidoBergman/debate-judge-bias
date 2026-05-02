"""One-off: prune unused jury Player slots and empty jury sessions.

Two layers of waste accumulate when sessions were created with the old
POOL_SIZE=10000:
  1. Empty sessions: a session whose Player rows produced 0 Turn rows.
  2. Unused slots inside populated sessions: 9,998 of every 10,000
     Players in a real session never deliberated and have 0 Turn rows.

Run modes:
    python _jury_cleanup.py count     # dry run — counts only, no writes
    python _jury_cleanup.py delete    # delete empty sessions AND
                                      # prune unused slots in populated
                                      # sessions

A jury session is detected as any session with rows in jury_player
(oTree 6.x stores the session config as JSON on otree_session, so there
is no otree_session_config table to join).

Safe to remove after one successful cleanup run.
"""
import sys
from otree.main import setup; setup()
from sqlalchemy import inspect, text
from otree.database import engine


CHUNK = 5000  # delete in batches of this many ids to keep statements small


def fetch_jury_session_ids(conn):
    return [r[0] for r in conn.execute(text(
        "SELECT DISTINCT session_id FROM jury_player"
    )).fetchall()]


def fetch_empty_session_ids(conn):
    return [r[0] for r in conn.execute(text("""
        SELECT p.session_id
        FROM jury_player p
        LEFT JOIN jury_turn t ON t.player_id = p.id
        GROUP BY p.session_id
        HAVING COUNT(t.id) = 0
    """)).fetchall()]


def fetch_unused_player_rows(conn):
    """Players (in any session) with zero Turn rows. Returns (player_id,
    participant_id) pairs."""
    return [
        (r[0], r[1])
        for r in conn.execute(text("""
            SELECT p.id, p.participant_id
            FROM jury_player p
            LEFT JOIN jury_turn t ON t.player_id = p.id
            WHERE t.id IS NULL
        """)).fetchall()
    ]


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def in_clause_params(ids, prefix='id'):
    placeholders = ','.join(f':{prefix}{i}' for i in range(len(ids)))
    params = {f'{prefix}{i}': v for i, v in enumerate(ids)}
    return placeholders, params


def delete_empty_sessions(conn, tables, empty_ids):
    if not empty_ids:
        return
    placeholders, params = in_clause_params(empty_ids)

    # Unbind room→session mappings.
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
        print(f'  Cleared {room_table} bindings.')
    else:
        cols = {c['name'] for c in inspect(engine).get_columns('otree_session')}
        if 'room_name' in cols:
            conn.execute(text(
                f"UPDATE otree_session SET room_name = NULL "
                f"WHERE id IN ({placeholders})"
            ), params)
            print('  Nulled otree_session.room_name.')

    # Children first, parents last.
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
    print(f'  Deleted {len(empty_ids)} empty sessions.')


def prune_unused_slots(conn, pairs):
    """Delete jury_player rows + their otree_participant rows for slots
    that produced no Turn. Done in chunks so a 100k-row delete doesn't
    build one massive parameter list."""
    if not pairs:
        return
    total = len(pairs)
    print(f'  Pruning {total} unused (player, participant) pairs in '
          f'chunks of {CHUNK}…')
    done = 0
    for chunk in chunked(pairs, CHUNK):
        player_ids = [p[0] for p in chunk]
        participant_ids = [p[1] for p in chunk if p[1] is not None]

        ph_p, params_p = in_clause_params(player_ids, prefix='pl')
        conn.execute(text(
            f"DELETE FROM jury_player WHERE id IN ({ph_p})"
        ), params_p)

        if participant_ids:
            ph_pp, params_pp = in_clause_params(participant_ids, prefix='pp')
            conn.execute(text(
                f"DELETE FROM otree_participant WHERE id IN ({ph_pp})"
            ), params_pp)

        done += len(chunk)
        print(f'    {done}/{total}')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'count'
    print('Mode:', mode)
    tables = sorted(
        t for t in inspect(engine).get_table_names()
        if t.startswith(('jury_', 'otree_'))
    )
    print('Tables present:', tables)

    with engine.begin() as conn:
        total_ids = fetch_jury_session_ids(conn)
        empty_ids = fetch_empty_session_ids(conn)
        unused_pairs = fetch_unused_player_rows(conn)
        print(f'Total jury sessions:        {len(total_ids)}')
        print(f'  Empty (whole-session):    {len(empty_ids)}')
        print(f'  Populated:                {len(total_ids) - len(empty_ids)}')
        print(f'Unused jury_player rows:    {len(unused_pairs)}')

        if mode != 'delete':
            print('Dry run only. Re-run with `delete` to actually remove.')
            return

        # Step 1: drop empty sessions wholesale (covers all their slots).
        if empty_ids:
            print('Deleting empty sessions…')
            delete_empty_sessions(conn, tables, empty_ids)

        # Step 2: prune unused slots in remaining populated sessions.
        # Re-fetch — Step 1 already removed the empty-session players.
        unused_pairs = fetch_unused_player_rows(conn)
        if unused_pairs:
            print('Pruning unused slots in populated sessions…')
            prune_unused_slots(conn, unused_pairs)

    print('Done.')


if __name__ == '__main__':
    main()
