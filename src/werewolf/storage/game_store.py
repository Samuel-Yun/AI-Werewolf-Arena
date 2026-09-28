import json
from dataclasses import asdict
from pathlib import Path

from werewolf.game.engine import GameEngine
from werewolf.game.events import Event, EventType as E, Visibility
from werewolf.game.state import GameState


def state_document(state: GameState) -> dict:
    public = asdict(state.public)
    public["dead"] = sorted(state.public.dead)
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
            case E.PLAYER_SPOKE:
                lines.append(f"{event.actor}号 {names[event.actor]}：{event.payload['text']}")
            case E.PLAYER_SKIPPED:
                lines.append(f"{event.actor}号 {names[event.actor]}：[跳过发言]")
            case E.VOTE_SUBMITTED:
                lines.append(f"Vote: {event.actor} -> {event.target if event.target is not None else 'abstain'}")
            case E.PLAYER_EXILED:
                lines.append(f"Exiled: {event.target}")
            case E.EXILE_SKIPPED:
                lines.append("No exile")
            case E.IDIOT_REVEALED:
                lines.append(f"Idiot revealed: {event.target}; survives, loses voting rights")
            case E.HUNTER_SHOT:
                lines.append(f"Hunter: {event.actor} -> {event.target if event.target is not None else 'holds fire'}")
            case E.GAME_ENDED:
                lines.append(f"Winner: {event.payload['winner']}")
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
        write_json(path / "metadata.json", {
            "schema_version": 1, "game_id": engine.game_id, "seed": state.seed,
            "board": state.board.model_dump(mode="json"),
            "players": [p.model_dump(mode="json") for p in state.profiles],
            **({"run": run_info} if run_info is not None else {}),
        })
        with (path / "events.jsonl").open("w", encoding="utf-8") as stream:
            for event in engine.events:
                stream.write(event.model_dump_json() + "\n")
        (path / "transcript.txt").write_text(transcript(engine.events, state), encoding="utf-8")
        write_json(path / "result.json", {
            "game_id": engine.game_id, "seed": state.seed, "completed": engine.ended,
            "winner": state.public.winner, "turns": state.public.day,
            "final_state": state_document(state),
            **({"run": run_info} if run_info is not None else {}),
        })
        if diagnostic is not None:
            write_json(path / "diagnostic.json", diagnostic)
        return path
