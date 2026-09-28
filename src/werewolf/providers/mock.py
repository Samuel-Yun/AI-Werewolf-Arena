from random import Random

from werewolf.agents.context import AgentContext


class MockProvider:
    def __init__(self, seed: int, seat: int, *, stream: str = "mock"):
        self.rng = Random(f"{seed}:{stream}:{seat}")

    def generate(self, context: AgentContext, *, feedback: str | None = None,
                 nudge: str | None = None) -> object:
        if not context.legal_actions:
            raise ValueError("No legal action")
        option = context.legal_actions[0]
        if option.action == "witch":
            if option.save_targets and self.rng.random() < 0.5:
                return {"action": "witch", "save_target": option.save_targets[0]}
            if option.targets and self.rng.random() < 0.5:
                return {"action": "witch", "poison_target": self.rng.choice(option.targets)}
            return {"action": "witch"}
        if option.action == "speech":
            others = [seat for seat in context.public.alive if seat != context.profile.seat]
            suspect = self.rng.choice(others) if others else context.profile.seat
            text = f"我是{context.profile.seat}号{context.profile.name}。今天我想听{suspect}号解释一下，先看发言和票型。"
            if nudge:
                text += f" {nudge}"
            return {"action": "speech", "text": text}
        if option.targets:
            return {"action": option.action, "target": self.rng.choice(option.targets)}
        if option.allow_pass:
            return {"action": option.action, "target": None}
        raise ValueError("No legal target")
