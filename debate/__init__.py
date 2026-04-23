import time

from otree.api import (
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    Page,
    WaitPage,
    models,
)


class C(BaseConstants):
    NAME_IN_URL = 'debate'
    PLAYERS_PER_GROUP = 3
    NUM_ROUNDS = 1
    CHAT_DURATION_SECONDS = 3 * 60


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    # Set once all 3 players arrive; used to compute remaining chat time
    # even if a participant reloads the page.
    chat_start_time = models.FloatField()


class Player(BasePlayer):
    # Copy of participant.label so it shows up in the per-app data export
    # alongside chat behavior, making the link to the survey ID explicit.
    # Falls back to participant.code when the entry URL omits
    # ?participant_label= (public-link path), so the nickname in chat and
    # the ID shown on the Results page are always populated.
    survey_id = models.StringField(blank=True)


class GroupingWaitPage(WaitPage):
    group_by_arrival_time = True
    title_text = "Waiting for other participants"
    body_text = "We're matching you with 2 other participants. This should only take a moment."

    @staticmethod
    def after_all_players_arrive(group: Group):
        group.chat_start_time = time.time()
        for p in group.get_players():
            p.survey_id = p.participant.label or p.participant.code


class Chat(Page):
    timer_text = "Time remaining in discussion:"

    @staticmethod
    def get_timeout_seconds(player: Player):
        elapsed = time.time() - player.group.chat_start_time
        return max(0, C.CHAT_DURATION_SECONDS - elapsed)

    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            survey_id=player.survey_id,
            chat_channel=player.group.id,
        )


class Results(Page):
    @staticmethod
    def vars_for_template(player: Player):
        return dict(survey_id=player.survey_id)


page_sequence = [GroupingWaitPage, Chat, Results]
