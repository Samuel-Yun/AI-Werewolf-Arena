import pytest

from conftest import begin_night
from werewolf.config import BoardConfig
from werewolf.game.engine import GameEngine
from werewolf.game.errors import InvariantViolation
from werewolf.game.phases import Phase
from werewolf.game.validation import validate_game_state
from werewolf.game.win_conditions import check_winner
from werewolf.roles import RoleName as R, Team
from werewolf.storage.replay import replay_events


@pytest.mark.parametrize("priority", [Team.GOOD, Team.WOLF])
def test_last_hunter_shoots_last_wolf_and_both_sides_disappear(priority):
    board = BoardConfig(name="double_elimination", players=3,
                        roles={R.WEREWOLF: 1, R.HUNTER: 1, R.VILLAGER: 1},
                        wolf_win="eliminate_good", simultaneous_elimination=priority)
    engine = GameEngine(board, 1, role_assignments={1: R.WEREWOLF, 2: R.HUNTER, 3: R.VILLAGER})
    begin_night(engine)
    engine.submit(1, {"action": "wolf_kill", "target": 3})
    for _ in range(5):
        engine.advance()
    assert engine.state.public.phase == Phase.DISCUSSION
    for seat in (1, 2):
        engine.submit(seat, {"action": "speech", "text": "准备投票。"})
    engine.advance()
    engine.submit(1, {"action": "vote", "target": 2})
    engine.submit(2, {"action": "vote", "target": None})
    engine.advance()
    engine.advance()
    engine.submit(2, {"action": "hunter_shot", "target": 1})
    engine.advance()
    engine.advance()
    assert engine.ended and not engine.state.public.alive
    assert engine.state.public.winner == priority
    assert replay_events(engine.events) == engine.state


def test_eliminate_good_differs_from_parity(engine):
    state = engine.state
    state.board = state.board.model_copy(update={"wolf_win": "eliminate_good"})
    for seat, player in state.public.players.items():
        player.alive = seat in {1, 2, 5, 6}
    assert check_winner(state) is None


def test_invariant_rejects_impossible_wolf_target(engine):
    state = engine.state
    state.secret.night.wolf_target = 99
    with pytest.raises(InvariantViolation, match="wolf target"):
        validate_game_state(state)


def test_invariant_rejects_false_winner(engine):
    state = engine.state
    state.public.winner = Team.GOOD
    with pytest.raises(InvariantViolation, match="winner"):
        validate_game_state(state)
