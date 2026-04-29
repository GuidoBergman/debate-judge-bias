from otree.api import (
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    Page,
    models,
)


# A participant entering with ?participant_label=coordinator is treated as
# the room coordinator and shown a "Close room" button on the Chat page.
COORDINATOR_LABEL = 'coordinator'


class C(BaseConstants):
    NAME_IN_URL = 'debate'
    # PLAYERS_PER_GROUP=None puts every participant of the session into one
    # Group, so live_method broadcasts (`{0: payload}`) reach everyone in the
    # room — that's how the coordinator's Close click fans out.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    survey_id = models.StringField(blank=True)


def _ensure_survey_id(player: 'Player') -> str:
    if not player.field_maybe_none('survey_id'):
        player.survey_id = player.participant.label or player.participant.code
    return player.survey_id


class Chat(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            survey_id=_ensure_survey_id(player),
            chat_channel=str(player.session.code),
            is_coordinator=(player.participant.label == COORDINATOR_LABEL),
        )

    @staticmethod
    def live_method(player: Player, data):
        action = (data or {}).get('action')
        if action == 'close' and player.participant.label == COORDINATOR_LABEL:
            player.session.vars['closed'] = True
        if player.session.vars.get('closed'):
            # Broadcast to every player in the group (i.e. the whole room).
            return {0: {'closed': True}}
        return {player.id_in_group: {'closed': False}}


class Results(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return dict(survey_id=_ensure_survey_id(player))


page_sequence = [Chat, Results]
