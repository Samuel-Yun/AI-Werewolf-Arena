from pydantic import ValidationError
from collections.abc import Callable

from werewolf.agents.agent import Agent, MockAgent
from werewolf.agents.context import build_context_for_player
from werewolf.agents.memory import MemoryStore, SimpleMemoryStore
from werewolf.game.engine import GameEngine
from werewolf.game.actions import Action
from werewolf.game.errors import IllegalAction
from werewolf.game.events import EventType as E
from werewolf.providers.mock import MockProvider
from werewolf.providers.errors import FatalProviderError, ProviderError


class AutoRunner:
    """Bounded correction attempts followed by a validated local fallback."""

    def __init__(self, engine: GameEngine, agents: dict[int, Agent] | None = None,
                 memory: MemoryStore | None = None, on_step: Callable[[GameEngine], None] | None = None):
        self.engine = engine
        state = engine.state
        self.agents = agents if agents is not None else {
            p.seat: MockAgent(state.seed, p.seat) for p in state.profiles
        }
        self.memory = memory or SimpleMemoryStore()
        self.on_step = on_step
        self.fallbacks = {p.seat: MockProvider(state.seed, p.seat, stream="fallback") for p in state.profiles}

    def take_action(self, seat: int) -> None:
        self.engine.submit(seat, self.propose_action(seat))

    def propose_action(self, seat: int, *, nudge: str | None = None) -> Action:
        context = build_context_for_player(self.engine._state, tuple(self.engine._events), seat,
                                          memories=self.memory.load(seat))
        feedback = None
        for attempt in range(self.engine._state.board.max_retries_per_action + 1):
            try:
                raw = self.agents[seat].act(context, feedback=feedback, nudge=nudge)
            except FatalProviderError:
                raise
            except ProviderError as exc:
                feedback = f"Provider failure: {type(exc).__name__}: {str(exc)[:300]}"
            except Exception as exc:
                feedback = f"Provider failure: {type(exc).__name__}"
            else:
                try:
                    return self.engine.validate(seat, raw)
                except (ValidationError, IllegalAction) as exc:
                    feedback = str(exc)[:1000]
            self.engine.emit(E.ACTION_REJECTED, actor=seat,
                             payload={"attempt": attempt + 1, "reason": feedback})
        self.engine.emit(E.FALLBACK_USED, actor=seat)
        return self.engine.validate(seat, self.fallbacks[seat].generate(context))

    def run(self) -> GameEngine:
        while not self.engine.ended:
            actor = self.engine.next_actor()
            if actor is None:
                self.engine.advance()
            else:
                self.take_action(actor)
            if self.on_step is not None:
                self.on_step(self.engine)
        return self.engine
