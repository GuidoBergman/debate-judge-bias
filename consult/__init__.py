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

from .llm import call_consultant
from .prompts import (
    PROMPTS_BY_TOPIC,
    SYSTEM_PROMPT,
    assigned_statement_for,
    build_round1,
    build_subsequent,
)


class C(BaseConstants):
    NAME_IN_URL = 'consult'
    # oTree requires None here (rejects 1). That means all N participants in
    # a session are nominally in ONE group. Isolation between participants
    # is enforced by targeting `{player.id_in_group: ...}` in every
    # live_method broadcast — never `{0: ...}` (which would broadcast to
    # the full group).
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    # 3 consultant arguments; between them the participant (acting as judge)
    # asks 2 follow-up questions. No conversation exceeds 3 consultant turns.
    CONSULTANT_TURNS = 3


class Subsession(BaseSubsession):
    def creating_session(self):
        # Assign each pre-created slot a prompt row by its arrival-order index.
        # id_in_subsession is 1..N as slots are claimed by real arrivals, so
        # row_index maps directly to the ordered CSV rows within this topic.
        # defending_statement alternates even/odd → 5 × Statement 1 and
        # 5 × Statement 2 per 10-slot topic session (balanced).
        for p in self.get_players():
            p.row_index = p.id_in_subsession - 1
            p.defending_statement = assigned_statement_for(p.row_index)


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    # Mirror of participant.label (or fallback to participant.code when the
    # room URL omits ?participant_label=) so the ID shows up in the per-app
    # CSV alongside transcript rows.
    survey_id = models.StringField(blank=True)
    # 0-based index into PROMPTS_BY_TOPIC[topic_slug]. Set in creating_session.
    row_index = models.IntegerField()
    # "Statement 1" or "Statement 2" — which side the LLM argues. Set in
    # creating_session by alternating row_index parity for balance. Exported.
    defending_statement = models.StringField()


class Turn(ExtraModel):
    # Append-only transcript, one row per utterance. Exports as its own CSV
    # from the admin Data tab.
    player = models.Link(Player)
    round_number = models.IntegerField()
    # "Consultant" (LLM) or "Judge" (participant). Names match the reference
    # script so the transcript we feed the LLM reads the same as in the
    # original pipeline.
    speaker = models.StringField()
    text = models.LongStringField()
    timestamp = models.FloatField()
    # For Consultant turns: exact strings sent to the LLM that produced
    # `text`. Empty for Judge turns. Stored so the export is fully
    # self-contained — no reconstruction needed from prompts.py + the CSV.
    system_prompt = models.LongStringField(blank=True)
    user_prompt = models.LongStringField(blank=True)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _topic_slug(player: Player) -> str:
    return player.session.config['topic_slug']


def _prompt_row(player: Player) -> dict:
    return PROMPTS_BY_TOPIC[_topic_slug(player)][player.row_index]


def _turns(player: Player) -> list:
    return sorted(Turn.filter(player=player), key=lambda t: t.timestamp)


def _format_transcript(turns: list) -> str:
    return "\n\n".join(f"{t.speaker}: {t.text}" for t in turns)


def _serialize(t: Turn) -> dict:
    # speaker_class is a lowercased CSS-class hook — oTree's template engine
    # has no |lower filter, so we pre-compute it for the server-side render.
    return dict(
        speaker=t.speaker,
        text=t.text,
        round_number=t.round_number,
        speaker_class=t.speaker.lower(),
    )


def _consultant_count(player: Player) -> int:
    return len(Turn.filter(player=player, speaker='Consultant'))


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


class Chat(Page):
    @staticmethod
    def vars_for_template(player: Player):
        if not player.field_maybe_none('survey_id'):
            player.survey_id = player.participant.label or player.participant.code

        # Self-heal row_index / defending_statement if creating_session didn't
        # populate them. Some session-creation paths (notably the demo flow,
        # and sessions created before this code landed) leave them null.
        if player.field_maybe_none('row_index') is None:
            player.row_index = player.id_in_subsession - 1
            player.defending_statement = assigned_statement_for(player.row_index)

        existing = _turns(player)
        if not existing:
            # First page load for this participant: produce the opening
            # argument. Blocking (3-8s) but reload-safe — we only run when
            # zero turns exist, so a mid-load reload doesn't duplicate.
            row = _prompt_row(player)
            user_prompt = build_round1(row, player.defending_statement)
            text = call_consultant(SYSTEM_PROMPT, user_prompt)
            Turn.create(
                player=player, round_number=1, speaker='Consultant',
                text=text, timestamp=time.time(),
                system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt,
            )
            existing = _turns(player)

        return dict(
            survey_id=player.survey_id,
            transcript=[_serialize(t) for t in existing],
            consultant_turns_total=C.CONSULTANT_TURNS,
            done=_consultant_count(player) >= C.CONSULTANT_TURNS,
        )

    @staticmethod
    def live_method(player: Player, data):
        text = (data.get('text') or '').strip()
        if not text:
            return

        consultant_count = _consultant_count(player)
        # Hard cap: refuse further input once 3 consultant turns exist.
        if consultant_count >= C.CONSULTANT_TURNS:
            return {player.id_in_group: {'done': True}}

        # Build the prompt with the participant's pending question appended
        # to the stored transcript. Nothing persists until the LLM replies.
        row = _prompt_row(player)
        existing = _turns(player)
        transcript_str = _format_transcript(existing) + f"\n\nJudge: {text}"
        prompt = build_subsequent(row, transcript_str, player.defending_statement)

        try:
            reply_text = call_consultant(SYSTEM_PROMPT, prompt)
        except Exception as e:
            return {player.id_in_group: {
                'error': f'Consultant unavailable ({type(e).__name__}). Please try again.'
            }}

        now = time.time()
        # Round numbering: the Judge's question belongs to the round the
        # consultant most recently finished; the Consultant's reply is the
        # next round.
        q = Turn.create(
            player=player, round_number=consultant_count,
            speaker='Judge', text=text, timestamp=now,
        )
        # Bump timestamp so sorted order is stable even at same-millisecond
        # creation.
        reply = Turn.create(
            player=player, round_number=consultant_count + 1,
            speaker='Consultant', text=reply_text, timestamp=now + 0.001,
            system_prompt=SYSTEM_PROMPT, user_prompt=prompt,
        )
        new_consultant_count = consultant_count + 1
        return {player.id_in_group: {
            'msgs': [_serialize(q), _serialize(reply)],
            'done': new_consultant_count >= C.CONSULTANT_TURNS,
        }}


class Results(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            survey_id=player.survey_id
                      or player.participant.label
                      or player.participant.code,
        )


page_sequence = [Chat, Results]


def custom_export(players):
    """One CSV row per Turn, joined to the player & session that produced it.
    oTree's default export doesn't surface ExtraModel rows; this hook makes
    them downloadable from the admin Data tab under Custom exports."""
    yield [
        'session_code', 'participant_code', 'survey_id',
        'topic_slug', 'row_index', 'defending_statement',
        'round_number', 'speaker', 'text', 'timestamp',
        'system_prompt', 'user_prompt',
    ]
    for p in players:
        topic_slug = p.session.config.get('topic_slug', '')
        for t in sorted(Turn.filter(player=p), key=lambda x: x.timestamp):
            yield [
                p.session.code,
                p.participant.code,
                p.field_maybe_none('survey_id') or '',
                topic_slug,
                p.field_maybe_none('row_index'),
                p.field_maybe_none('defending_statement') or '',
                t.round_number,
                t.speaker,
                t.text,
                t.timestamp,
                t.system_prompt or '',
                t.user_prompt or '',
            ]
