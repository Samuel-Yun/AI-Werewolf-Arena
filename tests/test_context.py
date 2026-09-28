import pytest
from pydantic import ValidationError

from conftest import finish_day, play_night
from werewolf.agents.context import build_context_for_player
from werewolf.game.events import EventType
from werewolf.game.phases import Phase


def context(engine, seat):
    return build_context_for_player(engine.state, engine.events, seat)


def test_villager_cannot_see_roles_or_night_actions(engine):
    play_night(engine)
    view = context(engine, 7)
    assert view.own.role == "villager"
    assert not view.own.wolf_teammates
    assert not view.own.checks
    assert not hasattr(view, "secret")
    assert all(e.event_type not in {EventType.GAME_STARTED, EventType.WOLF_KILL_SELECTED,
                                  EventType.SEER_CHECKED, EventType.NIGHT_RESOLVED} for e in view.events)
    assert all(p.revealed_role is None for p in view.public.players)


def test_wolf_teammates_and_seer_checks_are_scoped(engine):
    play_night(engine)
    wolf, seer = context(engine, 1), context(engine, 5)
    assert wolf.own.wolf_teammates == (1, 2, 3, 4)
    assert any(e.event_type == EventType.WOLF_KILL_SELECTED for e in wolf.events)
    assert not wolf.own.checks
    assert seer.own.checks[0].target == 1
    assert seer.own.checks[0].result == "wolf"
    assert all(e.event_type != EventType.WOLF_KILL_SELECTED for e in seer.events)
    assert not seer.own.wolf_teammates


def test_dead_wolf_receives_no_future_wolf_actions(engine):
    play_night(engine)
    finish_day(engine, exile=1)
    engine.advance()
    engine.advance()
    assert engine.state.public.phase == Phase.WOLF
    engine.submit(2, {"action": "wolf_kill", "target": 7})
    dead = context(engine, 1)
    alive = context(engine, 2)
    assert not dead.legal_actions
    assert not any(e.day == 2 and e.event_type == EventType.WOLF_VOTE_SUBMITTED for e in dead.events)
    assert any(e.day == 2 and e.event_type == EventType.WOLF_VOTE_SUBMITTED for e in alive.events)


def test_context_is_immutable_and_has_no_mutable_state_references(engine):
    view = context(engine, 7)
    with pytest.raises(ValidationError):
        view.public.players[0].alive = False
    assert isinstance(view.events, tuple)
    assert isinstance(view.legal_actions, tuple)

