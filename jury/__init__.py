"""Multi-judge hybrid jury: 2 LLM judges + 1 human judge deliberate over 3 rounds.

Per-participant random draws (set in creating_session, mirrored on the Player
for export):
    - judge1_position_statement: which statement Judge 1 (the first speaker)
      defends. The other LLM defends the opposite. Statement 1's defender gets
      a "mainstream"-belief persona; Statement 2's defender, "skeptical".
    - judge1_model / judge2_model: random allocation of Claude / Gemini to
      the first vs second speaking slot.
    - mainstream_persona_row_index / skeptical_persona_row_index: pointers
      into the unioned persona CSVs.

Round structure: 3 rounds, each round = Judge 1 (LLM) → Judge 2 (LLM) → Judge 3
(human). When the human first lands on Chat, Round 1's two LLM turns are
already produced (mirrors the consultant's pre-populated opening in `consult/`).
After the human submits a turn, that closes a round; the next two LLM turns
are generated and the human is prompted again. After Round 3's human turn the
Continue button appears.

All system + user prompts sent to the LLMs are persisted on the Turn row that
they produced, plus on the prompt-only rows we record for the human judge so
the export is fully self-contained.
"""
import json
import random
import time

from otree.api import (
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    ExtraModel,
    Page,
    models,
)

from . import auto_session  # noqa: F401  patches AssignVisitorToRoom.get to
                            # transparently auto-create a session per
                            # jury_room_* visit (no admin step required).
from .llm import call_llm
from .prompts import (
    LLM_MODELS,
    MODEL_CLAUDE,
    MODEL_GEMINI,
    PERSONAS_MAINSTREAM,
    PERSONAS_SKEPTICAL,
    ROW_BY_SPECIFIC_SLUG,
    build_round1_user_prompt,
    build_subsequent_user_prompt,
    build_system_prompt,
    format_transcript,
    slugify,
)


class C(BaseConstants):
    NAME_IN_URL = 'jury'
    # All "groups" hold a single participant — the room dispatcher creates a
    # new 1-participant session per arrival (see project urls.py). A None
    # value here matches what oTree expects when the app doesn't fix the
    # group size.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    # Three deliberation rounds; each round ends with the human's turn.
    NUM_DELIBERATION_ROUNDS = 3
    # Names match the prompt template's placeholders.
    JUDGE_1 = 'Judge 1'
    JUDGE_2 = 'Judge 2'
    JUDGE_3 = 'Judge 3'  # human


class Subsession(BaseSubsession):
    def creating_session(self):
        for p in self.get_players():
            _randomize(p)


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    survey_id = models.StringField(blank=True)
    # The specific-topic slug — mirror of session.config['topic_slug'] for
    # easy CSV export. Set in the dispatcher view; re-derived from
    # participant.label as a fallback if absent.
    topic_slug = models.StringField(blank=True)
    # "Statement 1" or "Statement 2" — what Judge 1 defends. Judge 2 defends
    # the opposite.
    judge1_position_statement = models.StringField(blank=True)
    # "claude" / "gemini" — which model speaks first. The other is Judge 2.
    judge1_model = models.StringField(blank=True)
    judge2_model = models.StringField(blank=True)
    # Indices into PERSONAS_MAINSTREAM / PERSONAS_SKEPTICAL respectively.
    # The mainstream-row persona is the Statement-1 defender; skeptical-row
    # the Statement-2 defender. Stored as ints so the CSV export remains
    # reconstructable from the prompt module alone.
    mainstream_persona_index = models.IntegerField(blank=True)
    skeptical_persona_index = models.IntegerField(blank=True)


class Turn(ExtraModel):
    player = models.Link(Player)
    round_number = models.IntegerField()
    # "Judge 1", "Judge 2", or "Judge 3" — matches transcript prefixes.
    speaker = models.StringField()
    # "claude", "gemini", or "human" — disambiguates which engine produced
    # the turn after random model assignment.
    speaker_engine = models.StringField()
    text = models.LongStringField()
    timestamp = models.FloatField()
    # Exact strings sent to the LLM. Empty for human turns.
    system_prompt = models.LongStringField(blank=True)
    user_prompt = models.LongStringField(blank=True)


# -----------------------------------------------------------------------------
# Setup helpers
# -----------------------------------------------------------------------------


def _randomize(player: Player) -> None:
    # Idempotent: safe to call after creating_session if a race or error
    # left fields blank.
    if not player.field_maybe_none('judge1_position_statement'):
        player.judge1_position_statement = random.choice(['Statement 1', 'Statement 2'])
    if not player.field_maybe_none('judge1_model'):
        models_shuffled = list(LLM_MODELS)
        random.shuffle(models_shuffled)
        player.judge1_model = _model_short(models_shuffled[0])
        player.judge2_model = _model_short(models_shuffled[1])
    if player.field_maybe_none('mainstream_persona_index') is None:
        player.mainstream_persona_index = random.randrange(len(PERSONAS_MAINSTREAM))
    if player.field_maybe_none('skeptical_persona_index') is None:
        player.skeptical_persona_index = random.randrange(len(PERSONAS_SKEPTICAL))


def _model_short(model_id: str) -> str:
    return 'claude' if model_id == MODEL_CLAUDE else 'gemini'


def _model_long(short: str) -> str:
    return MODEL_CLAUDE if short == 'claude' else MODEL_GEMINI


def _topic_slug(player: Player) -> str:
    return (
        player.field_maybe_none('topic_slug')
        or player.session.config.get('topic_slug', '')
    )


def _dataset_row(player: Player) -> dict:
    slug = _topic_slug(player)
    return ROW_BY_SPECIFIC_SLUG[slug]


def _persona_for(player: Player, belief_type: str) -> dict:
    if belief_type == 'mainstream':
        return PERSONAS_MAINSTREAM[player.mainstream_persona_index]
    return PERSONAS_SKEPTICAL[player.skeptical_persona_index]


def _judge_assignment(player: Player) -> dict:
    """Resolve, for this player, which judge defends what statement and which
    persona/model backs each LLM judge."""
    judge1_stmt = player.judge1_position_statement
    judge2_stmt = 'Statement 2' if judge1_stmt == 'Statement 1' else 'Statement 1'
    # The Statement 1 defender always uses the mainstream persona; Statement
    # 2 defender uses the skeptical persona.
    j1_belief = 'mainstream' if judge1_stmt == 'Statement 1' else 'skeptical'
    j2_belief = 'skeptical' if j1_belief == 'mainstream' else 'mainstream'
    return dict(
        judge1=dict(
            name=C.JUDGE_1,
            statement=judge1_stmt,
            belief=j1_belief,
            persona=_persona_for(player, j1_belief),
            model_short=player.judge1_model,
            model_id=_model_long(player.judge1_model),
        ),
        judge2=dict(
            name=C.JUDGE_2,
            statement=judge2_stmt,
            belief=j2_belief,
            persona=_persona_for(player, j2_belief),
            model_short=player.judge2_model,
            model_id=_model_long(player.judge2_model),
        ),
    )


def _turns(player: Player) -> list:
    return sorted(Turn.filter(player=player), key=lambda t: t.timestamp)


def _serialize(t: Turn) -> dict:
    return dict(
        speaker=t.speaker,
        speaker_engine=t.speaker_engine,
        text=t.text,
        round_number=t.round_number,
        speaker_class=t.speaker.lower().replace(' ', '_'),
    )


def _human_turns(player: Player) -> list:
    return [t for t in _turns(player) if t.speaker == C.JUDGE_3]


def _is_done(player: Player) -> bool:
    return len(_human_turns(player)) >= C.NUM_DELIBERATION_ROUNDS


def _next_round_number(player: Player) -> int:
    """Round the human is currently expected to argue in (1..3). Returns
    NUM_DELIBERATION_ROUNDS + 1 once the human has made all their turns."""
    return len(_human_turns(player)) + 1


# -----------------------------------------------------------------------------
# Turn generation
# -----------------------------------------------------------------------------


def _generate_round_llm_turns(player: Player, round_number: int) -> list[Turn]:
    """Produce Judge 1 then Judge 2 turns for the given round and persist them.

    For Round 1 each LLM gets the round-1 user prompt. For subsequent rounds
    each LLM gets the subsequent-round user prompt with the running transcript
    (which by then includes all prior turns including the human's last reply).

    Must be called only when no LLM turns yet exist for this round number.
    """
    a = _judge_assignment(player)
    row = _dataset_row(player)
    out: list[Turn] = []

    for judge_key in ('judge1', 'judge2'):
        j = a[judge_key]
        system_prompt = build_system_prompt(
            judge_name=j['name'],
            persona_row=j['persona'],
            dataset_row=row,
        )

        if round_number == 1:
            user_prompt = build_round1_user_prompt(
                dataset_row=row,
                debater_1_name=C.JUDGE_1,
                debater_2_name=C.JUDGE_2,
                assigned_statement_debater_1=a['judge1']['statement'],
                assigned_statement_debater_2=a['judge2']['statement'],
            )
        else:
            # Build transcript including any LLM turns already created in
            # *this* round (so Judge 2's prompt sees Judge 1's reply).
            existing = _turns(player)
            user_prompt = build_subsequent_user_prompt(
                transcript=format_transcript(existing),
            )

        text = call_llm(j['model_id'], system_prompt, user_prompt)
        now = time.time()
        turn = Turn.create(
            player=player,
            round_number=round_number,
            speaker=j['name'],
            speaker_engine=j['model_short'],
            text=text,
            timestamp=now,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        out.append(turn)

    return out


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


class Chat(Page):
    @staticmethod
    def vars_for_template(player: Player):
        # First page render seeds row, identity, topic, persona indices.
        if not player.field_maybe_none('topic_slug'):
            slug = (
                player.session.config.get('topic_slug')
                or slugify(player.participant.label or '')
            )
            if slug in ROW_BY_SPECIFIC_SLUG:
                player.topic_slug = slug

        _randomize(player)

        if not player.field_maybe_none('survey_id'):
            label = (player.participant.label or '').strip()
            # When the dispatcher creates the session it also re-sets
            # participant.label to the survey id; if missing we fall back to
            # participant.code so the Results page still has a usable handle.
            player.survey_id = label or player.participant.code

        # Lazy round-1 generation: produce Judge 1 + Judge 2 turns the first
        # time a participant lands here so the human enters mid-debate.
        if not Turn.filter(player=player):
            try:
                _generate_round_llm_turns(player, round_number=1)
            except Exception as e:
                # Surface the error in vars; don't crash the template render.
                return dict(
                    survey_id=player.survey_id,
                    topic_specific=_dataset_row(player)['topic']
                        if player.field_maybe_none('topic_slug') else '',
                    transcript=[],
                    done=False,
                    error=f'Could not start the deliberation '
                          f'({type(e).__name__}: {e}). Please reload.',
                    round_number=1,
                    total_rounds=C.NUM_DELIBERATION_ROUNDS,
                )

        return dict(
            survey_id=player.survey_id,
            topic_specific=_dataset_row(player)['topic'],
            transcript=[_serialize(t) for t in _turns(player)],
            done=_is_done(player),
            error='',
            round_number=min(_next_round_number(player), C.NUM_DELIBERATION_ROUNDS),
            total_rounds=C.NUM_DELIBERATION_ROUNDS,
        )

    @staticmethod
    def live_method(player: Player, data):
        action = data.get('action') if isinstance(data, dict) else None

        if action == 'check':
            # Tab reload while a deliberation is mid-flight: just re-send the
            # current state so the client can render whatever it missed.
            return {player.id_in_group: dict(
                msgs=[],
                done=_is_done(player),
                round_number=min(
                    _next_round_number(player), C.NUM_DELIBERATION_ROUNDS
                ),
            )}

        text = (data.get('text') or '').strip() if isinstance(data, dict) else ''
        if not text:
            return

        if _is_done(player):
            return {player.id_in_group: {'done': True}}

        round_number = _next_round_number(player)

        # Persist the human turn first.
        now = time.time()
        human_turn = Turn.create(
            player=player,
            round_number=round_number,
            speaker=C.JUDGE_3,
            speaker_engine='human',
            text=text,
            timestamp=now,
            system_prompt='',
            user_prompt='',
        )

        msgs = [_serialize(human_turn)]

        # If we just closed Round k, generate Round k+1's two LLM turns so
        # the human sees them next.
        next_round = round_number + 1
        if next_round <= C.NUM_DELIBERATION_ROUNDS:
            try:
                generated = _generate_round_llm_turns(player, round_number=next_round)
            except Exception as e:
                return {player.id_in_group: {
                    'msgs': msgs,
                    'error': f'A judge could not respond '
                             f'({type(e).__name__}). Please try again.',
                    'done': False,
                    'round_number': next_round,
                }}
            msgs.extend(_serialize(t) for t in generated)

        return {player.id_in_group: {
            'msgs': msgs,
            'done': _is_done(player),
            'round_number': min(
                _next_round_number(player), C.NUM_DELIBERATION_ROUNDS
            ),
        }}


class Results(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            survey_id=player.field_maybe_none('survey_id')
                      or player.participant.label
                      or player.participant.code,
        )


page_sequence = [Chat, Results]


def custom_export(players):
    """One CSV row per Turn — every utterance, every prompt, every assignment.

    Includes the per-player random assignments so a downstream join with the
    survey can reconstruct exactly which model defended which statement and
    what persona/belief each LLM was given."""
    yield [
        'session_code', 'participant_code', 'survey_id',
        'topic_slug',
        'judge1_position_statement', 'judge1_model', 'judge2_model',
        'mainstream_persona_index', 'skeptical_persona_index',
        'mainstream_persona_demographic', 'skeptical_persona_demographic',
        'round_number', 'speaker', 'speaker_engine', 'text', 'timestamp',
        'system_prompt', 'user_prompt',
    ]
    for p in players:
        mp_idx = p.field_maybe_none('mainstream_persona_index')
        sk_idx = p.field_maybe_none('skeptical_persona_index')
        mp = PERSONAS_MAINSTREAM[mp_idx]['demographic_info'] if mp_idx is not None else ''
        sk = PERSONAS_SKEPTICAL[sk_idx]['demographic_info'] if sk_idx is not None else ''
        for t in sorted(Turn.filter(player=p), key=lambda x: x.timestamp):
            yield [
                p.session.code,
                p.participant.code,
                p.field_maybe_none('survey_id') or '',
                _topic_slug(p),
                p.field_maybe_none('judge1_position_statement') or '',
                p.field_maybe_none('judge1_model') or '',
                p.field_maybe_none('judge2_model') or '',
                mp_idx if mp_idx is not None else '',
                sk_idx if sk_idx is not None else '',
                mp,
                sk,
                t.round_number,
                t.speaker,
                t.speaker_engine,
                t.text,
                t.timestamp,
                t.system_prompt or '',
                t.user_prompt or '',
            ]
