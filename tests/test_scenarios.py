from random import Random

import pytest

from conftest import begin_night, finish_day, play_night
from werewolf.game.errors import GameLimitExceeded, InvariantViolation
from werewolf.game.phases import Phase
from werewolf.game.resolver import plurality
from werewolf.game.validation import validate_game_state
from werewolf.game.win_conditions import check_winner
from werewolf.roles import Team
from werewolf.runner import AutoRunner


def test_pending_night_actions_and_seer_result(engine):
    begin_night(engine)
    for seat in (1, 2, 3, 4):
        engine.submit(seat, {"action": "wolf_kill", "target": 6})
    assert engine.state.public.players[6].alive
    engine.advance()
    engine.submit(5, {"action": "seer_check", "target": 1})
    assert engine.state.secret.check_history == {}
    engine.advance()
    assert engine.state.public.phase == Phase.NIGHT_RESOLUTION
    assert engine.state.public.players[6].alive
    engine.advance()
    assert engine.state.secret.check_history[5] == [{"day": 1, "target": 1, "result": "wolf"}]
    engine.advance()
    assert 6 in engine.state.public.dead


def test_seer_acts_before_simultaneous_death(engine):
    play_night(engine, kill=5, check=1)
    assert not engine.state.public.players[5].alive
    assert engine.state.secret.check_history[5][0]["result"] == "wolf"


def test_day_exile_then_next_night(engine):
    play_night(engine)
    assert engine.state.public.phase == Phase.DISCUSSION
    finish_day(engine, exile=1)
    assert 1 in engine.state.public.dead
    engine.advance()
    assert engine.state.public.phase == Phase.NIGHT_START
    engine.advance()
    assert engine.state.public.day == 2
    assert not engine.state.public.votes
    assert not engine.state.secret.night.wolf_votes


def test_day_vote_tie_has_no_exile(engine):
    play_night(engine)
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "speech", "text": "过。"})
    engine.advance()
    eligible = engine.state.public.alive
    for seat in eligible:
        target = 7 if seat <= 5 else None if seat == 8 else 8
        engine.submit(seat, {"action": "vote", "target": target})
    # Five votes for each target; seat 8 abstains.
    engine.advance()
    before = engine.state.public.alive
    engine.advance()
    assert engine.state.public.alive == before


def test_plurality_policy():
    votes = {1: 5, 2: 7, 3: None}
    assert plurality(votes, Random(123), random_tie=False) is None
    assert plurality(votes, Random(123), random_tie=True) == plurality(votes, Random(123), random_tie=True)


@pytest.mark.parametrize("alive,expected", [
    ((5, 6, 7), Team.GOOD), ((1, 2, 5, 6), Team.WOLF),
    ((1, 2, 3), Team.WOLF), ((1, 5, 6), None),
])
def test_win_conditions(engine, alive, expected):
    snapshot = engine.state
    for seat, player in snapshot.public.players.items():
        player.alive = seat in alive
    assert check_winner(snapshot) == expected


def test_invariant_violation_fails_loudly(engine):
    state = engine.state
    state.public.dead.add(1)
    with pytest.raises(InvariantViolation, match="overlap"):
        validate_game_state(state)


def test_state_snapshot_is_detached(engine):
    state = engine.state
    state.secret.roles.clear()
    state.public.players[1].alive = False
    assert len(engine.state.secret.roles) == 12
    assert engine.state.public.players[1].alive


def test_day_and_event_limits(board):
    from werewolf.game.engine import GameEngine
    limited = board.model_copy(update={"max_days": 1})
    with pytest.raises(GameLimitExceeded, match="MAX_DAYS"):
        AutoRunner(GameEngine(limited, 123)).run()
    limited = board.model_copy(update={"max_events": 2})
    with pytest.raises(GameLimitExceeded, match="MAX_EVENTS"):
        AutoRunner(GameEngine(limited, 123)).run()
