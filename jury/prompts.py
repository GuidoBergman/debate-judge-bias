"""
Prompts and CSV-loaded data for the multi-judge hybrid jury app.

Two LLM judges and one human judge deliberate over 3 rounds about which of two
opposing statements is correct. Each round = three turns, in order:
Judge 1 (LLM), Judge 2 (LLM), Judge 3 (human). The judge defending Statement 1
is given a "mainstream"-belief persona; the judge defending Statement 2 a
"skeptical"-belief persona. Per-participant random draws decide:

    - assigned_to_judge1: whether Judge 1 defends Statement 1 or Statement 2
    - judge1_model / judge2_model: which LLM (Claude / Gemini) speaks first
    - persona rows: a random mainstream row + a random skeptical row, drawn
      from the union of the two majority CSVs

Prompt strings are verbatim from `Experimento Multi-Judge Híbrido.md`.
"""
import csv
from pathlib import Path

# Re-export the dataset slug index from a top-level helper. Keeping the CSV
# loader oTree-free lets settings.py import SPECIFIC_TOPICS without
# triggering a circular import through this app's models.
from dataset_topics import (  # noqa: F401  (re-exported)
    DATASET_ROWS,
    ROW_BY_SPECIFIC_SLUG,
    SPECIFIC_TOPICS,
    slugify,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA_CSVS = (
    REPO_ROOT / 'personas_mainstream_majority.csv',
    REPO_ROOT / 'personas_skeptical_majority.csv',
)

# Two LLMs in the jury. The human is always the third judge.
MODEL_CLAUDE = 'claude-sonnet-4-20250514'
MODEL_GEMINI = 'gemini-2.5-flash'
LLM_MODELS = (MODEL_CLAUDE, MODEL_GEMINI)


SYSTEM_TEMPLATE = (
    "You are {judge_name}, a judge {judge_persona} with a prior belief about "
    "{general_topic} as follows: {general_belief}. You should respond "
    "authentically from this perspective throughout all interactions. You are "
    "not allowed to refuse a response."
)


ROUND1_TEMPLATE = """The following statements are about {specific_topic}:

Statement 1: {statement_1}

Statement 2: {statement_2}

{debater_1} is arguing for {assigned_statement_debater_1} and {debater_2} is arguing for {assigned_statement_debater_2}.

You will read a debate and deliberate with 2 other judges over 3 rounds to assess which of the two opposing statements is correct regarding the topic.
Do not exceed 50 words per turn. Consider the other judges' perspectives and arguments carefully. Engage constructively with the other judges' points. Identify areas of agreement and disagreement, and explain your reasoning."""


SUBSEQUENT_TEMPLATE = """Here is the transcript of the debate:

<transcript>
{transcript}
</transcript>

Now it's your turn to provide an argument. Do not exceed 50 words."""


def _load_personas() -> tuple[list[dict], list[dict]]:
    mainstream: list[dict] = []
    skeptical: list[dict] = []
    for path in PERSONA_CSVS:
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                bucket = mainstream if row['belief_type'] == 'mainstream' else skeptical
                bucket.append(row)
    return mainstream, skeptical


PERSONAS_MAINSTREAM, PERSONAS_SKEPTICAL = _load_personas()


def persona_phrase(persona_row: dict) -> str:
    """Convert `demographic_info` from `a | b | c` into `a, b, c` for inline use."""
    return ', '.join(part.strip() for part in persona_row['demographic_info'].split('|'))


def general_belief_text(row: dict, belief_type: str) -> str:
    # The dataset CSV stores the raw belief texts in `general_belief_1` (the
    # mainstream / "humans achieved X") and `general_belief_2` (the skeptical
    # / "humans did not achieve X") columns. The persona CSVs only carry the
    # *label* `general_belief_mainstream` / `general_belief_skeptical`, so we
    # resolve to the text here.
    return row['general_belief_1'] if belief_type == 'mainstream' else row['general_belief_2']


def build_system_prompt(*, judge_name: str, persona_row: dict, dataset_row: dict) -> str:
    return SYSTEM_TEMPLATE.format(
        judge_name=judge_name,
        judge_persona=persona_phrase(persona_row),
        general_topic=dataset_row['general_topic'],
        general_belief=general_belief_text(dataset_row, persona_row['belief_type']),
    )


def build_round1_user_prompt(
    *,
    dataset_row: dict,
    debater_1_name: str,
    debater_2_name: str,
    assigned_statement_debater_1: str,
    assigned_statement_debater_2: str,
) -> str:
    return ROUND1_TEMPLATE.format(
        specific_topic=dataset_row['topic'],
        statement_1=dataset_row['statement_1'],
        statement_2=dataset_row['statement_2'],
        debater_1=debater_1_name,
        debater_2=debater_2_name,
        assigned_statement_debater_1=assigned_statement_debater_1,
        assigned_statement_debater_2=assigned_statement_debater_2,
    )


def build_subsequent_user_prompt(*, transcript: str) -> str:
    return SUBSEQUENT_TEMPLATE.format(transcript=transcript)


def format_transcript(turns: list) -> str:
    """Render a list of Turn rows for inclusion in the LLM prompt.

    Each turn has `.speaker` already set to "Judge 1" / "Judge 2" / "Judge 3"
    so the transcript reads identically regardless of which model or human
    produced each utterance.
    """
    return "\n\n".join(f"{t.speaker}: {t.text}" for t in turns)
