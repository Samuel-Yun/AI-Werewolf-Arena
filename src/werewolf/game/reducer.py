"""The only mutation path for canonical state, shared by live play and replay."""

from werewolf.game.errors import ReplayError
from werewolf.game.events import Event, EventType
from werewolf.game.phases import Phase, TRANSITIONS
from werewolf.game.state import GameState, NightActions, Potions, PublicPlayer
from werewolf.roles import RoleName, Team


def apply_event(state: GameState, event: Event) -> None:
    if event.event_id != state.event_count + 1:
        raise ReplayError("Non-contiguous event sequence")
    if event.phase != state.public.phase or event.day != state.public.day:
        raise ReplayError("Event phase/day does not match canonical state")
    payload = event.payload
    kind = event.event_type
    public, secret = state.public, state.secret
    match kind:
        case EventType.GAME_STARTED:
            if public.players or state.event_count:
                raise ReplayError("GameStarted must be the first event")
            public.players = {p.seat: PublicPlayer(p.seat, p.name) for p in state.profiles}
            secret.roles = {int(seat): RoleName(role) for seat, role in payload["roles"].items()}
            secret.potions = {s: Potions() for s, r in secret.roles.items() if r == RoleName.WITCH}
        case EventType.PHASE_CHANGED:
            next_phase = Phase(payload["next"])
            if next_phase not in TRANSITIONS[public.phase]:
                raise ReplayError(f"Illegal transition {public.phase} -> {next_phase}")
            public.phase = next_phase
            state.submitted = set()
            if event.phase == Phase.DEATH_SKILL:
                secret.death_skill_resume = None
        case EventType.NIGHT_STARTED:
            public.day += 1
            public.votes = {}
            secret.night = NightActions()
            secret.night_deaths = []
            secret.night_causes = {}
        case EventType.WOLF_VOTE_SUBMITTED:
            secret.night.wolf_votes[event.actor] = event.target
            state.submitted.add(event.actor)
        case EventType.HYBRID_MODEL_CHOSEN:
            from werewolf.roles.alignment import alignment_for_model
            secret.hybrid_models[event.actor] = event.target
            secret.hybrid_teams[event.actor] = alignment_for_model(state, event.target)
            state.submitted.add(event.actor)
        case EventType.WOLF_KILL_SELECTED:
            secret.night.wolf_target = event.target
        case EventType.SEER_CHECK_SELECTED:
            secret.night.seer_checks[event.actor] = event.target
            state.submitted.add(event.actor)
        case EventType.SEER_CHECKED:
            secret.check_history.setdefault(event.actor, []).append(
                {"day": public.day, "target": event.target, "result": payload["result"]}
            )
        case EventType.WITCH_ACTION_SELECTED:
            secret.night.witch_actions[event.actor] = dict(payload)
            state.submitted.add(event.actor)
        case EventType.WITCH_USED_ANTIDOTE:
            secret.potions[event.actor].antidote -= 1
        case EventType.WITCH_USED_POISON:
            secret.potions[event.actor].poison -= 1
        case EventType.DEATH_CAUSE_RECORDED:
            secret.death_causes[event.target] = list(payload["causes"])
        case EventType.HUNTER_TRIGGERED:
            secret.death_skill_queue.append(event.actor)
        case EventType.DEATH_SKILLS_STARTED:
            secret.death_skill_resume = Phase(payload["resume"])
        case EventType.HUNTER_SHOT:
            if not secret.death_skill_queue or secret.death_skill_queue[0] != event.actor:
                raise ReplayError("Hunter is not at the head of the death-skill queue")
            secret.death_skill_queue.pop(0)
            secret.hunter_spent.add(event.actor)
            public.players[event.actor].revealed_role = RoleName.HUNTER
        case EventType.IDIOT_REVEALED:
            public.players[event.target].revealed_role = RoleName.IDIOT
            public.players[event.target].can_vote = False
        case EventType.NIGHT_RESOLVED:
            secret.night_deaths = list(payload["deaths"])
            secret.night_causes = {int(s): list(c) for s, c in payload.get("causes", {}).items()}
        case EventType.PLAYER_DIED:
            player = public.players[event.target]
            if not player.alive:
                raise ReplayError("A player cannot die twice")
            player.alive = False
            player.can_vote = False
            public.dead.add(event.target)
        case EventType.PLAYER_SPOKE:
            public.speeches.append({"day": public.day, "seat": event.actor, "text": payload["text"]})
            state.submitted.add(event.actor)
        case EventType.PLAYER_SKIPPED:
            public.speeches.append({"day": public.day, "seat": event.actor, "text": "[跳过发言]"})
            state.submitted.add(event.actor)
        case EventType.VOTE_SUBMITTED:
            public.votes[event.actor] = event.target
            state.submitted.add(event.actor)
        case EventType.GAME_ENDED:
            public.winner = Team(payload["winner"])
        case EventType.WINNERS_DETERMINED:
            secret.winning_players = list(payload["seats"])
        case EventType.DAY_STARTED | EventType.PLAYER_EXILED | EventType.EXILE_SKIPPED:
            pass
        case EventType.ACTION_REJECTED | EventType.FALLBACK_USED | EventType.DIRECTOR_DECISION:
            pass
    state.event_count = event.event_id
