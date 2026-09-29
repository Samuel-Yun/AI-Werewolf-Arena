from collections import Counter
from typing import TYPE_CHECKING

from werewolf.game.errors import GameLimitExceeded
from werewolf.game.events import EventType as E, Visibility as V
from werewolf.game.phases import Phase
from werewolf.game.resolver import plurality, resolve_night
from werewolf.game.rules import candidates, police_down
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
    if engine._state.public.day == 1 and engine._state.board.roles.get(RoleName.HYBRID, 0):
        phase = Phase.HYBRID_CHOOSE
    else:
        phase = Phase.WOLF_CHAT if engine._state.board.wolf_chat.enabled else Phase.WOLF
    engine.transition(phase)


def hybrid_choose(engine: "GameEngine") -> None:
    if not end_if_winner(engine):
        engine.transition(Phase.WOLF_CHAT if engine._state.board.wolf_chat.enabled else Phase.WOLF)


def wolf_chat(engine: "GameEngine") -> None:
    if engine._state.secret.wolf_chat_round < engine._state.board.wolf_chat.rounds:
        engine.emit(E.WOLF_CHAT_ROUND_ENDED, payload={"round": engine._state.secret.wolf_chat_round})
    else:
        engine.transition(Phase.WOLF)


def wolf(engine: "GameEngine") -> None:
    engine.resolve_wolf_vote()
    engine.transition(Phase.SEER)


def seer(engine: "GameEngine") -> None:
    if engine._state.board.roles.get(RoleName.WITCH, 0):
        engine.transition(Phase.WITCH)
        for seat in engine._state.public.alive:
            if engine._state.secret.roles[seat] == RoleName.WITCH:
                potion = engine._state.secret.potions[seat]
                visible = engine._state.secret.night.wolf_target if (
                    potion.antidote or engine._state.board.witch.see_victim_without_antidote) else None
                engine.emit(E.WITCH_WINDOW_OPENED, actor=seat, target=visible,
                            payload={"antidote": potion.antidote, "poison": potion.poison})
    else:
        engine.transition(Phase.NIGHT_RESOLUTION)


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
    if engine._state.secret.death_skill_queue or engine._state.secret.badge_transfer_pending is not None:
        engine.emit(E.DEATH_SKILLS_STARTED, payload={"resume": resume})
        engine.transition(Phase.DEATH_SKILL if engine._state.secret.death_skill_queue else Phase.BADGE_TRANSFER)
    else:
        engine.transition(resume)


def death_skill(engine: "GameEngine") -> None:
    if engine._state.secret.badge_transfer_pending is not None:
        engine.transition(Phase.BADGE_TRANSFER)
    else:
        engine.transition(engine._state.secret.death_skill_resume)


def badge_transfer(engine: "GameEngine") -> None:
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
    if end_if_winner(engine):
        return
    if engine._state.public.phase == Phase.DAY_WIN_CHECK:
        engine.transition(Phase.NIGHT_START)
    elif engine._state.public.day == 1 and engine._state.board.sheriff.enabled:
        engine.transition(Phase.SHERIFF_SIGNUP)
    else:
        begin_discussion(engine)


def begin_discussion(engine: "GameEngine") -> None:
    sheriff = engine._state.public.sheriff
    engine.transition(Phase.SPEECH_ORDER if sheriff is not None and sheriff in engine._state.public.alive
                      else Phase.DISCUSSION)


def sheriff_signup(engine: "GameEngine") -> None:
    seats = candidates(engine._state)
    if len(seats) > 1:
        engine.transition(Phase.SHERIFF_SPEECH)
    else:
        engine.emit(E.SHERIFF_ELECTED, target=seats[0] if seats else None, visibility=V.PUBLIC,
                    payload={"reason": "sole_candidate" if seats else "no_candidates"})
        begin_discussion(engine)


def sheriff_speech(engine: "GameEngine") -> None:
    engine.transition(Phase.SHERIFF_WITHDRAW)


def sheriff_withdraw(engine: "GameEngine") -> None:
    seats = candidates(engine._state)
    if len(seats) > 1 and police_down(engine._state):
        engine.transition(Phase.SHERIFF_VOTE)
    else:
        engine.emit(E.SHERIFF_ELECTED, target=seats[0] if len(seats) == 1 else None,
                    visibility=V.PUBLIC, payload={"reason": "withdrawal" if len(seats) == 1 else "no_election"})
        begin_discussion(engine)


def decide_sheriff_vote(engine: "GameEngine", *, pk: bool) -> None:
    engine.emit(E.SHERIFF_BALLOTS_REVEALED, visibility=V.PUBLIC,
                payload={"ballots": engine._state.secret.pending_sheriff_ballots})
    ballots = engine._state.public.sheriff_ballots
    counts = Counter(target for target in ballots.values() if target is not None)
    leaders = tuple(sorted(s for s, n in counts.items() if n == max(counts.values()))) if counts else ()
    if len(leaders) == 1:
        engine.emit(E.SHERIFF_ELECTED, target=leaders[0], visibility=V.PUBLIC,
                    payload={"reason": "ballot", "tally": dict(counts)})
        begin_discussion(engine)
    elif len(leaders) > 1 and engine._state.public.sheriff_pk_round < engine._state.board.sheriff.pk_rounds:
        engine.emit(E.SHERIFF_PK_STARTED, visibility=V.PUBLIC, payload={"candidates": leaders,
                    "tally": dict(counts)})
        engine.transition(Phase.SHERIFF_PK_SPEECH)
    else:
        engine.emit(E.SHERIFF_ELECTED, visibility=V.PUBLIC,
                    payload={"reason": "tie_or_abstention", "tally": dict(counts)})
        begin_discussion(engine)


def sheriff_vote(engine: "GameEngine") -> None:
    decide_sheriff_vote(engine, pk=False)


def sheriff_pk_speech(engine: "GameEngine") -> None:
    engine.transition(Phase.SHERIFF_PK_VOTE)


def sheriff_pk_vote(engine: "GameEngine") -> None:
    decide_sheriff_vote(engine, pk=True)


def speech_order(engine: "GameEngine") -> None:
    engine.transition(Phase.DISCUSSION)


def discussion(engine: "GameEngine") -> None:
    engine.transition(Phase.VOTING)


def voting(engine: "GameEngine") -> None:
    engine.emit(E.VOTES_REVEALED, visibility=V.PUBLIC,
                payload={"votes": engine._state.secret.pending_votes})
    engine.transition(Phase.EXILE_RESOLUTION)


def exile_resolution(engine: "GameEngine") -> None:
    state = engine._state
    weights = {seat: 3 if seat == state.public.sheriff else 2 for seat in state.public.votes}
    totals = Counter()
    for seat, target in state.public.votes.items():
        if target is not None:
            totals[target] += weights[seat]
    leaders = sorted(s for s, n in totals.items() if n == max(totals.values())) if totals else []
    target = (leaders[0] if len(leaders) == 1 else
              engine.rng.choice(leaders) if leaders and state.board.vote_tie == "seeded_random" else None)
    engine.emit(E.EXILE_TALLY, visibility=V.PUBLIC,
                payload={"weights": weights, "totals": dict(totals), "target": target})
    if target is None:
        engine.emit(E.EXILE_SKIPPED, visibility=V.PUBLIC, payload={"reason": "tie_or_abstention"})
    else:
        engine.emit(E.PLAYER_EXILED, target=target, visibility=V.PUBLIC)
        player = state.public.players[target]
        if state.secret.roles[target] == RoleName.IDIOT and player.revealed_role is None:
            engine.emit(E.IDIOT_REVEALED, target=target, visibility=V.PUBLIC)
        else:
            engine.kill(target, ["exile"])
    schedule_death_skills(engine, Phase.DAY_WIN_CHECK)


HANDLERS = {
    Phase.GAME_START: game_start, Phase.NIGHT_START: night_start,
    Phase.HYBRID_CHOOSE: hybrid_choose, Phase.WOLF_CHAT: wolf_chat,
    Phase.WOLF: wolf, Phase.SEER: seer, Phase.WITCH: witch, Phase.NIGHT_RESOLUTION: night_resolution,
    Phase.DAWN: dawn, Phase.NIGHT_WIN_CHECK: win_check,
    Phase.SHERIFF_SIGNUP: sheriff_signup, Phase.SHERIFF_SPEECH: sheriff_speech,
    Phase.SHERIFF_WITHDRAW: sheriff_withdraw, Phase.SHERIFF_VOTE: sheriff_vote,
    Phase.SHERIFF_PK_SPEECH: sheriff_pk_speech, Phase.SHERIFF_PK_VOTE: sheriff_pk_vote,
    Phase.SPEECH_ORDER: speech_order,
    Phase.DISCUSSION: discussion, Phase.VOTING: voting,
    Phase.EXILE_RESOLUTION: exile_resolution, Phase.DAY_WIN_CHECK: win_check,
    Phase.DEATH_SKILL: death_skill, Phase.BADGE_TRANSFER: badge_transfer,
}
