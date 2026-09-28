import pytest

from conftest import begin_night
from werewolf.agents.context import build_context_for_player
from werewolf.config import BoardConfig, WitchRules
from werewolf.game.engine import GameEngine
from werewolf.game.errors import IllegalAction, InvariantViolation
from werewolf.game.phases import Phase
from werewolf.game.validation import validate_game_state
from werewolf.roles import RoleName as R
from werewolf.runner import AutoRunner
from werewolf.storage.replay import replay_events


def witch_game(**rules):
    board = BoardConfig(name="witch_test", players=12,
                        roles={R.WEREWOLF: 4, R.SEER: 1, R.WITCH: 1, R.VILLAGER: 6},
                        witch=WitchRules(**rules))
    roles = {seat: R.WEREWOLF if seat <= 4 else R.SEER if seat == 5 else R.WITCH if seat == 6 else R.VILLAGER
             for seat in range(1, 13)}
    return GameEngine(board, 123, role_assignments=roles)


def witch_window(engine, kill=7):
    begin_night(engine)
    for seat in range(1, 5):
        engine.submit(seat, {"action": "wolf_kill", "target": kill})
    engine.advance()
    engine.submit(5, {"action": "seer_check", "target": 1})
    engine.advance()
    assert engine.state.public.phase == Phase.WITCH


def settle(engine, action):
    engine.submit(6, {"action": "witch", **action})
    engine.advance()
    engine.advance()
    engine.advance()


def test_antidote_saves_victim_and_is_consumed_only_at_resolution():
    engine = witch_game()
    witch_window(engine)
    engine.submit(6, {"action": "witch", "save_target": 7})
    assert engine.state.secret.potions[6].antidote == 1
    assert engine.state.public.players[7].alive
    engine.advance()
    engine.advance()
    engine.advance()
    assert engine.state.public.players[7].alive
    assert engine.state.secret.potions[6].antidote == 0
    assert engine.state.secret.potions[6].poison == 1


def test_poison_and_wolf_kill_resolve_together():
    engine = witch_game()
    witch_window(engine)
    settle(engine, {"poison_target": 8})
    assert engine.state.public.dead == {7, 8}
    assert engine.state.secret.potions[6].poison == 0
    assert engine.state.secret.night_causes[8] == ["poison"]


def test_same_target_double_kill_is_one_death():
    engine = witch_game()
    witch_window(engine)
    settle(engine, {"poison_target": 7})
    assert engine.state.public.dead == {7}
    assert engine.state.secret.night_causes[7] == ["wolf_kill", "poison"]


def test_saved_but_poisoned_target_still_dies_when_both_potions_allowed():
    engine = witch_game(allow_both_potions=True)
    witch_window(engine)
    settle(engine, {"save_target": 7, "poison_target": 7})
    assert engine.state.public.dead == {7}
    assert engine.state.secret.night_causes[7] == ["poison"]
    assert engine.state.secret.potions[6].antidote == engine.state.secret.potions[6].poison == 0


@pytest.mark.parametrize("action", [
    {"save_target": 8}, {"poison_target": 6}, {"poison_target": 99},
    {"save_target": 7, "poison_target": 8},
])
def test_invalid_potion_actions_preserve_state(action):
    engine = witch_game()
    witch_window(engine)
    before = engine.state
    with pytest.raises(IllegalAction):
        engine.submit(6, {"action": "witch", **action})
    assert engine.state == before


@pytest.mark.parametrize("policy,allowed", [("never", False), ("first_night", True), ("always", True)])
def test_first_night_self_save_policy(policy, allowed):
    engine = witch_game(self_save=policy)
    witch_window(engine, kill=6)
    if allowed:
        settle(engine, {"save_target": 6})
        assert engine.state.public.players[6].alive
    else:
        with pytest.raises(IllegalAction):
            engine.submit(6, {"action": "witch", "save_target": 6})


def test_witch_sees_only_required_information():
    engine = witch_game()
    witch_window(engine)
    witch = build_context_for_player(engine.state, engine.events, 6)
    villager = build_context_for_player(engine.state, engine.events, 8)
    assert witch.own.wolf_victim == 7
    assert witch.own.antidote == witch.own.poison == 1
    assert not witch.own.wolf_teammates and not witch.own.checks
    assert villager.own.wolf_victim is None and villager.own.antidote is None
    settle(engine, {"save_target": 7})
    assert build_context_for_player(engine.state, engine.events, 6).own.wolf_victim is None


def test_negative_potion_count_is_an_invariant_failure():
    state = witch_game().state
    state.secret.potions[6].antidote = -1
    with pytest.raises(InvariantViolation, match="potion"):
        validate_game_state(state)


def test_spent_antidote_cannot_be_reused_and_victim_is_hidden():
    engine = witch_game()
    witch_window(engine)
    settle(engine, {"save_target": 7})
    engine.advance()
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "speech", "text": "过。"})
    engine.advance()
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "vote", "target": None})
    for _ in range(4):
        engine.advance()
    for seat in range(1, 5):
        engine.submit(seat, {"action": "wolf_kill", "target": 8})
    engine.advance()
    engine.submit(5, {"action": "seer_check", "target": 1})
    engine.advance()
    assert engine.state.public.day == 2
    view = build_context_for_player(engine.state, engine.events, 6)
    assert view.own.wolf_victim is None
    with pytest.raises(IllegalAction):
        engine.submit(6, {"action": "witch", "save_target": 8})


def test_witch_board_replay():
    engine = AutoRunner(witch_game()).run()
    assert replay_events(engine.events) == engine.state
