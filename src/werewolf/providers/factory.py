from werewolf.agents.agent import Agent, MockAgent
from werewolf.config import BoardConfig, PlayerConfig
from werewolf.providers.openai_compatible import DeepSeekProvider, OpenAICompatibleClient


def create_agents(board: BoardConfig, players: tuple[PlayerConfig, ...], seed: int, *,
                  timeout: float = 45, max_requests: int = 240, thinking: str = "disabled"):
    unsupported = sorted({p.provider for p in players} - {"mock", "deepseek"})
    if unsupported:
        raise ValueError(f"Unsupported providers: {', '.join(unsupported)}")
    real_players = [p for p in players if p.provider == "deepseek"]
    client = None
    catalog = []
    if real_players:
        client = OpenAICompatibleClient.from_environment(timeout=timeout, max_requests=max_requests)
        catalog = client.list_models()
        available = {m.get("id") for m in catalog if isinstance(m.get("id"), str)}
        requested = {p.model for p in real_players}
        if not requested <= available:
            raise ValueError(f"Requested API models unavailable: {sorted(requested - available)}; available={sorted(available)}")
        catalog = [m for m in catalog if m.get("id") in requested]
    agents = {p.seat: Agent(DeepSeekProvider(client, board, model=p.model, thinking=thinking))
              if p.provider == "deepseek" else MockAgent(seed, p.seat) for p in players}
    return agents, client, catalog

