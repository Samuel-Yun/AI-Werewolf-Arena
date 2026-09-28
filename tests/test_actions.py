import pytest
from pydantic import ValidationError

from conftest import begin_night, play_night
from werewolf.game.actions import parse_action
from werewolf.game.errors import IllegalAction
from werewolf.game.phases import Phase


@pytest.mark.parametrize("raw", [
    '{"action":"vote","target":true}',
    {"action": "vote", "target": "7"},
    {"action": "wolf_kill", "target": 7, "alive": False},
    {"action": "unknown", "target": 7},
    {"action": "speech", "text": "   "},
    {"action": "speech", "text": 12},
    "not JSON",
])
def test_schema_rejects_untrusted_outputs(raw):
    with pytest.raises(ValidationError):
        parse_action(raw)


def test_parses_json_and_abstention():
    action = parse_action('{"action":"vote","target":null}')
    assert action.target is None


@pytest.mark.parametrize("actor,target", [(1, 1), (1, 2), (1, 99), (5, 6), (99, 6)])
def test_illegal_wolf_actions_do_not_mutate(engine, actor, target):
    begin_night(engine)
    before = engine.state
    with pytest.raises(IllegalAction):
        engine.submit(actor, {"action": "wolf_kill", "target": target})
    assert engine.state == before


def test_duplicate_action_is_rejected(engine):
    begin_night(engine)
    engine.submit(1, {"action": "wolf_kill", "target": 6})
    with pytest.raises(IllegalAction):
        engine.submit(1, {"action": "wolf_kill", "target": 7})


def test_wrong_phase_and_dead_voting(engine):
    with pytest.raises(IllegalAction):
        engine.submit(1, {"action": "vote", "target": 6})
    play_night(engine)
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "speech", "text": "继续。"})
    engine.advance()
    assert engine.state.public.phase == Phase.VOTING
    with pytest.raises(IllegalAction):
        engine.submit(6, {"action": "vote", "target": 1})
    with pytest.raises(IllegalAction):
        engine.submit(1, {"action": "vote", "target": 6})
    with pytest.raises(IllegalAction):
        engine.submit(1, {"action": "vote", "target": 1})

