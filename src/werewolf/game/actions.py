from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, TypeAdapter, field_validator


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WolfChatAction(ActionModel):
    action: Literal["wolf_chat"] = "wolf_chat"
    text: str = Field(min_length=1, max_length=500, strict=True)
    target: StrictInt | None = None


class SheriffSignupAction(ActionModel):
    action: Literal["sheriff_signup"] = "sheriff_signup"
    run: bool


class SheriffWithdrawAction(ActionModel):
    action: Literal["sheriff_withdraw"] = "sheriff_withdraw"
    withdraw: bool


class SheriffVoteAction(ActionModel):
    action: Literal["sheriff_vote"] = "sheriff_vote"
    target: StrictInt | None


class SpeechOrderAction(ActionModel):
    action: Literal["speech_order"] = "speech_order"
    start: StrictInt
    direction: Literal["clockwise", "counterclockwise"]


class BadgeTransferAction(ActionModel):
    action: Literal["badge_transfer"] = "badge_transfer"
    target: StrictInt | None


class WolfKillAction(ActionModel):
    action: Literal["wolf_kill"] = "wolf_kill"
    target: StrictInt


class SeerCheckAction(ActionModel):
    action: Literal["seer_check"] = "seer_check"
    target: StrictInt


class WitchAction(ActionModel):
    action: Literal["witch"] = "witch"
    save_target: StrictInt | None = None
    poison_target: StrictInt | None = None


class HunterShotAction(ActionModel):
    action: Literal["hunter_shot"] = "hunter_shot"
    target: StrictInt | None


class HybridChooseAction(ActionModel):
    action: Literal["hybrid_choose"] = "hybrid_choose"
    target: StrictInt


class VoteAction(ActionModel):
    action: Literal["vote"] = "vote"
    target: StrictInt | None


class SpeechAction(ActionModel):
    action: Literal["speech"] = "speech"
    text: str = Field(min_length=1, max_length=4000, strict=True)

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Speech cannot be blank")
        return value


class SkipSpeechAction(ActionModel):
    action: Literal["skip_speech"] = "skip_speech"


Action = Annotated[
    WolfChatAction | SheriffSignupAction | SheriffWithdrawAction | SheriffVoteAction | SpeechOrderAction | BadgeTransferAction | WolfKillAction | SeerCheckAction | WitchAction | HunterShotAction | HybridChooseAction | VoteAction | SpeechAction | SkipSpeechAction,
    Field(discriminator="action"),
]
ACTION_ADAPTER = TypeAdapter(Action)


def parse_action(raw: object) -> Action:
    """Re-validate even model objects: providers are an untrusted boundary."""
    if isinstance(raw, BaseModel):
        raw = raw.model_dump()
    if isinstance(raw, (str, bytes)):
        return ACTION_ADAPTER.validate_json(raw)
    return ACTION_ADAPTER.validate_python(raw)
