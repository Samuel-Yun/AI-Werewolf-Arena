from enum import StrEnum


class Phase(StrEnum):
    GAME_START = "game_start"
    NIGHT_START = "night_start"
    HYBRID_CHOOSE = "hybrid_choose"
    WOLF = "wolf"
    SEER = "seer"
    WITCH = "witch"
    NIGHT_RESOLUTION = "night_resolution"
    DAWN = "dawn"
    NIGHT_WIN_CHECK = "night_win_check"
    DISCUSSION = "discussion"
    VOTING = "voting"
    EXILE_RESOLUTION = "exile_resolution"
    DEATH_SKILL = "death_skill"
    DAY_WIN_CHECK = "day_win_check"
    ENDED = "ended"


TRANSITIONS = {
    Phase.GAME_START: {Phase.NIGHT_START, Phase.ENDED},
    Phase.NIGHT_START: {Phase.WOLF, Phase.HYBRID_CHOOSE},
    Phase.HYBRID_CHOOSE: {Phase.WOLF, Phase.ENDED},
    Phase.WOLF: {Phase.SEER},
    Phase.SEER: {Phase.WITCH, Phase.NIGHT_RESOLUTION},
    Phase.WITCH: {Phase.NIGHT_RESOLUTION},
    Phase.NIGHT_RESOLUTION: {Phase.DAWN},
    Phase.DAWN: {Phase.NIGHT_WIN_CHECK, Phase.DEATH_SKILL},
    Phase.NIGHT_WIN_CHECK: {Phase.DISCUSSION, Phase.ENDED},
    Phase.DISCUSSION: {Phase.VOTING},
    Phase.VOTING: {Phase.EXILE_RESOLUTION},
    Phase.EXILE_RESOLUTION: {Phase.DAY_WIN_CHECK, Phase.DEATH_SKILL},
    Phase.DEATH_SKILL: {Phase.DAY_WIN_CHECK, Phase.NIGHT_WIN_CHECK},
    Phase.DAY_WIN_CHECK: {Phase.NIGHT_START, Phase.ENDED},
    Phase.ENDED: set(),
}
