from dataclasses import asdict, dataclass, field
from pathlib import Path

from werewolf.config import BoardConfig, PlayerConfig
from werewolf.game.engine import GameEngine
from werewolf.game.errors import GameLimitExceeded, InvariantViolation
from werewolf.runner import AutoRunner
from werewolf.storage.game_store import GameStore


@dataclass
class SimulationStats:
    games: int
    completed_games: int = 0
    crashed_games: int = 0
    invariant_violations: int = 0
    average_turns: float = 0
    good_wins: int = 0
    wolf_wins: int = 0
    special_wins: int = 0
    hybrid_wins: int = 0
    max_turns: int = 0
    deadlocks: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.completed_games == self.games and not self.failures

    def to_dict(self) -> dict:
        return asdict(self)


def simulate(board: BoardConfig, players: tuple[PlayerConfig, ...], *, games: int,
             seed: int, failure_root: Path) -> SimulationStats:
    if games < 1:
        raise ValueError("games must be positive")
    stats = SimulationStats(games)
    total_turns = 0
    for offset in range(games):
        game_seed = seed + offset
        engine = None
        try:
            engine = GameEngine(board, game_seed, players)
            AutoRunner(engine).run()
        except Exception as exc:
            if isinstance(exc, GameLimitExceeded):
                stats.deadlocks += 1
            elif isinstance(exc, InvariantViolation):
                stats.invariant_violations += 1
            else:
                stats.crashed_games += 1
            failure = {"seed": game_seed, "type": type(exc).__name__, "reason": str(exc)}
            if engine is not None:
                failure["path"] = str(GameStore(failure_root).save(engine, diagnostic=failure))
            stats.failures.append(failure)
            continue
        state = engine.state
        stats.completed_games += 1
        total_turns += state.public.day
        stats.max_turns = max(stats.max_turns, state.public.day)
        stats.hybrid_wins += sum(state.secret.roles[s] == "hybrid" for s in state.secret.winning_players)
        if state.public.winner == "good":
            stats.good_wins += 1
        elif state.public.winner == "wolf":
            stats.wolf_wins += 1
        else:
            stats.special_wins += 1
    stats.average_turns = round(total_turns / stats.completed_games, 3) if stats.completed_games else 0
    return stats
