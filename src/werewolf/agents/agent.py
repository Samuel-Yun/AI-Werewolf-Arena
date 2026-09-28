from werewolf.agents.context import AgentContext
from werewolf.providers.base import LLMProvider
from werewolf.providers.mock import MockProvider


class Agent:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def act(self, context: AgentContext, *, feedback: str | None = None,
            nudge: str | None = None) -> object:
        return self.provider.generate(context, feedback=feedback, nudge=nudge)


class MockAgent(Agent):
    def __init__(self, seed: int, seat: int):
        super().__init__(MockProvider(seed, seat))

