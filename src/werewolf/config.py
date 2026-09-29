from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from werewolf.roles import RoleName, Team


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    archetype: str = "neutral"
    traits: tuple[str, ...] = ()
    speaking_style: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()


class PlayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seat: int = Field(ge=1)
    name: str = Field(min_length=1)
    provider: str = "mock"
    model: str = "mock"
    persona: Persona = Field(default_factory=Persona)


class WitchRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    self_save: Literal["never", "first_night", "always"] = "first_night"
    allow_both_potions: bool = False
    see_victim_without_antidote: bool = False


class HunterRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    allowed_causes: tuple[Literal["wolf_kill", "poison", "exile", "hunter_shot"], ...] = (
        "wolf_kill", "exile", "hunter_shot",
    )
    blocked_causes: tuple[Literal["wolf_kill", "poison", "exile", "hunter_shot"], ...] = ("poison",)


class IdiotRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    exile_after_reveal: Literal["immune", "dies"] = "immune"


class HybridRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alignment: Literal["follow_model", "good", "wolf"] = "follow_model"
    victory: Literal["aligned_team", "model_team", "survive"] = "aligned_team"
    counts_for_win: bool = False
    seer_result: Team = Team.GOOD
    reveal_alignment: bool = False


class SheriffRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    pk_rounds: int = Field(default=1, ge=0, le=2)


class WolfChatRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    rounds: int = Field(default=2, ge=1, le=3)


class BoardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1)
    players: int = Field(ge=3)
    roles: dict[RoleName, int]
    witch: WitchRules = Field(default_factory=WitchRules)
    hunter: HunterRules = Field(default_factory=HunterRules)
    idiot: IdiotRules = Field(default_factory=IdiotRules)
    hybrid: HybridRules = Field(default_factory=HybridRules)
    sheriff: SheriffRules = Field(default_factory=SheriffRules)
    wolf_chat: WolfChatRules = Field(default_factory=WolfChatRules)
    wolf_win: Literal["parity", "eliminate_good", "slaughter"] = "parity"
    simultaneous_elimination: Team = Team.GOOD
    vote_tie: Literal["no_exile", "seeded_random"] = "no_exile"
    max_days: int = Field(default=100, ge=1)
    max_events: int = Field(default=20000, ge=1)
    max_retries_per_action: int = Field(default=1, ge=0, le=5)

    @model_validator(mode="after")
    def check_board(self) -> "BoardConfig":
        if any(count < 0 for count in self.roles.values()):
            raise ValueError("Role counts cannot be negative")
        if sum(self.roles.values()) != self.players:
            raise ValueError("Role counts must equal players")
        wolves = self.roles.get(RoleName.WEREWOLF, 0)
        if not 0 < wolves < self.players:
            raise ValueError("A board needs both wolves and good players")
        if self.roles.get(RoleName.SEER, 0) > 1:
            raise ValueError("This board supports at most one seer")
        if self.roles.get(RoleName.WITCH, 0) > 1:
            raise ValueError("This board supports at most one witch")
        if self.roles.get(RoleName.HYBRID, 0) > 1:
            raise ValueError("This board supports at most one hybrid")
        if self.roles.get(RoleName.HYBRID, 0) and self.hybrid.counts_for_win and self.wolf_win == "eliminate_good":
            raise ValueError("A non-attacking hybrid cannot participate in eliminate_good victory counts")
        if self.wolf_win == "slaughter" and (self.players != 12 or wolves != 4 or
                any(self.roles.get(role, 0) != 1 for role in (RoleName.SEER, RoleName.WITCH, RoleName.HUNTER, RoleName.IDIOT)) or
                self.roles.get(RoleName.VILLAGER, 0) != 3 or self.roles.get(RoleName.HYBRID, 0) != 1):
            raise ValueError("Slaughter board requires 4 wolves, 4 gods, 3 villagers and 1 hybrid")
        if self.wolf_win == "slaughter" and self.hybrid != HybridRules():
            raise ValueError("Slaughter board requires hidden follow-model hybrid with good seer result")
        return self


def load_board(path: Path) -> BoardConfig:
    return BoardConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_players(path: Path, count: int) -> tuple[PlayerConfig, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    players = tuple(PlayerConfig.model_validate(item) for item in data["players"])
    if sorted(p.seat for p in players) != list(range(1, count + 1)):
        raise ValueError("Player seats must be unique and cover 1..board.players")
    return tuple(sorted(players, key=lambda player: player.seat))


def default_players(count: int) -> tuple[PlayerConfig, ...]:
    names = ("ChatGPT", "DeepSeek", "Claude", "Gemini", "Doubao", "Qwen", "Kimi", "Grok")
    return tuple(PlayerConfig(seat=i, name=names[i - 1] if i <= 8 else f"Mock-{i}")
                 for i in range(1, count + 1))
