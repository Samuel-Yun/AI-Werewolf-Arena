import json
from dataclasses import asdict
from pathlib import Path

from werewolf.game.engine import GameEngine
from werewolf.game.events import Event, EventType as E, Visibility
from werewolf.game.state import GameState


def state_document(state: GameState) -> dict:
    public = asdict(state.public)
    public["dead"] = sorted(state.public.dead)
    public["sheriff_withdrawn"] = sorted(state.public.sheriff_withdrawn)
    secret = asdict(state.secret)
    secret["hunter_spent"] = sorted(state.secret.hunter_spent)
    return {
        "board": state.board.model_dump(mode="json"),
        "profiles": [p.model_dump(mode="json") for p in state.profiles],
        "seed": state.seed, "public": public, "secret": secret,
        "submitted": sorted(state.submitted), "event_count": state.event_count,
    }


def transcript(events: tuple[Event, ...], state: GameState) -> str:
    lines = []
    names = {p.seat: p.name for p in state.profiles}
    for event in events:
        if event.visibility != Visibility.PUBLIC:
            continue
        match event.event_type:
            case E.DAY_STARTED:
                lines.extend([f"\nDay {event.day}", f"Deaths: {event.payload['deaths']}"])
            case E.SHERIFF_SIGNUP:
                lines.append(f"Sheriff signup: {event.actor} -> {event.payload['run']}")
            case E.SHERIFF_WITHDREW:
                lines.append(f"Sheriff withdrawal: {event.actor} -> {event.payload['withdraw']}")
            case E.SHERIFF_BALLOT:
                lines.append(f"Sheriff ballot: {event.actor} -> {event.target}")
            case E.SHERIFF_BALLOTS_REVEALED:
                lines.extend(f"Sheriff ballot: {seat} -> {target}" for seat, target in event.payload["ballots"].items())
            case E.SHERIFF_PK_STARTED:
                lines.append(f"Sheriff PK: {event.payload['candidates']}")
            case E.SHERIFF_ELECTED:
                lines.append(f"Sheriff: {event.target if event.target is not None else 'none'}")
            case E.SPEECH_ORDER_CHOSEN:
                lines.append(f"Speech order: {event.payload['order']}")
            case E.BADGE_TRANSFERRED:
                lines.append(f"Badge: {event.actor} -> {event.target if event.target is not None else 'destroyed'}")
            case E.PLAYER_SPOKE:
                lines.append(f"{event.actor}号 {names[event.actor]}：{event.payload['text']}")
            case E.PLAYER_SKIPPED:
                lines.append(f"{event.actor}号 {names[event.actor]}：[跳过发言]")
            case E.VOTE_SUBMITTED:
                lines.append(f"Vote: {event.actor} -> {event.target if event.target is not None else 'abstain'}")
            case E.VOTES_REVEALED:
                lines.extend(f"Vote: {seat} -> {target if target is not None else 'abstain'}"
                             for seat, target in event.payload["votes"].items())
            case E.EXILE_TALLY:
                lines.append(f"Exile tally (half-votes): {event.payload['totals']}")
            case E.PLAYER_EXILED:
                lines.append(f"Exiled: {event.target}")
            case E.PLAYER_DIED:
                if event.phase != "dawn":
                    lines.append(f"Died: {event.target}")
            case E.EXILE_SKIPPED:
                lines.append("No exile")
            case E.IDIOT_REVEALED:
                lines.append(f"Idiot revealed: {event.target}; survives, loses voting rights")
            case E.HUNTER_SHOT:
                lines.append(f"Hunter: {event.actor} -> {event.target if event.target is not None else 'holds fire'}")
            case E.GAME_ENDED:
                lines.append(f"Winner: {event.payload['winner']}")
    return "\n".join(lines) + "\n"


def director_transcript(events: tuple[Event, ...], state: GameState) -> str:
    names = {p.seat: p.name for p in state.profiles}
    roles = events[0].payload["roles"] if events else {}
    lines = ["导演复盘（含剧透）", "真实身份："]
    lines.extend(f"{seat}号 {names[int(seat)]}: {role}" for seat, role in sorted(roles.items(), key=lambda x: int(x[0])))
    for e in events:
        kind, p = e.event_type, e.payload
        detail = None
        match kind:
            case E.NIGHT_STARTED:
                detail = f"第{e.day}夜开始"
            case E.HYBRID_MODEL_CHOSEN:
                detail = f"混血儿{e.actor}选榜样{e.target}；隐藏归属={state.secret.hybrid_teams.get(e.actor)}"
            case E.WOLF_CHAT_MESSAGE:
                detail = f"狼聊第{p['round']}轮 {e.actor}号建议刀{e.target}：{p['text']}"
            case E.WOLF_VOTE_SUBMITTED:
                detail = f"狼人{e.actor}投刀{e.target}"
            case E.WOLF_KILL_SELECTED:
                detail = f"最终刀口={e.target}"
            case E.SEER_CHECK_SELECTED:
                detail = f"预言家{e.actor}查验{e.target}"
            case E.SEER_CHECKED:
                detail = f"查验结果 {e.actor}验{e.target}={p['result']}"
            case E.WITCH_WINDOW_OPENED:
                detail = f"女巫{e.actor}行动窗口：可见刀口={e.target}，解药={p['antidote']}，毒药={p['poison']}"
            case E.WITCH_ACTION_SELECTED:
                detail = f"女巫{e.actor}选择：救={p['save_target']}，毒={p['poison_target']}"
            case E.WITCH_USED_ANTIDOTE:
                detail = f"女巫{e.actor}对{e.target}使用解药"
            case E.WITCH_USED_POISON:
                detail = f"女巫{e.actor}对{e.target}使用毒药"
            case E.NIGHT_RESOLVED:
                detail = f"夜间结算：死亡={p['deaths']}，原因={p['causes']}"
            case E.DAY_STARTED:
                detail = f"法官宣布第{e.day}天，夜间死亡={p['deaths']}"
            case E.SHERIFF_SIGNUP:
                detail = f"{e.actor}号{'上警' if p['run'] else '不上警'}"
            case E.SHERIFF_WITHDREW:
                detail = f"{e.actor}号{'退水' if p['withdraw'] else '继续竞选'}"
            case E.SHERIFF_BALLOT:
                detail = f"警下投票 {e.actor}->{e.target}（暂不公开）"
            case E.SHERIFF_BALLOTS_REVEALED:
                detail = f"警徽票型公布={p['ballots']}"
            case E.SHERIFF_PK_STARTED:
                detail = f"警长PK候选={p['candidates']}，票型={p['tally']}"
            case E.SHERIFF_ELECTED:
                detail = f"警长={e.target}，原因={p['reason']}，票型={p.get('tally', {})}"
            case E.SPEECH_ORDER_CHOSEN:
                detail = f"警长{e.actor}选择发言顺序：起点={p['start']}，方向={p['direction']}，顺序={p['order']}"
            case E.PLAYER_SPOKE:
                detail = f"{e.actor}号发言：{p['text']}"
            case E.PLAYER_SKIPPED:
                detail = f"{e.actor}号跳过发言"
            case E.VOTE_SUBMITTED:
                detail = f"放逐投票 {e.actor}->{e.target}（暂不公开）"
            case E.VOTES_REVEALED:
                detail = f"放逐票型公布={p['votes']}"
            case E.EXILE_TALLY:
                detail = f"放逐计票（半票单位）：权重={p['weights']}，总票={p['totals']}，结果={p['target']}"
            case E.PLAYER_EXILED:
                detail = f"放逐目标={e.target}"
            case E.EXILE_SKIPPED:
                detail = "平票或弃票，无人放逐"
            case E.IDIOT_REVEALED:
                detail = f"白痴{e.target}翻牌免死，失去投票权"
            case E.DEATH_CAUSE_RECORDED:
                detail = f"{e.target}号死亡原因={p['causes']}"
            case E.PLAYER_DIED:
                detail = f"{e.target}号实际死亡"
            case E.HUNTER_TRIGGERED:
                detail = f"猎人{e.actor}获得开枪机会"
            case E.HUNTER_SHOT:
                detail = f"猎人{e.actor}{'不开枪' if e.target is None else f'开枪射{e.target}号'}"
            case E.BADGE_TRANSFERRED:
                detail = f"警徽由{e.actor}号{'撕毁' if e.target is None else f'移交给{e.target}号'}"
            case E.WINNERS_DETERMINED:
                detail = f"个人胜者={p['seats']}"
            case E.GAME_ENDED:
                detail = f"Winner: {p['winner']}"
        if detail is not None:
            lines.append(f"#{e.event_id} [第{e.day}天/{e.phase}] {detail}")
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class GameStore:
    def __init__(self, root: Path):
        self.root = root

    def save(self, engine: GameEngine, *, diagnostic: dict | None = None, run_info: dict | None = None) -> Path:
        path = self.root / engine.game_id
        path.mkdir(parents=True, exist_ok=False)
        state = engine.state
        # JSONL turns integer payload keys into strings. Render both transcripts
        # from the same canonical representation that Replay later reads.
        events = tuple(Event.model_validate_json(event.model_dump_json()) for event in engine.events)
        write_json(path / "metadata.json", {
            "schema_version": 1, "game_id": engine.game_id, "seed": state.seed,
            "board": state.board.model_dump(mode="json"),
            "players": [p.model_dump(mode="json") for p in state.profiles],
            **({"run": run_info} if run_info is not None else {}),
        })
        with (path / "events.jsonl").open("w", encoding="utf-8") as stream:
            for event in events:
                stream.write(event.model_dump_json() + "\n")
        (path / "transcript.txt").write_text(director_transcript(events, state), encoding="utf-8")
        (path / "public_transcript.txt").write_text(transcript(events, state), encoding="utf-8")
        write_json(path / "result.json", {
            "game_id": engine.game_id, "seed": state.seed, "completed": engine.ended,
            "winner": state.public.winner, "turns": state.public.day,
            "final_state": state_document(state),
            **({"run": run_info} if run_info is not None else {}),
        })
        if diagnostic is not None:
            write_json(path / "diagnostic.json", diagnostic)
        return path
