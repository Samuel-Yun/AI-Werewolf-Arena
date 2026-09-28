import pytest
from pydantic import ValidationError

from werewolf.agents.context import build_context_for_player
from werewolf.config import BoardConfig, HybridRules
from werewolf.game.engine import GameEngine
from werewolf.game.errors import IllegalAction, InvariantViolation
from werewolf.game.phases import Phase
from werewolf.game.validation import validate_game_state
from werewolf.game.win_conditions import check_winner, winning_players
from werewolf.roles import RoleName as R, Team
from werewolf.runner import AutoRunner
from werewolf.storage.replay import replay_events


def hybrid_game(**rules):
    board = BoardConfig(name="hybrid_test", players=12,
                        roles={R.WEREWOLF: 4, R.SEER: 1, R.WITCH: 1, R.HUNTER: 1, R.IDIOT: 1,
                               R.HYBRID: 1, R.VILLAGER: 3}, hybrid=HybridRules(**rules))
    roles = [R.WEREWOLF] * 4 + [R.SEER, R.WITCH, R.HUNTER, R.IDIOT, R.HYBRID] + [R.VILLAGER] * 3
    return GameEngine(board, 123, role_assignments=dict(enumerate(roles, 1)))


def choose(engine, target=1):
    engine.advance()
    engine.advance()
    assert engine.state.public.phase == Phase.HYBRID_CHOOSE
    engine.submit(9, {"action": "hybrid_choose", "target": target})
    engine.advance()


@pytest.mark.parametrize("target,expected", [(1, Team.WOLF), (5, Team.GOOD), (10, Team.GOOD)])
def test_follows_initial_model_alignment(target, expected):
    engine = hybrid_game()
    choose(engine, target)
    assert engine.state.secret.hybrid_models == {9: target}
    assert engine.state.secret.hybrid_teams == {9: expected}
    state = engine.state
    state.public.players[target].alive = False
    assert state.secret.hybrid_teams[9] == expected


@pytest.mark.parametrize("alignment,target,expected", [("good", 1, Team.GOOD), ("wolf", 5, Team.WOLF)])
def test_alignment_policy_is_configurable(alignment, target, expected):
    engine = hybrid_game(alignment=alignment)
    choose(engine, target)
    assert engine.state.secret.hybrid_teams[9] == expected


def test_hybrid_has_no_model_role_or_wolf_team_access():
    engine = hybrid_game()
    choose(engine)
    hybrid = build_context_for_player(engine.state, engine.events, 9)
    wolf = build_context_for_player(engine.state, engine.events, 1)
    villager = build_context_for_player(engine.state, engine.events, 10)
    assert hybrid.own.hybrid_model == 1 and hybrid.own.team is None
    assert not hybrid.own.wolf_teammates
    assert not hybrid.legal_actions
    assert wolf.own.wolf_teammates == (1, 2, 3, 4)
    assert villager.own.hybrid_model is None
    assert all(p.revealed_role is None for p in hybrid.public.players)


def test_revealing_alignment_is_an_explicit_configuration():
    engine = hybrid_game(reveal_alignment=True)
    choose(engine)
    assert build_context_for_player(engine.state, engine.events, 9).own.team == Team.WOLF


def test_model_can_only_be_chosen_once_on_first_night():
    engine = hybrid_game()
    engine.advance()
    engine.advance()
    for target in (9, 99):
        with pytest.raises(IllegalAction):
            engine.submit(9, {"action": "hybrid_choose", "target": target})
    with pytest.raises(IllegalAction):
        engine.submit(10, {"action": "hybrid_choose", "target": 1})
    engine.submit(9, {"action": "hybrid_choose", "target": 1})
    with pytest.raises(IllegalAction):
        engine.submit(9, {"action": "hybrid_choose", "target": 5})
    engine.advance()
    with pytest.raises(IllegalAction):
        engine.submit(9, {"action": "hybrid_choose", "target": 5})


@pytest.mark.parametrize("result", [Team.GOOD, Team.WOLF])
def test_seer_result_is_independent_of_hybrid_alignment(result):
    engine = hybrid_game(seer_result=result)
    choose(engine, 1)
    for seat in range(1, 5):
        engine.submit(seat, {"action": "wolf_kill", "target": 10})
    engine.advance()
    engine.submit(5, {"action": "seer_check", "target": 9})
    engine.advance()
    engine.submit(6, {"action": "witch"})
    engine.advance()
    engine.advance()
    assert engine.state.secret.check_history[5][0]["result"] == result


@pytest.mark.parametrize("counted,expected", [(False, Team.WOLF), (True, None)])
def test_hybrid_victory_counts_are_configurable(counted, expected):
    engine = hybrid_game(counts_for_win=counted)
    choose(engine, 5)
    state = engine.state
    for seat, player in state.public.players.items():
        player.alive = seat in {1, 5, 9}
    assert check_winner(state) == expected


@pytest.mark.parametrize("victory,winner,alive,won", [
    ("aligned_team", Team.WOLF, False, True),
    ("aligned_team", Team.GOOD, True, False),
    ("model_team", Team.GOOD, False, True),
    ("model_team", Team.WOLF, True, False),
    ("survive", Team.GOOD, True, True),
    ("survive", Team.WOLF, False, False),
])
def test_hybrid_individual_victory_policy(victory, winner, alive, won):
    engine = hybrid_game(alignment="wolf", victory=victory)
    choose(engine, 5)
    state = engine.state
    state.public.players[9].alive = alive
    assert (9 in winning_players(state, winner)) == won


def test_hybrid_alignment_invariant():
    engine = hybrid_game()
    choose(engine)
    state = engine.state
    state.secret.hybrid_teams[9] = Team.GOOD
    with pytest.raises(InvariantViolation, match="alignment"):
        validate_game_state(state)


def test_non_attacking_hybrid_count_configuration_rejects_forced_stalemate():
    with pytest.raises(ValidationError, match="non-attacking"):
        BoardConfig(name="invalid", players=3, roles={R.WEREWOLF: 1, R.VILLAGER: 1, R.HYBRID: 1},
                    wolf_win="eliminate_good", hybrid=HybridRules(counts_for_win=True))


def test_initial_parity_ends_without_an_unnecessary_night():
    board = BoardConfig(name="already_won", players=3, roles={R.WEREWOLF: 2, R.VILLAGER: 1})
    engine = AutoRunner(GameEngine(board, 123)).run()
    assert engine.ended and engine.state.public.day == 0
    assert engine.state.public.winner == Team.WOLF


def test_full_board_replay_and_seed_reproducibility():
    first = AutoRunner(hybrid_game()).run()
    second = AutoRunner(hybrid_game()).run()
    assert first.state == second.state
    assert replay_events(first.events) == first.state

