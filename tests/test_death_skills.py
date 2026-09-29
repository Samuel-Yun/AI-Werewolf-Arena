import pytest

from conftest import begin_night
from werewolf.agents.context import build_context_for_player
from werewolf.config import BoardConfig, HunterRules, IdiotRules
from werewolf.game.engine import GameEngine
from werewolf.game.errors import IllegalAction
from werewolf.game.phases import Phase
from werewolf.game.rules import legal_actions
from werewolf.roles import RoleName as R
from werewolf.runner import AutoRunner
from werewolf.storage.replay import replay_events


def rich_game(*, hunter=None, idiot=None):
    board = BoardConfig(name="death_skills", players=12,
                        roles={R.WEREWOLF: 4, R.SEER: 1, R.WITCH: 1, R.HUNTER: 1, R.IDIOT: 1, R.VILLAGER: 4},
                        hunter=hunter or HunterRules(), idiot=idiot or IdiotRules())
    role_list = [R.WEREWOLF] * 4 + [R.SEER, R.WITCH, R.HUNTER, R.IDIOT] + [R.VILLAGER] * 4
    return GameEngine(board, 123, role_assignments=dict(enumerate(role_list, 1)))


def rich_night(engine, *, kill=9, poison=None):
    begin_night(engine)
    complete_night(engine, kill=kill, poison=poison)


def complete_night(engine, *, kill, poison=None):
    for seat in range(1, 5):
        engine.submit(seat, {"action": "wolf_kill", "target": kill})
    engine.advance()
    engine.submit(5, {"action": "seer_check", "target": 1})
    engine.advance()
    engine.submit(6, {"action": "witch", "poison_target": poison})
    for _ in range(4):
        engine.advance()


def exile(engine, target):
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "speech", "text": "我准备投票。"})
    engine.advance()
    for seat in engine.state.public.alive:
        if engine.state.public.players[seat].can_vote:
            engine.submit(seat, {"action": "vote", "target": target if target != seat else 1})
    engine.advance()
    engine.advance()


def test_hunter_killed_by_wolves_can_shoot_once():
    engine = rich_game()
    rich_night(engine, kill=7)
    assert engine.state.public.phase == Phase.DEATH_SKILL
    assert engine.next_actor() == 7
    view = build_context_for_player(engine.state, engine.events, 7)
    assert view.legal_actions[0].action == "hunter_shot"
    assert not view.own.wolf_teammates and not view.own.checks
    engine.submit(7, {"action": "hunter_shot", "target": 1})
    assert {1, 7} <= engine.state.public.dead
    with pytest.raises(IllegalAction):
        engine.submit(7, {"action": "hunter_shot", "target": 2})
    engine.advance()
    engine.advance()
    assert engine.state.public.phase == Phase.DISCUSSION


def test_hunter_can_hold_fire():
    engine = rich_game()
    rich_night(engine, kill=7)
    engine.submit(7, {"action": "hunter_shot", "target": None})
    assert engine.state.public.dead == {7}
    assert engine.state.secret.hunter_spent == {7}


@pytest.mark.parametrize("kill", [7, 9])
def test_poison_blocks_hunter_even_on_double_kill(kill):
    engine = rich_game()
    rich_night(engine, kill=kill, poison=7)
    assert 7 in engine.state.public.dead
    assert not engine.state.secret.death_skill_queue
    with pytest.raises(IllegalAction):
        engine.submit(7, {"action": "hunter_shot", "target": 1})


def test_hunter_poison_rule_is_configurable():
    rules = HunterRules(allowed_causes=("poison",), blocked_causes=())
    engine = rich_game(hunter=rules)
    rich_night(engine, poison=7)
    assert engine.state.public.phase == Phase.DEATH_SKILL
    assert engine.next_actor() == 7


def test_live_hunter_and_non_hunter_cannot_shoot():
    engine = rich_game()
    with pytest.raises(IllegalAction):
        engine.submit(7, {"action": "hunter_shot", "target": 1})
    rich_night(engine, kill=7)
    with pytest.raises(IllegalAction):
        engine.submit(8, {"action": "hunter_shot", "target": 1})
    with pytest.raises(IllegalAction):
        engine.submit(7, {"action": "hunter_shot", "target": 7})


def test_exiled_hunter_shoots_before_day_win_check():
    engine = rich_game()
    rich_night(engine)
    exile(engine, 7)
    assert engine.state.public.phase == Phase.DEATH_SKILL
    engine.submit(7, {"action": "hunter_shot", "target": 1})
    engine.advance()
    assert engine.state.public.phase == Phase.DAY_WIN_CHECK


def test_hunter_can_prevent_parity_victory():
    roles = [R.WEREWOLF] * 3 + [R.HUNTER] + [R.VILLAGER] * 3
    board = BoardConfig(name="parity_then_shot", players=7,
                        roles={R.WEREWOLF: 3, R.HUNTER: 1, R.VILLAGER: 3})
    engine = GameEngine(board, 1, role_assignments=dict(enumerate(roles, 1)))
    begin_night(engine)
    for seat in (1, 2, 3):
        engine.submit(seat, {"action": "wolf_kill", "target": 4})
    for _ in range(4):
        engine.advance()
    assert engine.state.public.phase == Phase.DEATH_SKILL
    assert engine.state.public.winner is None
    engine.submit(4, {"action": "hunter_shot", "target": 1})
    engine.advance()
    engine.advance()
    assert not engine.ended
    assert engine.state.public.phase == Phase.DISCUSSION


def test_chain_of_hunters_is_resolved_in_queue_order():
    roles = [R.WEREWOLF, R.HUNTER, R.HUNTER, R.VILLAGER, R.VILLAGER]
    board = BoardConfig(name="chain", players=5, roles={R.WEREWOLF: 1, R.HUNTER: 2, R.VILLAGER: 2})
    engine = GameEngine(board, 1, role_assignments=dict(enumerate(roles, 1)))
    begin_night(engine)
    engine.submit(1, {"action": "wolf_kill", "target": 2})
    for _ in range(4):
        engine.advance()
    engine.submit(2, {"action": "hunter_shot", "target": 3})
    assert engine.next_actor() == 3
    engine.submit(3, {"action": "hunter_shot", "target": 1})
    engine.advance()
    engine.advance()
    assert engine.ended and engine.state.public.winner == "good"
    assert replay_events(engine.events) == engine.state


def test_idiot_survives_exile_loses_vote_but_keeps_speaking():
    engine = rich_game()
    rich_night(engine)
    exile(engine, 8)
    player = engine.state.public.players[8]
    assert player.alive and not player.can_vote and player.revealed_role == R.IDIOT
    engine.advance()
    engine.advance()
    complete_night(engine, kill=10)
    assert engine.state.public.players[8].alive
    for seat in engine.state.public.alive:
        if seat == 8:
            break
        engine.submit(seat, {"action": "speech", "text": "过。"})
    assert legal_actions(engine.state, 8)[0].action == "speech"
    engine.submit(8, {"action": "speech", "text": "我已经翻牌了，继续听你们聊。"})
    for seat in engine.state.public.alive:
        if seat > 8:
            engine.submit(seat, {"action": "speech", "text": "过。"})
    engine.advance()
    with pytest.raises(IllegalAction):
        engine.submit(8, {"action": "vote", "target": 1})
    with pytest.raises(IllegalAction):
        engine.submit(1, {"action": "vote", "target": 8})


@pytest.mark.parametrize("cause", ["wolf_kill", "poison"])
def test_idiot_dies_to_night_skills(cause):
    engine = rich_game()
    rich_night(engine, kill=8 if cause == "wolf_kill" else 9, poison=8 if cause == "poison" else None)
    assert not engine.state.public.players[8].alive
    assert engine.state.public.players[8].revealed_role is None


def test_revealed_idiot_can_be_shot():
    engine = rich_game()
    rich_night(engine)
    exile(engine, 8)
    engine.advance()
    engine.advance()
    complete_night(engine, kill=7)
    assert engine.state.public.phase == Phase.DEATH_SKILL
    engine.submit(7, {"action": "hunter_shot", "target": 8})
    assert not engine.state.public.players[8].alive


def test_repeated_exile_can_kill_when_configured():
    engine = rich_game(idiot=IdiotRules(exile_after_reveal="dies"))
    rich_night(engine)
    exile(engine, 8)
    engine.advance()
    engine.advance()
    complete_night(engine, kill=10)
    exile(engine, 8)
    assert not engine.state.public.players[8].alive


def test_rich_board_replay():
    engine = AutoRunner(rich_game()).run()
    assert replay_events(engine.events) == engine.state
