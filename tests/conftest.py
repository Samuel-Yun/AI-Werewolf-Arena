import pytest

from werewolf.config import BoardConfig
from werewolf.game.engine import GameEngine
from werewolf.game.phases import Phase
from werewolf.roles import RoleName as R


@pytest.fixture
def board():
    return BoardConfig(name="test_phase1", players=12,
                       roles={R.WEREWOLF: 4, R.SEER: 1, R.VILLAGER: 7})


@pytest.fixture
def engine(board):
    roles = {seat: R.WEREWOLF if seat <= 4 else R.SEER if seat == 5 else R.VILLAGER
             for seat in range(1, 13)}
    return GameEngine(board, 123, role_assignments=roles)


def begin_night(engine):
    engine.advance()
    engine.advance()
    assert engine.state.public.phase == Phase.WOLF


def play_night(engine, *, kill=6, check=1):
    if engine.state.public.phase == Phase.GAME_START:
        begin_night(engine)
    for seat in (1, 2, 3, 4):
        if engine.state.public.players[seat].alive:
            engine.submit(seat, {"action": "wolf_kill", "target": kill})
    engine.advance()
    if engine.state.public.players[5].alive:
        engine.submit(5, {"action": "seer_check", "target": check})
    engine.advance()
    engine.advance()
    engine.advance()
    engine.advance()


def finish_day(engine, *, exile=1):
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "speech", "text": "我想听一下大家的理由。"})
    engine.advance()
    for seat in engine.state.public.alive:
        engine.submit(seat, {"action": "vote", "target": exile if seat != exile else 2})
    engine.advance()
    engine.advance()
