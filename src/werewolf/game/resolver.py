from collections import Counter
from dataclasses import dataclass
from random import Random

from werewolf.game.state import GameState, NightActions
from werewolf.roles import RoleName, Team


def plurality(votes: dict[int, int | None], rng: Random, *, random_tie: bool) -> int | None:
    counts = Counter(target for target in votes.values() if target is not None)
    if not counts:
        return None
    leaders = sorted(target for target, count in counts.items() if count == max(counts.values()))
    if len(leaders) == 1:
        return leaders[0]
    return rng.choice(leaders) if random_tie else None


@dataclass(frozen=True)
class NightResult:
    deaths: tuple[int, ...]
    checks: tuple[tuple[int, int, Team], ...]
    saves: tuple[tuple[int, int], ...]
    poisons: tuple[tuple[int, int], ...]
    causes: dict[int, list[str]]


def resolve_night(state: GameState, actions: NightActions) -> NightResult:
    """Compute all night effects without mutating the world."""
    checks = tuple(
        (actor, target, state.board.hybrid.seer_result if state.secret.roles[target] == RoleName.HYBRID
         else Team.WOLF if state.secret.roles[target] == RoleName.WEREWOLF else Team.GOOD)
        for actor, target in sorted(actions.seer_checks.items())
    )
    saves = tuple((actor, a["save_target"]) for actor, a in sorted(actions.witch_actions.items())
                  if a["save_target"] is not None)
    poisons = tuple((actor, a["poison_target"]) for actor, a in sorted(actions.witch_actions.items())
                    if a["poison_target"] is not None)
    causes: dict[int, list[str]] = {}
    if actions.wolf_target is not None and not any(t == actions.wolf_target for _, t in saves):
        causes[actions.wolf_target] = ["wolf_kill"]
    for _, target in poisons:
        causes.setdefault(target, []).append("poison")
    return NightResult(tuple(sorted(causes)), checks, saves, poisons, causes)
