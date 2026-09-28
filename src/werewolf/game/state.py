from dataclasses import dataclass, field

from werewolf.config import BoardConfig, PlayerConfig
from werewolf.game.phases import Phase
from werewolf.roles import RoleName, Team


@dataclass
class PublicPlayer:
    seat: int
    name: str
    alive: bool = True
    can_vote: bool = True
    revealed_role: RoleName | None = None


@dataclass
class PublicState:
    day: int = 0
    phase: Phase = Phase.GAME_START
    players: dict[int, PublicPlayer] = field(default_factory=dict)
    dead: set[int] = field(default_factory=set)
    speeches: list[dict] = field(default_factory=list)
    votes: dict[int, int | None] = field(default_factory=dict)
    winner: Team | None = None

    @property
    def alive(self) -> tuple[int, ...]:
        return tuple(seat for seat, player in sorted(self.players.items()) if player.alive)


@dataclass
class NightActions:
    wolf_votes: dict[int, int] = field(default_factory=dict)
    wolf_target: int | None = None
    seer_checks: dict[int, int] = field(default_factory=dict)
    witch_actions: dict[int, dict] = field(default_factory=dict)


@dataclass
class Potions:
    antidote: int = 1
    poison: int = 1


@dataclass
class SecretState:
    roles: dict[int, RoleName] = field(default_factory=dict)
    night: NightActions = field(default_factory=NightActions)
    check_history: dict[int, list[dict]] = field(default_factory=dict)
    night_deaths: list[int] = field(default_factory=list)
    night_causes: dict[int, list[str]] = field(default_factory=dict)
    potions: dict[int, Potions] = field(default_factory=dict)
    death_causes: dict[int, list[str]] = field(default_factory=dict)
    hunter_spent: set[int] = field(default_factory=set)
    death_skill_queue: list[int] = field(default_factory=list)
    death_skill_resume: Phase | None = None
    hybrid_models: dict[int, int] = field(default_factory=dict)
    hybrid_teams: dict[int, Team] = field(default_factory=dict)
    winning_players: list[int] = field(default_factory=list)


@dataclass
class GameState:
    board: BoardConfig
    profiles: tuple[PlayerConfig, ...]
    seed: int
    public: PublicState = field(default_factory=PublicState)
    secret: SecretState = field(default_factory=SecretState)
    submitted: set[int] = field(default_factory=set)
    event_count: int = 0
