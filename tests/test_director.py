import pytest

from werewolf.agents.agent import Agent
from werewolf.director.cli import ConsoleDirector, DirectorRunner, ReviewDecision
from werewolf.game.engine import GameEngine
from werewolf.game.errors import GameLimitExceeded
from werewolf.game.events import EventType as E, Visibility
from werewolf.game.phases import Phase
from werewolf.providers.mock import MockProvider
from werewolf.runner import AutoRunner
from werewolf.storage.replay import replay_events


class RecordingProvider:
    def __init__(self, seed, seat):
        self.mock = MockProvider(seed, seat)
        self.nudges = []
        self.contexts = []

    def generate(self, context, *, feedback=None, nudge=None):
        self.contexts.append(context)
        self.nudges.append(nudge)
        return self.mock.generate(context, feedback=feedback, nudge=nudge)


class ScriptedReviewer:
    def __init__(self, engine, decisions):
        self.engine = engine
        self.decisions = list(decisions)
        self.proposals = []
        self.first_seat = None

    def review(self, context, proposal, director_state):
        # Draft generation and review cannot publish a speech before acceptance.
        if self.first_seat is None:
            self.first_seat = context.profile.seat
        if self.decisions:
            assert not self.engine.state.public.speeches
        assert not hasattr(context, "secret")
        assert director_state.secret.roles
        director_state.secret.roles.clear()
        self.proposals.append(proposal.text)
        return self.decisions.pop(0) if self.decisions else ReviewDecision(choice="accept")


def director_game(board, decisions):
    engine = GameEngine(board, 123)
    providers = {seat: RecordingProvider(123, seat) for seat in range(1, 13)}
    agents = {seat: Agent(p) for seat, p in providers.items()}
    reviewer = ScriptedReviewer(engine, decisions)
    runner = DirectorRunner(engine, agents, reviewer=reviewer)
    return engine, runner, reviewer, providers


def test_accept_is_equivalent_to_auto(board):
    engine, runner, _, _ = director_game(board, [])
    runner.run()
    automatic = AutoRunner(GameEngine(board, 123)).run()
    assert engine.state.public == automatic.state.public
    assert engine.state.secret == automatic.state.secret
    assert replay_events(engine.events) == engine.state


def test_regenerate_nudge_then_edit_only_publishes_final_text(board):
    decisions = [ReviewDecision(choice="regenerate"),
                 ReviewDecision(choice="nudge", text="直接回应3号。"),
                 ReviewDecision(choice="edit", text="3号，我想先听你的理由。")]
    engine, runner, reviewer, providers = director_game(board, decisions)
    runner.run()
    assert engine.state.public.speeches[0]["text"] == "3号，我想先听你的理由。"
    seat = reviewer.first_seat
    speech_contexts = [c for c in providers[seat].contexts if c.public.phase == Phase.DISCUSSION]
    assert speech_contexts[0] == speech_contexts[1] == speech_contexts[2]
    assert "直接回应3号。" in reviewer.proposals[2]
    decisions = [e for e in engine.events if e.event_type == E.DIRECTOR_DECISION]
    assert all(e.visibility == Visibility.ENGINE_ONLY for e in decisions)
    assert replay_events(engine.events) == engine.state


def test_skip_finishes_speech_turn_without_publishing_draft(board):
    engine, runner, reviewer, _ = director_game(board, [ReviewDecision(choice="skip")])
    runner.run()
    assert engine.state.public.speeches[0]["text"] == "[跳过发言]"
    assert not any(e.event_type == E.PLAYER_SPOKE and e.day == 1 and e.actor == reviewer.first_seat
                   for e in engine.events)
    assert replay_events(engine.events) == engine.state


def test_invalid_edit_is_rejected_and_can_be_corrected(board):
    engine, runner, _, _ = director_game(board, [ReviewDecision(choice="edit", text="  "),
                                               ReviewDecision(choice="edit", text="我改好了。")])
    runner.run()
    assert engine.state.public.speeches[0]["text"] == "我改好了。"
    assert any(e.event_type == E.ACTION_REJECTED for e in engine.events)


def test_review_loop_is_bounded(board):
    engine, runner, _, _ = director_game(board, [ReviewDecision(choice="regenerate")] * 3)
    runner.max_reviews = 2
    with pytest.raises(GameLimitExceeded, match="MAX_DIRECTOR_REVIEWS"):
        runner.run()


def test_review_predicate_reserves_hybrid_mode_interface(board):
    engine, runner, reviewer, _ = director_game(board, [])
    runner.review_when = lambda context: False
    runner.run()
    assert not reviewer.proposals


def test_console_controls_and_god_view(board):
    engine = GameEngine(board, 123)
    from werewolf.agents.context import build_context_for_player
    from werewolf.game.actions import SpeechAction
    context = build_context_for_player(engine.state, engine.events, 1)
    answers = iter(["g", "n", "回应3号。"])
    output = []
    reviewer = ConsoleDirector(read=lambda prompt: next(answers), write=output.append)
    decision = reviewer.review(context, SpeechAction(text="测试发言。"), engine.state)
    assert decision == ReviewDecision(choice="nudge", text="回应3号。")
    assert any('"secret"' in line for line in output)

