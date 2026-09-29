from dataclasses import dataclass

from werewolf.game.actions import Action, WitchAction, SpeechOrderAction
from werewolf.game.errors import IllegalAction
from werewolf.game.phases import Phase
from werewolf.game.state import GameState
from werewolf.roles import ROLES, RoleName


@dataclass(frozen=True)
class LegalAction:
    action: str
    targets: tuple[int, ...] = ()
    allow_pass: bool = False
    save_targets: tuple[int, ...] = ()


def candidates(state: GameState) -> tuple[int, ...]:
    return tuple(s for s, run in sorted(state.public.sheriff_signup.items())
                 if run and s not in state.public.sheriff_withdrawn and s in state.public.alive)


def police_down(state: GameState) -> tuple[int, ...]:
    # Signing up removes the right to vote in this election, even after withdrawal.
    return tuple(s for s in state.public.alive if not state.public.sheriff_signup.get(s, False))


def actors_for_phase(state: GameState) -> tuple[int, ...]:
    public, secret = state.public, state.secret
    phase = public.phase
    if phase == Phase.HYBRID_CHOOSE:
        return tuple(s for s in public.alive if secret.roles[s] == RoleName.HYBRID)
    if phase == Phase.WOLF_CHAT:
        return tuple(s for s in public.alive if secret.roles[s] == RoleName.WEREWOLF)
    if phase == Phase.DEATH_SKILL:
        return tuple(secret.death_skill_queue[:1])
    if phase == Phase.BADGE_TRANSFER:
        return (secret.badge_transfer_pending,) if secret.badge_transfer_pending is not None else ()
    if phase in {Phase.WOLF, Phase.SEER, Phase.WITCH}:
        action = {Phase.WOLF: "wolf_kill", Phase.SEER: "seer_check", Phase.WITCH: "witch"}[phase]
        return tuple(s for s in public.alive if ROLES[secret.roles[s]].night_action == action)
    if phase == Phase.SHERIFF_SIGNUP:
        return public.alive
    if phase in {Phase.SHERIFF_SPEECH, Phase.SHERIFF_WITHDRAW}:
        return candidates(state)
    if phase in {Phase.SHERIFF_VOTE, Phase.SHERIFF_PK_VOTE}:
        return police_down(state)
    if phase == Phase.SHERIFF_PK_SPEECH:
        return tuple(s for s in public.sheriff_pk_candidates if s in public.alive)
    if phase == Phase.SPEECH_ORDER:
        return (public.sheriff,) if public.sheriff is not None else ()
    if phase == Phase.DISCUSSION:
        return public.speech_order or public.alive
    if phase == Phase.VOTING:
        return tuple(s for s in public.alive if public.players[s].can_vote)
    return ()


def legal_actions(state: GameState, seat: int) -> tuple[LegalAction, ...]:
    if seat not in actors_for_phase(state) or seat in state.submitted:
        return ()
    phase = state.public.phase
    if phase in {Phase.WOLF_CHAT, Phase.SHERIFF_SPEECH, Phase.SHERIFF_PK_SPEECH, Phase.DISCUSSION}:
        first = next((s for s in actors_for_phase(state) if s not in state.submitted), None)
        if seat != first:
            return ()
    targets = tuple(s for s in state.public.alive if s != seat)
    if phase == Phase.HYBRID_CHOOSE:
        if state.public.day != 1 or seat in state.secret.hybrid_models:
            return ()
        return (LegalAction("hybrid_choose", targets),)
    if phase == Phase.WOLF_CHAT:
        targets = tuple(s for s in targets if state.secret.roles[s] != RoleName.WEREWOLF)
        return (LegalAction("wolf_chat", targets, True),)
    if phase == Phase.WOLF:
        targets = tuple(s for s in targets if state.secret.roles[s] != RoleName.WEREWOLF)
        return (LegalAction("wolf_kill", targets),) if targets else ()
    if phase == Phase.SEER:
        return (LegalAction("seer_check", targets),) if targets else ()
    if phase == Phase.WITCH:
        potions = state.secret.potions[seat]
        victim = state.secret.night.wolf_target
        self_save = state.board.witch.self_save
        can_save = potions.antidote > 0 and victim is not None
        can_save &= victim != seat or self_save == "always" or (self_save == "first_night" and state.public.day == 1)
        return (LegalAction("witch", targets if potions.poison else (), True,
                            (victim,) if can_save else ()),)
    if phase == Phase.SHERIFF_SIGNUP:
        return (LegalAction("sheriff_signup"),)
    if phase == Phase.SHERIFF_WITHDRAW:
        return (LegalAction("sheriff_withdraw"),)
    if phase in {Phase.SHERIFF_SPEECH, Phase.SHERIFF_PK_SPEECH, Phase.DISCUSSION}:
        return (LegalAction("speech"), LegalAction("skip_speech"))
    if phase in {Phase.SHERIFF_VOTE, Phase.SHERIFF_PK_VOTE}:
        eligible = state.public.sheriff_pk_candidates if phase == Phase.SHERIFF_PK_VOTE else candidates(state)
        return (LegalAction("sheriff_vote", eligible, True),)
    if phase == Phase.SPEECH_ORDER:
        return (LegalAction("speech_order", targets),)
    if phase == Phase.VOTING:
        targets = tuple(s for s in targets if not (
            state.public.players[s].revealed_role == RoleName.IDIOT
            and state.board.idiot.exile_after_reveal == "immune"
        ))
        return (LegalAction("vote", targets, True),)
    if phase == Phase.BADGE_TRANSFER:
        return (LegalAction("badge_transfer", state.public.alive, True),)
    if phase == Phase.DEATH_SKILL:
        return (LegalAction("hunter_shot", targets, True),)
    return ()


def validate_action(state: GameState, seat: int, action: Action) -> None:
    options = legal_actions(state, seat)
    option = next((option for option in options if option.action == action.action), None)
    if option is None:
        raise IllegalAction(f"Seat {seat} cannot use {action.action} in {state.public.phase}")
    if isinstance(action, WitchAction):
        if action.save_target is not None and action.save_target not in option.save_targets:
            raise IllegalAction("Antidote is unavailable or this target cannot be saved")
        if action.poison_target is not None and action.poison_target not in option.targets:
            raise IllegalAction("Poison is unavailable or this target cannot be poisoned")
        if action.save_target is not None and action.poison_target is not None and not state.board.witch.allow_both_potions:
            raise IllegalAction("This board permits only one potion per night")
        return
    if isinstance(action, SpeechOrderAction):
        if action.start not in option.targets:
            raise IllegalAction("Speech order must start with another living player")
        return
    if hasattr(action, "target"):
        if action.target is None and option.allow_pass:
            return
        if action.target not in option.targets:
            raise IllegalAction(f"Target {action.target} is illegal for {action.action}")
