from copy import deepcopy
from datetime import datetime, timezone
from random import Random
from uuid import uuid4

from werewolf.config import BoardConfig, PlayerConfig, default_players
from werewolf.game.actions import Action, parse_action
from werewolf.game.errors import GameLimitExceeded
from werewolf.game.events import Event, EventType as E, Visibility as V
from werewolf.game.phases import Phase
from werewolf.game.reducer import apply_event
from werewolf.game.resolver import plurality
from werewolf.game.rules import actors_for_phase, legal_actions, validate_action
from werewolf.game.state import GameState
from werewolf.game.validation import validate_game_state
from werewolf.roles import RoleName
from werewolf.roles.skills import hunter_can_shoot


class GameEngine:
    """Accept intents; own canonical state; advance an explicit phase machine."""

    def __init__(self, board: BoardConfig, seed: int,
                 players: tuple[PlayerConfig, ...] | None = None,
                 *, role_assignments: dict[int, RoleName] | None = None,
                 game_id: str | None = None):
        players = players if players is not None else default_players(board.players)
        if sorted(p.seat for p in players) != list(range(1, board.players + 1)):
            raise ValueError("Players must uniquely occupy seats 1..board.players")
        self.game_id = game_id or uuid4().hex
        self.rng = Random(seed)
        self._state = GameState(deepcopy(board), tuple(sorted(players, key=lambda p: p.seat)), seed)
        self._events: list[Event] = []
        deck = [role for role, count in sorted(board.roles.items()) for _ in range(count)]
        self.rng.shuffle(deck)
        roles = role_assignments if role_assignments is not None else dict(enumerate(deck, 1))
        self.emit(E.GAME_STARTED, payload={
            "seed": seed, "board": board.model_dump(mode="json"),
            "players": [p.model_dump(mode="json") for p in self._state.profiles],
            "roles": {str(s): r for s, r in roles.items()},
        })

    @property
    def state(self) -> GameState:
        """A detached snapshot for trusted controllers, never an Agent argument."""
        return deepcopy(self._state)

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(event.model_copy(deep=True) for event in self._events)

    @property
    def ended(self) -> bool:
        return self._state.public.phase == Phase.ENDED

    def emit(self, kind: E, *, actor: int | None = None, target: int | None = None,
             visibility: V = V.ENGINE_ONLY, recipients: tuple[int, ...] = (),
             payload: dict | None = None) -> None:
        if len(self._events) >= self._state.board.max_events:
            raise GameLimitExceeded("MAX_EVENTS exceeded")
        event = Event(
            event_id=len(self._events) + 1, game_id=self.game_id,
            day=self._state.public.day, phase=self._state.public.phase,
            event_type=kind, actor=actor, target=target, visibility=visibility,
            recipients=recipients, payload=deepcopy(payload or {}),
            timestamp=datetime.now(timezone.utc),
        )
        apply_event(self._state, event)
        validate_game_state(self._state)
        self._events.append(event)

    def transition(self, phase: Phase) -> None:
        self.emit(E.PHASE_CHANGED, payload={"next": phase})

    def next_actor(self) -> int | None:
        return next((s for s in actors_for_phase(self._state) if legal_actions(self._state, s)), None)

    def validate(self, seat: int, raw: object) -> Action:
        action = parse_action(raw)
        validate_action(self._state, seat, action)
        return action

    def submit(self, seat: int, raw: object) -> None:
        action = self.validate(seat, raw)
        match action.action:
            case "wolf_chat":
                self.emit(E.WOLF_CHAT_MESSAGE, actor=seat, target=action.target,
                          visibility=V.PRIVATE_WOLVES,
                          payload={"text": action.text, "round": self._state.secret.wolf_chat_round})
            case "sheriff_signup":
                self.emit(E.SHERIFF_SIGNUP, actor=seat, visibility=V.PUBLIC, payload={"run": action.run})
            case "sheriff_withdraw":
                self.emit(E.SHERIFF_WITHDREW, actor=seat, visibility=V.PUBLIC,
                          payload={"withdraw": action.withdraw})
            case "sheriff_vote":
                self.emit(E.SHERIFF_BALLOT, actor=seat, target=action.target)
            case "speech_order":
                seats = list(range(1, self._state.board.players + 1))
                step = 1 if action.direction == "clockwise" else -1
                cursor = action.start - 1
                order = []
                for _ in seats:
                    current = seats[cursor]
                    if current in self._state.public.alive and current != seat:
                        order.append(current)
                    cursor = (cursor + step) % len(seats)
                order.append(seat)
                self.emit(E.SPEECH_ORDER_CHOSEN, actor=seat, visibility=V.PUBLIC,
                          payload={"start": action.start, "direction": action.direction, "order": order})
            case "badge_transfer":
                self.emit(E.BADGE_TRANSFERRED, actor=seat, target=action.target, visibility=V.PUBLIC)
            case "wolf_kill":
                self.emit(E.WOLF_VOTE_SUBMITTED, actor=seat, target=action.target,
                          visibility=V.PRIVATE_WOLVES)
            case "hybrid_choose":
                self.emit(E.HYBRID_MODEL_CHOSEN, actor=seat, target=action.target,
                          visibility=V.PRIVATE_PLAYER, recipients=(seat,))
            case "seer_check":
                self.emit(E.SEER_CHECK_SELECTED, actor=seat, target=action.target,
                          visibility=V.PRIVATE_PLAYER, recipients=(seat,))
            case "witch":
                self.emit(E.WITCH_ACTION_SELECTED, actor=seat, visibility=V.PRIVATE_PLAYER,
                          recipients=(seat,), payload={"save_target": action.save_target,
                                                      "poison_target": action.poison_target})
            case "speech":
                self.emit(E.PLAYER_SPOKE, actor=seat, visibility=V.PUBLIC,
                          payload={"text": action.text})
            case "skip_speech":
                self.emit(E.PLAYER_SKIPPED, actor=seat, visibility=V.PUBLIC)
            case "vote":
                self.emit(E.VOTE_SUBMITTED, actor=seat, target=action.target)
            case "hunter_shot":
                self.emit(E.HUNTER_SHOT, actor=seat, target=action.target, visibility=V.PUBLIC)
                if action.target is not None:
                    self.kill(action.target, ["hunter_shot"])

    def kill(self, target: int, causes: list[str]) -> None:
        self.emit(E.DEATH_CAUSE_RECORDED, target=target, payload={"causes": causes})
        self.emit(E.PLAYER_DIED, target=target, visibility=V.PUBLIC)
        if self._state.secret.roles[target] == RoleName.HUNTER and hunter_can_shoot(self._state.board, causes):
            self.emit(E.HUNTER_TRIGGERED, actor=target)

    def advance(self) -> None:
        """Execute one automatic phase step; callers supply actions when needed."""
        from werewolf.game.phase_handlers import HANDLERS

        if self.ended or self.next_actor() is not None:
            return
        HANDLERS[self._state.public.phase](self)

    def resolve_wolf_vote(self) -> None:
        target = plurality(self._state.secret.night.wolf_votes, self.rng, random_tie=True)
        self.emit(E.WOLF_KILL_SELECTED, target=target, visibility=V.PRIVATE_WOLVES)
