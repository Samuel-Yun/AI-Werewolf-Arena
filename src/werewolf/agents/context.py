import json

from pydantic import BaseModel, ConfigDict

from werewolf.config import PlayerConfig
from werewolf.game.events import Event, EventType, Visibility
from werewolf.game.phases import Phase
from werewolf.game.rules import LegalAction, legal_actions
from werewolf.game.state import GameState
from werewolf.roles import ROLES, RoleName, Team
from werewolf.roles.alignment import effective_team


class FrozenView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PublicPlayerView(FrozenView):
    seat: int
    name: str
    alive: bool
    can_vote: bool
    revealed_role: RoleName | None


class SpeechView(FrozenView):
    day: int
    seat: int
    text: str


class PublicView(FrozenView):
    day: int
    phase: Phase
    players: tuple[PublicPlayerView, ...]
    speeches: tuple[SpeechView, ...]
    votes: tuple[tuple[int, int | None], ...]
    previous_day_votes: tuple[tuple[int, int | None], ...] = ()
    sheriff: int | None = None
    sheriff_signup: tuple[tuple[int, bool], ...] = ()
    sheriff_ballots: tuple[tuple[int, int | None], ...] = ()
    sheriff_pk_candidates: tuple[int, ...] = ()
    speech_order: tuple[int, ...] = ()
    deaths: tuple[tuple[int, int, str], ...] = ()
    exiles: tuple[tuple[int, int], ...] = ()
    winner: Team | None

    @property
    def alive(self) -> tuple[int, ...]:
        return tuple(p.seat for p in self.players if p.alive)


class CheckView(FrozenView):
    day: int
    target: int
    result: Team


class VisibleEvent(FrozenView):
    visibility: Visibility
    day: int
    event_type: EventType
    actor: int | None
    target: int | None
    payload_json: str


class OwnInformation(FrozenView):
    role: RoleName
    team: Team | None
    wolf_teammates: tuple[int, ...] = ()
    checks: tuple[CheckView, ...] = ()
    antidote: int | None = None
    poison: int | None = None
    wolf_victim: int | None = None
    hybrid_model: int | None = None
    wolf_chat_round: int | None = None


class PlayerBelief(FrozenView):
    """A player's opinion, never canonical role or victory data."""
    seat: int
    statement: str


class AgentContext(FrozenView):
    profile: PlayerConfig
    public: PublicView
    own: OwnInformation
    legal_actions: tuple[LegalAction, ...]
    events: tuple[VisibleEvent, ...]
    memories: tuple[str, ...] = ()
    beliefs: tuple[PlayerBelief, ...] = ()
    expert_examples: tuple[str, ...] = ()


def build_context_for_player(state: GameState, events: tuple[Event, ...], seat: int,
                             *, memories: tuple[str, ...] = ()) -> AgentContext:
    if seat not in state.public.players:
        raise ValueError("Unknown player")
    role = state.secret.roles[seat]
    death_id = next((e.event_id for e in events
                     if e.event_type == EventType.PLAYER_DIED and e.target == seat), None)
    visible = []
    for event in events:
        if event.event_id > state.event_count:
            break
        private_allowed = death_id is None or event.event_id <= death_id
        allowed = event.visibility == Visibility.PUBLIC
        allowed |= private_allowed and event.visibility == Visibility.PRIVATE_PLAYER and seat in event.recipients
        allowed |= private_allowed and event.visibility == Visibility.PRIVATE_WOLVES and role == RoleName.WEREWOLF
        if allowed:
            visible.append(VisibleEvent(
                visibility=event.visibility, day=event.day, event_type=event.event_type, actor=event.actor, target=event.target,
                payload_json=json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
            ))
    return AgentContext(
        profile=next(p for p in state.profiles if p.seat == seat),
        public=PublicView(
            day=state.public.day, phase=state.public.phase,
            players=tuple(PublicPlayerView(**vars(p)) for _, p in sorted(state.public.players.items())),
            speeches=tuple(SpeechView(**s) for s in state.public.speeches),
            votes=tuple(sorted(state.public.votes.items())),
            previous_day_votes=tuple(sorted(state.public.previous_day_votes.items())),
            sheriff=state.public.sheriff,
            sheriff_signup=tuple(sorted(state.public.sheriff_signup.items())),
            sheriff_ballots=tuple(sorted(state.public.sheriff_ballots.items())),
            sheriff_pk_candidates=state.public.sheriff_pk_candidates,
            speech_order=state.public.speech_order,
            deaths=tuple((d["day"], d["seat"], str(d["phase"])) for d in state.public.public_deaths),
            exiles=tuple((d["day"], d["seat"]) for d in state.public.exiles),
            winner=state.public.winner,
        ),
        own=OwnInformation(
            role=role, team=effective_team(state, seat)
                if role != RoleName.HYBRID or state.board.hybrid.reveal_alignment else None,
            hybrid_model=state.secret.hybrid_models.get(seat),
            wolf_chat_round=state.secret.wolf_chat_round
                if role == RoleName.WEREWOLF and state.public.phase == Phase.WOLF_CHAT else None,
            wolf_teammates=tuple(s for s, r in sorted(state.secret.roles.items())
                                 if r == RoleName.WEREWOLF) if role == RoleName.WEREWOLF else (),
            checks=tuple(CheckView(**c) for c in state.secret.check_history.get(seat, [])),
            antidote=state.secret.potions[seat].antidote if role == RoleName.WITCH else None,
            poison=state.secret.potions[seat].poison if role == RoleName.WITCH else None,
            wolf_victim=state.secret.night.wolf_target
                if role == RoleName.WITCH and state.public.players[seat].alive and state.public.phase == Phase.WITCH
                and (state.secret.potions[seat].antidote or state.board.witch.see_victim_without_antidote) else None,
        ),
        legal_actions=legal_actions(state, seat), events=tuple(visible), memories=memories,
    )
