from typing import TYPE_CHECKING

from werewolf.game.errors import GameLimitExceeded
from werewolf.game.events import EventType as E, Visibility as V
from werewolf.game.phases import Phase
from werewolf.game.resolver import plurality, resolve_night
from werewolf.game.win_conditions import check_winner, winning_players
from werewolf.roles import RoleName

if TYPE_CHECKING:
    from werewolf.game.engine import GameEngine


def game_start(engine: "GameEngine") -> None:
    if engine._state.board.roles.get(RoleName.HYBRID, 0) or not end_if_winner(engine):
        engine.transition(Phase.NIGHT_START)


def night_start(engine: "GameEngine") -> None:
    if engine._state.public.day >= engine._state.board.max_days:
        raise GameLimitExceeded("MAX_DAYS exceeded")
    engine.emit(E.NIGHT_STARTED, visibility=V.PUBLIC)
    engine.transition(Phase.HYBRID_CHOOSE if engine._state.public.day == 1
                      and engine._state.board.roles.get(RoleName.HYBRID, 0) else Phase.WOLF)


def hybrid_choose(engine: "GameEngine") -> None:
    if not end_if_winner(engine):
        engine.transition(Phase.WOLF)


def wolf(engine: "GameEngine") -> None:
    engine.resolve_wolf_vote()
    engine.transition(Phase.SEER)


def seer(engine: "GameEngine") -> None:
    engine.transition(Phase.WITCH if engine._state.board.roles.get(RoleName.WITCH, 0) else Phase.NIGHT_RESOLUTION)


def witch(engine: "GameEngine") -> None:
    engine.transition(Phase.NIGHT_RESOLUTION)


def night_resolution(engine: "GameEngine") -> None:
    result = resolve_night(engine._state, engine._state.secret.night)
    for actor, target, team in result.checks:
        engine.emit(E.SEER_CHECKED, actor=actor, target=target,
                    visibility=V.PRIVATE_PLAYER, recipients=(actor,), payload={"result": team})
    for actor, target in result.saves:
        engine.emit(E.WITCH_USED_ANTIDOTE, actor=actor, target=target,
                    visibility=V.PRIVATE_PLAYER, recipients=(actor,))
    for actor, target in result.poisons:
        engine.emit(E.WITCH_USED_POISON, actor=actor, target=target,
                    visibility=V.PRIVATE_PLAYER, recipients=(actor,))
    engine.emit(E.NIGHT_RESOLVED, payload={"deaths": result.deaths, "causes": result.causes})
    engine.transition(Phase.DAWN)


def dawn(engine: "GameEngine") -> None:
    for target in engine._state.secret.night_deaths:
        engine.kill(target, engine._state.secret.night_causes.get(target, ["wolf_kill"]))
    engine.emit(E.DAY_STARTED, visibility=V.PUBLIC,
                payload={"deaths": engine._state.secret.night_deaths})
    schedule_death_skills(engine, Phase.NIGHT_WIN_CHECK)


def schedule_death_skills(engine: "GameEngine", resume: Phase) -> None:
    if engine._state.secret.death_skill_queue:
        engine.emit(E.DEATH_SKILLS_STARTED, payload={"resume": resume})
        engine.transition(Phase.DEATH_SKILL)
    else:
        engine.transition(resume)


def death_skill(engine: "GameEngine") -> None:
    engine.transition(engine._state.secret.death_skill_resume)


def end_if_winner(engine: "GameEngine") -> bool:
    winner = check_winner(engine._state)
    if winner is not None:
        engine.emit(E.WINNERS_DETERMINED, payload={"seats": winning_players(engine._state, winner)})
        engine.emit(E.GAME_ENDED, visibility=V.PUBLIC, payload={"winner": winner})
        engine.transition(Phase.ENDED)
        return True
    return False


def win_check(engine: "GameEngine") -> None:
    if not end_if_winner(engine):
        phase = Phase.DISCUSSION if engine._state.public.phase == Phase.NIGHT_WIN_CHECK else Phase.NIGHT_START
        engine.transition(phase)


def discussion(engine: "GameEngine") -> None:
    engine.transition(Phase.VOTING)


def voting(engine: "GameEngine") -> None:
    engine.transition(Phase.EXILE_RESOLUTION)


def exile_resolution(engine: "GameEngine") -> None:
    target = plurality(engine._state.public.votes, engine.rng,
                       random_tie=engine._state.board.vote_tie == "seeded_random")
    if target is None:
        engine.emit(E.EXILE_SKIPPED, visibility=V.PUBLIC, payload={"reason": "tie_or_abstention"})
    else:
        engine.emit(E.PLAYER_EXILED, target=target, visibility=V.PUBLIC)
        player = engine._state.public.players[target]
        if engine._state.secret.roles[target] == RoleName.IDIOT and player.revealed_role is None:
            engine.emit(E.IDIOT_REVEALED, target=target, visibility=V.PUBLIC)
        else:
            engine.kill(target, ["exile"])
    schedule_death_skills(engine, Phase.DAY_WIN_CHECK)


HANDLERS = {
    Phase.GAME_START: game_start, Phase.NIGHT_START: night_start,
    Phase.WOLF: wolf, Phase.SEER: seer, Phase.WITCH: witch, Phase.NIGHT_RESOLUTION: night_resolution,
    Phase.DAWN: dawn, Phase.NIGHT_WIN_CHECK: win_check,
    Phase.DISCUSSION: discussion, Phase.VOTING: voting,
    Phase.EXILE_RESOLUTION: exile_resolution, Phase.DAY_WIN_CHECK: win_check,
    Phase.DEATH_SKILL: death_skill,
    Phase.HYBRID_CHOOSE: hybrid_choose,
}
