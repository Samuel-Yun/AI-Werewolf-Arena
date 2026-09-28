from dataclasses import dataclass
from enum import StrEnum


class Team(StrEnum):
    GOOD = "good"
    WOLF = "wolf"


class RoleName(StrEnum):
    WEREWOLF = "werewolf"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    IDIOT = "idiot"
    HYBRID = "hybrid"
    VILLAGER = "villager"


@dataclass(frozen=True)
class Role:
    name: RoleName
    team: Team
    night_action: str | None = None
    death_action: str | None = None
    survives_first_exile: bool = False


ROLES = {
    RoleName.WEREWOLF: Role(RoleName.WEREWOLF, Team.WOLF, "wolf_kill"),
    RoleName.SEER: Role(RoleName.SEER, Team.GOOD, "seer_check"),
    RoleName.WITCH: Role(RoleName.WITCH, Team.GOOD, "witch"),
    RoleName.HUNTER: Role(RoleName.HUNTER, Team.GOOD, death_action="hunter_shot"),
    RoleName.IDIOT: Role(RoleName.IDIOT, Team.GOOD, survives_first_exile=True),
    RoleName.HYBRID: Role(RoleName.HYBRID, Team.GOOD, "hybrid_choose"),
    RoleName.VILLAGER: Role(RoleName.VILLAGER, Team.GOOD),
}
