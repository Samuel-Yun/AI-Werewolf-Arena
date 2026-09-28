from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from werewolf.agents.context import AgentContext, build_context_for_player
from werewolf.game.actions import SkipSpeechAction, SpeechAction
from werewolf.game.errors import GameLimitExceeded
from werewolf.game.events import EventType as E
from werewolf.game.state import GameState
from werewolf.runner import AutoRunner
from werewolf.storage.game_store import state_document


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    choice: Literal["accept", "regenerate", "nudge", "edit", "skip"]
    text: str | None = None


class ContentReviewer(Protocol):
    def review(self, context: AgentContext, proposal: SpeechAction,
               director_state: GameState) -> ReviewDecision: ...


class ConsoleDirector:
    def __init__(self, read: Callable[[str], str] | None = None,
                 write: Callable[[str], None] | None = None):
        self.read = read or input
        self.write = write or print

    def review(self, context: AgentContext, proposal: SpeechAction,
               director_state: GameState) -> ReviewDecision:
        self.write(f"\nDay {context.public.day} | Seat {context.profile.seat} | {context.profile.name}")
        self.write("Director roles: " + ", ".join(
            f"{s}:{role}" for s, role in sorted(director_state.secret.roles.items())
        ))
        self.write(f"Generated:\n{proposal.text}")
        choices = {"a": "accept", "r": "regenerate", "n": "nudge", "e": "edit", "s": "skip"}
        for _ in range(20):
            choice = self.read("[A] Accept [R] Regenerate [N] Nudge [E] Edit [S] Skip [G] State: ").strip().lower()
            if choice == "g":
                import json
                self.write(json.dumps(state_document(director_state), ensure_ascii=False, indent=2))
                continue
            if choice not in choices:
                self.write("请输入 A / R / N / E / S / G。")
                continue
            text = self.read("指导: " if choice == "n" else "发言: ") if choice in {"n", "e"} else None
            return ReviewDecision(choice=choices[choice], text=text)
        raise GameLimitExceeded("MAX_DIRECTOR_INPUT_ATTEMPTS exceeded")


class DirectorRunner(AutoRunner):
    def __init__(self, engine, agents=None, memory=None, *, reviewer: ContentReviewer | None = None,
                 review_when: Callable[[AgentContext], bool] | None = None, max_reviews: int = 20,
                 on_step: Callable | None = None):
        super().__init__(engine, agents, memory, on_step=on_step)
        self.reviewer = reviewer or ConsoleDirector()
        self.review_when = review_when or (lambda context: True)
        self.max_reviews = max_reviews

    def take_action(self, seat: int) -> None:
        proposal = self.propose_action(seat)
        if not isinstance(proposal, SpeechAction):
            self.engine.submit(seat, proposal)
            return
        context = build_context_for_player(self.engine._state, tuple(self.engine._events), seat,
                                          memories=self.memory.load(seat))
        if not self.review_when(context):
            self.engine.submit(seat, proposal)
            return
        for _ in range(self.max_reviews):
            decision = self.reviewer.review(context, proposal, self.engine.state)
            self.engine.emit(E.DIRECTOR_DECISION, actor=seat, payload=decision.model_dump())
            match decision.choice:
                case "accept":
                    self.engine.submit(seat, proposal)
                    return
                case "skip":
                    self.engine.submit(seat, SkipSpeechAction())
                    return
                case "regenerate" | "nudge":
                    proposal = self.propose_action(seat, nudge=decision.text if decision.choice == "nudge" else None)
                    if not isinstance(proposal, SpeechAction):
                        self.engine.submit(seat, proposal)
                        return
                case "edit":
                    try:
                        proposal = SpeechAction(text=decision.text)
                    except ValidationError as exc:
                        self.engine.emit(E.ACTION_REJECTED, actor=seat,
                                         payload={"reason": str(exc)[:1000], "source": "director_edit"})
                        if isinstance(self.reviewer, ConsoleDirector):
                            self.reviewer.write("编辑发言无效：请输入 1–4000 字的非空文本。")
                        continue
                    self.engine.submit(seat, proposal)
                    return
        raise GameLimitExceeded("MAX_DIRECTOR_REVIEWS exceeded")
