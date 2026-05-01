"""Single source of truth for the dataset_consultancy.csv specific-topic list.

Imported by both settings.py (to register one room/session config per
specific topic for the jury app) and jury/prompts.py (for prompt-template
substitution). Kept oTree-free so settings.py can import it without
triggering circular loads of the oTree app modules.
"""
import csv
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DATASET_CSV = REPO_ROOT / 'dataset_consultancy.csv'


def slugify(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', s.lower().strip()).strip('_')


def _load_dataset_rows() -> list[dict]:
    with open(DATASET_CSV, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _build_specific_index(rows: list[dict]) -> dict[str, dict]:
    """Slugify the `topic` column; suffix duplicates with _2, _3, ..."""
    out: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for r in rows:
        base = slugify(r['topic'])
        seen[base] = seen.get(base, 0) + 1
        slug = base if seen[base] == 1 else f'{base}_{seen[base]}'
        out[slug] = r
    return out


DATASET_ROWS: list[dict] = _load_dataset_rows()
ROW_BY_SPECIFIC_SLUG: dict[str, dict] = _build_specific_index(DATASET_ROWS)

# (slug, general_topic, specific_topic) sorted by slug for stable room ordering.
SPECIFIC_TOPICS: list[tuple[str, str, str]] = sorted(
    (slug, row['general_topic'].strip(), row['topic'].strip())
    for slug, row in ROW_BY_SPECIFIC_SLUG.items()
)
