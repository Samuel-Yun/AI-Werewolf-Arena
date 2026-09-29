from enum import StrEnum


class Phase(StrEnum):
    GAME_START = "game_start"
    NIGHT_START = "night_start"
    HYBRID_CHOOSE = "hybrid_choose"
    WOLF_CHAT = "wolf_chat"
    WOLF = "wolf"
    SEER = "seer"
    WITCH = "witch"
    NIGHT_RESOLUTION = "night_resolution"
    DAWN = "dawn"
    NIGHT_WIN_CHECK = "night_win_check"
    SHERIFF_SIGNUP = "sheriff_signup"
    SHERIFF_SPEECH = "sheriff_speech"
    SHERIFF_WITHDRAW = "sheriff_withdraw"
    SHERIFF_VOTE = "sheriff_vote"
    SHERIFF_PK_SPEECH = "sheriff_pk_speech"
    SHERIFF_PK_VOTE = "sheriff_pk_vote"
    SPEECH_ORDER = "speech_order"
    DISCUSSION = "discussion"
    VOTING = "voting"
    EXILE_RESOLUTION = "exile_resolution"
    DEATH_SKILL = "death_skill"
    BADGE_TRANSFER = "badge_transfer"
    DAY_WIN_CHECK = "day_win_check"
    ENDED = "ended"


TRANSITIONS = {
    Phase.GAME_START: {Phase.NIGHT_START, Phase.ENDED},
    Phase.NIGHT_START: {Phase.WOLF, Phase.HYBRID_CHOOSE, Phase.WOLF_CHAT},
    Phase.HYBRID_CHOOSE: {Phase.WOLF, Phase.WOLF_CHAT, Phase.ENDED},
    Phase.WOLF_CHAT: {Phase.WOLF},
    Phase.WOLF: {Phase.SEER},
    Phase.SEER: {Phase.WITCH, Phase.NIGHT_RESOLUTION},
    Phase.WITCH: {Phase.NIGHT_RESOLUTION},
    Phase.NIGHT_RESOLUTION: {Phase.DAWN},
    Phase.DAWN: {Phase.NIGHT_WIN_CHECK, Phase.DEATH_SKILL, Phase.BADGE_TRANSFER},
    Phase.NIGHT_WIN_CHECK: {Phase.DISCUSSION, Phase.SHERIFF_SIGNUP, Phase.SPEECH_ORDER, Phase.ENDED},
    Phase.SHERIFF_SIGNUP: {Phase.SHERIFF_SPEECH, Phase.DISCUSSION, Phase.SPEECH_ORDER},
    Phase.SHERIFF_SPEECH: {Phase.SHERIFF_WITHDRAW},
    Phase.SHERIFF_WITHDRAW: {Phase.SHERIFF_VOTE, Phase.DISCUSSION, Phase.SPEECH_ORDER},
    Phase.SHERIFF_VOTE: {Phase.SHERIFF_PK_SPEECH, Phase.DISCUSSION, Phase.SPEECH_ORDER},
    Phase.SHERIFF_PK_SPEECH: {Phase.SHERIFF_PK_VOTE},
    Phase.SHERIFF_PK_VOTE: {Phase.DISCUSSION, Phase.SPEECH_ORDER},
    Phase.SPEECH_ORDER: {Phase.DISCUSSION},
    Phase.DISCUSSION: {Phase.VOTING},
    Phase.VOTING: {Phase.EXILE_RESOLUTION},
    Phase.EXILE_RESOLUTION: {Phase.DAY_WIN_CHECK, Phase.DEATH_SKILL, Phase.BADGE_TRANSFER},
    Phase.DEATH_SKILL: {Phase.DAY_WIN_CHECK, Phase.NIGHT_WIN_CHECK, Phase.BADGE_TRANSFER},
    Phase.BADGE_TRANSFER: {Phase.DAY_WIN_CHECK, Phase.NIGHT_WIN_CHECK},
    Phase.DAY_WIN_CHECK: {Phase.NIGHT_START, Phase.ENDED},
    Phase.ENDED: set(),
}
