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
        if option.action == "sheriff_signup":
            return {"action": "sheriff_signup", "run": self.rng.random() < 0.3}
        if option.action == "sheriff_withdraw":
            return {"action": "sheriff_withdraw", "withdraw": False}
        if option.action == "speech_order":
            return {"action": "speech_order", "start": option.targets[0],
                    "direction": "clockwise"}
        if option.action == "wolf_chat":
            target = self.rng.choice(option.targets) if option.targets else None
            history = [e for e in context.events if e.event_type == "WolfChatMessage" and e.day == context.public.day]
            reply = f"我看过队友本轮的{len(history)}条意见。" if history else "先给出我的刀口建议。"
            return {"action": "wolf_chat", "target": target,
                    "text": reply + (f"建议刀{target}号，白天围绕真实票型解释。" if target else "今晚没有合法刀口。")}
        if option.action == "witch":
            if option.save_targets and self.rng.random() < 0.5:
                return {"action": "witch", "save_target": option.save_targets[0]}
            if option.targets and self.rng.random() < 0.5:
                return {"action": "witch", "poison_target": self.rng.choice(option.targets)}
            return {"action": "witch"}
        if option.action == "speech":
            others = [seat for seat in context.public.alive if seat != context.profile.seat]
            suspect = self.rng.choice(others) if others else context.profile.seat
            previous = dict(context.public.previous_day_votes)
            detail = (f"上一轮{suspect}号投给{previous[suspect]}号。" if suspect in previous
                      else f"{suspect}号目前没有可核对的上一轮票。")
            text = f"我是{context.profile.seat}号{context.profile.name}。我关注{suspect}号，{detail}今天要看他如何解释这个判断。"
            if nudge:
                text += f" {nudge}"
            return {"action": "speech", "text": text}
        if option.targets:
            return {"action": option.action, "target": self.rng.choice(option.targets)}
        if option.allow_pass:
            return {"action": option.action, "target": None}
        raise ValueError("No legal target")
