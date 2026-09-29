import json
from pathlib import Path

from pydantic import TypeAdapter

from werewolf.config import BoardConfig, PlayerConfig
from werewolf.game.errors import ReplayError
from werewolf.game.events import Event, EventType
from werewolf.game.reducer import apply_event
from werewolf.game.state import GameState
from werewolf.game.validation import validate_game_state
from werewolf.storage.game_store import state_document, transcript, director_transcript


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
        TypeAdapter(GameState).validate_python(document)
        actual = json.loads(json.dumps(state_document(state)))
        # Older logs predate additive public history and sheriff fields. Compare their
        # recorded fields while retaining a full comparison for new logs.
        def recorded(actual_value, saved_value):
            if isinstance(saved_value, dict):
                if not isinstance(actual_value, dict) or not saved_value.keys() <= actual_value.keys():
                    raise ReplayError("Saved state has missing or altered fields")
                return {key: recorded(actual_value[key], value) for key, value in saved_value.items()}
            if isinstance(saved_value, list):
                if not isinstance(actual_value, list) or len(actual_value) != len(saved_value):
                    raise ReplayError("Saved state list length differs from replay")
                return [recorded(a, b) for a, b in zip(actual_value, saved_value)]
            return actual_value
        if recorded(actual, document) != document:
            raise ReplayError("Replayed state differs from saved result")
    public_path = path / "public_transcript.txt"
    if public_path.exists():
        if public_path.read_text(encoding="utf-8") != transcript(events, state):
            raise ReplayError("Public transcript differs from event log")
        director_path = path / "transcript.txt"
        if not director_path.exists() or director_path.read_text(encoding="utf-8") != director_transcript(events, state):
            raise ReplayError("Director transcript differs from event log")
    return state
