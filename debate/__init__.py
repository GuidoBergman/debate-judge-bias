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
    NUM_ROUNDS = 2
    CHAT_DURATION_SECONDS = 5 * 60


class Subsession(BaseSubsession):
    def creating_session(self):
        # Preserve the same 3-person grouping in round 2 so participants
        # reconnect with the same partners after the rejoin wait page.
        if self.round_number > 1:
            self.group_like_round(1)


class Group(BaseGroup):
    # Set once all 3 players arrive; used to compute remaining chat time
    # even if a participant reloads the page. Per-round field: round 2
    # gets its own fresh clock when the rejoin wait page releases.
    chat_start_time = models.FloatField()


class Player(BasePlayer):
    # Copy of participant.label so it shows up in the per-app data export
    # alongside chat behavior, making the link to the survey ID explicit.
    survey_id = models.StringField(blank=True)


class GroupingWaitPage(WaitPage):
    group_by_arrival_time = True
    title_text = "Waiting for other participants"
    body_text = "We're matching you with 2 other participants. This should only take a moment."

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def after_all_players_arrive(group: Group):
        group.chat_start_time = time.time()
        for p in group.get_players():
            p.survey_id = p.participant.label or ''


class Chat(Page):
    timer_text = "Time remaining in discussion:"

    @staticmethod
    def get_timeout_seconds(player: Player):
        elapsed = time.time() - player.group.chat_start_time
        return max(0, C.CHAT_DURATION_SECONDS - elapsed)

    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            survey_id=player.participant.label or '(no id)',
            # Stable channel across rounds so round-2 chat shows the
            # round-1 transcript and participants keep the same thread.
            chat_channel=player.group.in_round(1).id,
            round_number=player.round_number,
        )


class RejoinWaitPage(WaitPage):
    # Non-arrival wait page: holds round-2 entry until all 3 players have
    # clicked "finished" on round-1 Chat. The round-2 clock is not stamped
    # here — it's anchored when the first player clicks Start on the
    # StartRound2 page so participants aren't burning time while they read
    # the start screen.
    title_text = "Waiting for the others to finish"
    body_text = "Click continue once everyone is ready to start the next discussion."

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 2

    @staticmethod
    def after_all_players_arrive(group: Group):
        for p in group.get_players():
            p.survey_id = p.participant.label or ''


class StartRound2(Page):
    # Interstitial between RejoinWaitPage and round-2 Chat. Gives each
    # participant an explicit "Start" click so they don't land straight in
    # the next discussion with the timer already ticking.
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 2

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        # First player to click Start anchors the shared 5-minute deadline
        # for the round-2 group; later clickers inherit the same clock.
        if player.group.field_maybe_none('chat_start_time') is None:
            player.group.chat_start_time = time.time()


class Results(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == C.NUM_ROUNDS

    @staticmethod
    def vars_for_template(player: Player):
        return dict(survey_id=player.participant.label or '(no id)')


page_sequence = [GroupingWaitPage, RejoinWaitPage, StartRound2, Chat, Results]
