from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from werewolf.game.phases import Phase


class Visibility(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE_PLAYER = "PRIVATE_PLAYER"
    PRIVATE_WOLVES = "PRIVATE_WOLVES"
    ENGINE_ONLY = "ENGINE_ONLY"


class EventType(StrEnum):
    GAME_STARTED = "GameStarted"
    PHASE_CHANGED = "PhaseChanged"
    NIGHT_STARTED = "NightStarted"
    WOLF_CHAT_MESSAGE = "WolfChatMessage"
    WOLF_CHAT_ROUND_ENDED = "WolfChatRoundEnded"
    WITCH_WINDOW_OPENED = "WitchWindowOpened"
    SHERIFF_SIGNUP = "SheriffSignup"
    SHERIFF_WITHDREW = "SheriffWithdrew"
    SHERIFF_BALLOT = "SheriffBallot"
    SHERIFF_BALLOTS_REVEALED = "SheriffBallotsRevealed"
    SHERIFF_ELECTED = "SheriffElected"
    SHERIFF_PK_STARTED = "SheriffPkStarted"
    SPEECH_ORDER_CHOSEN = "SpeechOrderChosen"
    BADGE_TRANSFERRED = "BadgeTransferred"
    WOLF_VOTE_SUBMITTED = "WolfVoteSubmitted"
    WOLF_KILL_SELECTED = "WolfKillSelected"
    SEER_CHECK_SELECTED = "SeerCheckSelected"
    SEER_CHECKED = "SeerChecked"
    WITCH_ACTION_SELECTED = "WitchActionSelected"
    WITCH_USED_ANTIDOTE = "WitchUsedAntidote"
    WITCH_USED_POISON = "WitchUsedPoison"
    DEATH_CAUSE_RECORDED = "DeathCauseRecorded"
    HUNTER_TRIGGERED = "HunterTriggered"
    DEATH_SKILLS_STARTED = "DeathSkillsStarted"
    HUNTER_SHOT = "HunterShot"
    IDIOT_REVEALED = "IdiotRevealed"
    HYBRID_MODEL_CHOSEN = "HybridModelChosen"
    WINNERS_DETERMINED = "WinnersDetermined"
    NIGHT_RESOLVED = "NightResolved"
    DAY_STARTED = "DayStarted"
    PLAYER_SPOKE = "PlayerSpoke"
    PLAYER_SKIPPED = "PlayerSkipped"
    DIRECTOR_DECISION = "DirectorDecision"
    VOTE_SUBMITTED = "VoteSubmitted"
    VOTES_REVEALED = "VotesRevealed"
    EXILE_TALLY = "ExileTally"
    PLAYER_EXILED = "PlayerExiled"
    PLAYER_DIED = "PlayerDied"
    EXILE_SKIPPED = "ExileSkipped"
    GAME_ENDED = "GameEnded"
    ACTION_REJECTED = "ActionRejected"
    FALLBACK_USED = "FallbackUsed"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: int = 1
    event_id: int = Field(ge=1)
    game_id: str
    day: int = Field(ge=0)
    phase: Phase
    event_type: EventType
    actor: StrictInt | None = None
    target: StrictInt | None = None
    visibility: Visibility = Visibility.ENGINE_ONLY
    recipients: tuple[int, ...] = ()
    payload: dict = Field(default_factory=dict)
    timestamp: datetime

    @model_validator(mode="after")
    def check_visibility(self) -> "Event":
        if self.schema_version != 1:
            raise ValueError("Unsupported event schema version")
        if self.visibility == Visibility.PRIVATE_PLAYER and not self.recipients:
            raise ValueError("Private player events need recipients")
        if self.visibility != Visibility.PRIVATE_PLAYER and self.recipients:
            raise ValueError("Recipients are only valid for private player events")
        return self
