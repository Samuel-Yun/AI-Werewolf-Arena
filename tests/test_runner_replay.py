from pathlib import Path

import pytest

from werewolf.agents.agent import Agent
from werewolf.game.engine import GameEngine
from werewolf.game.errors import ReplayError
from werewolf.game.events import EventType
from werewolf.runner import AutoRunner
from werewolf.simulation import simulate
from werewolf.storage.game_store import GameStore, state_document
from werewolf.storage.replay import replay_directory, replay_events


class BrokenProvider:
    def __init__(self, *, raise_error=False):
        self.raise_error = raise_error
        self.calls = []

    def generate(self, context, *, feedback=None, nudge=None):
        self.calls.append(feedback)
        if self.raise_error:
            raise TimeoutError("unavailable")
        return {"action": "vote", "target": 999}


@pytest.mark.parametrize("raise_error", [False, True])
def test_broken_provider_corrects_once_then_falls_back(board, raise_error):
    engine = GameEngine(board, 123)
    broken = BrokenProvider(raise_error=raise_error)
    agents = {seat: Agent(broken) for seat in range(1, 13)}
    AutoRunner(engine, agents).run()
    assert engine.ended
    rejected = [e for e in engine.events if e.event_type == EventType.ACTION_REJECTED]
    fallback = [e for e in engine.events if e.event_type == EventType.FALLBACK_USED]
    assert len(rejected) == 2 * len(fallback)
    assert broken.calls[0] is None and broken.calls[1] is not None


def test_seed_reproduces_full_state_and_actions(board):
    first = AutoRunner(GameEngine(board, 123)).run()
    second = AutoRunner(GameEngine(board, 123)).run()
    assert first.state == second.state
    def semantic_events(engine):
        return [e.model_dump(exclude={"timestamp", "game_id"}) for e in engine.events]
    assert semantic_events(first) == semantic_events(second)


@pytest.mark.parametrize("seed", [0, 1, 2, 123, 928374])
def test_complete_game_replays_identically(board, seed):
    engine = AutoRunner(GameEngine(board, seed)).run()
    assert replay_events(engine.events) == engine.state


def test_storage_transcript_and_replay(board, tmp_path):
    engine = AutoRunner(GameEngine(board, 123)).run()
    directory = GameStore(tmp_path).save(engine)
    assert {p.name for p in directory.iterdir()} == {
        "metadata.json", "events.jsonl", "transcript.txt", "result.json"
    }
    assert "Vote:" in (directory / "transcript.txt").read_text(encoding="utf-8")
    assert state_document(replay_directory(directory)) == state_document(engine.state)
    with pytest.raises(FileExistsError):
        GameStore(tmp_path).save(engine)


def test_replay_rejects_missing_reordered_or_mixed_events(board):
    engine = AutoRunner(GameEngine(board, 123)).run()
    events = engine.events
    with pytest.raises(ReplayError):
        replay_events(events[:-1])
    with pytest.raises(ReplayError):
        replay_events((events[0], events[2], events[1], *events[3:]))
    changed = events[1].model_copy(update={"game_id": "other"})
    with pytest.raises(ReplayError):
        replay_events((events[0], changed, *events[2:]))


def test_simulation_summary(board, tmp_path):
    from werewolf.config import default_players
    stats = simulate(board, default_players(12), games=20, seed=123, failure_root=tmp_path)
    assert stats.success
    assert stats.completed_games == 20
    assert stats.good_wins + stats.wolf_wins + stats.special_wins == 20
    assert stats.crashed_games == stats.deadlocks == stats.invariant_violations == 0

