import json
from pathlib import Path

from pydantic import TypeAdapter

from werewolf.config import BoardConfig, PlayerConfig
from werewolf.game.errors import ReplayError
from werewolf.game.events import Event, EventType
from werewolf.game.reducer import apply_event
from werewolf.game.state import GameState
from werewolf.game.validation import validate_game_state
from werewolf.storage.game_store import state_document


def replay_events(events: tuple[Event, ...], *, require_complete: bool = True) -> GameState:
    if not events or events[0].event_type != EventType.GAME_STARTED:
        raise ReplayError("Replay requires GameStarted")
    first = events[0]
    payload = first.payload
    state = GameState(
        BoardConfig.model_validate(payload["board"]),
        tuple(PlayerConfig.model_validate(p) for p in payload["players"]), payload["seed"],
    )
    for event in events:
        if event.game_id != first.game_id:
            raise ReplayError("Mixed game IDs")
        apply_event(state, event)
        validate_game_state(state)
    from werewolf.game.phases import Phase
    if require_complete and state.public.phase != Phase.ENDED:
        raise ReplayError("Incomplete event log")
    return state


def replay_directory(path: Path) -> GameState:
    events = tuple(Event.model_validate_json(line)
                   for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()
                   if line.strip())
    state = replay_events(events)
    result_path = path / "result.json"
    if result_path.exists():
        document = json.loads(result_path.read_text(encoding="utf-8"))["final_state"]
        expected = json.loads(json.dumps(state_document(TypeAdapter(GameState).validate_python(document))))
        actual = json.loads(json.dumps(state_document(state)))
        if actual != expected:
            raise ReplayError("Replayed state differs from saved result")
    return state
