from typing import Protocol

from werewolf.agents.context import AgentContext


class LLMProvider(Protocol):
    def generate(self, context: AgentContext, *, feedback: str | None = None,
                 nudge: str | None = None) -> object: ...

