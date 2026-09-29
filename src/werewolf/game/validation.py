from werewolf.game.errors import InvariantViolation
from werewolf.game.phases import Phase
from werewolf.game.state import GameState
from werewolf.roles import RoleName


def validate_game_state(state: GameState) -> None:
    """Check invariants after every event, including phase transitions."""
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise InvariantViolation(message)

    public, secret = state.public, state.secret
    seats = set(range(1, state.board.players + 1))
    require(isinstance(public.phase, Phase), "Unknown phase")
    require(0 <= public.day <= state.board.max_days, "Invalid day")
    if not public.players and state.event_count == 0:
        return
    require(set(public.players) == seats, "Seats must be unique and complete")
    require(set(secret.roles) == seats, "Every player needs exactly one role")
    for role, count in state.board.roles.items():
        require(sum(r == role for r in secret.roles.values()) == count, "Role distribution changed")
    alive = set(public.alive)
    require(not alive & public.dead, "Alive and dead overlap")
    require(alive | public.dead == seats, "Alive and dead must partition players")
    require(state.submitted <= seats, "Unknown submitted actor")
    for seat, player in public.players.items():
        require(player.seat == seat, "Seat key mismatch")
        require(player.alive or not player.can_vote, "Dead players cannot vote")
    for actor, target in public.votes.items():
        require(actor in seats and (target is None or target in seats), "Invalid vote seat")
        if public.phase == Phase.VOTING:
            require(actor in alive and public.players[actor].can_vote, "Ineligible voter")
            require(target is None or target in alive and target != actor, "Illegal active vote target")
    for actor, target in secret.pending_votes.items():
        require(public.phase == Phase.VOTING and actor in alive and public.players[actor].can_vote,
                "Ineligible pending voter")
        require(target is None or target in alive and target != actor, "Invalid pending vote target")
    for actor, target in secret.pending_sheriff_ballots.items():
        require(public.phase in {Phase.SHERIFF_VOTE, Phase.SHERIFF_PK_VOTE} and actor in alive,
                "Ineligible pending sheriff voter")
        eligible = (set(public.sheriff_pk_candidates) if public.phase == Phase.SHERIFF_PK_VOTE else
                    {s for s, run in public.sheriff_signup.items() if run and s not in public.sheriff_withdrawn})
        require(not public.sheriff_signup.get(actor, False), "Candidate cast sheriff ballot")
        require(target is None or target in alive and target in eligible, "Invalid pending sheriff target")
    if secret.night.wolf_target is not None:
        require(secret.night.wolf_target in seats, "Unknown wolf target")
        require(secret.roles[secret.night.wolf_target] != RoleName.WEREWOLF, "Wolf target is a teammate")
    for actor, target in secret.night.wolf_votes.items():
        require(actor in seats and target in seats, "Invalid wolf action seat")
        require(secret.roles[actor] == RoleName.WEREWOLF, "Non-wolf submitted wolf action")
        require(secret.roles[target] != RoleName.WEREWOLF, "Wolves cannot kill teammates")
        if public.phase in {Phase.WOLF, Phase.SEER, Phase.WITCH, Phase.NIGHT_RESOLUTION}:
            require(actor in alive and target in alive, "Dead player in pending wolf action")
    for actor, target in secret.night.seer_checks.items():
        require(actor in seats and target in seats and actor != target, "Invalid check")
        require(secret.roles[actor] == RoleName.SEER, "Non-seer submitted check")
        if public.phase in {Phase.SEER, Phase.WITCH, Phase.NIGHT_RESOLUTION}:
            require(actor in alive and target in alive, "Dead player in pending seer action")
    for actor, potions in secret.potions.items():
        require(secret.roles.get(actor) == RoleName.WITCH, "Potions belong to a non-witch")
        require(0 <= potions.antidote <= 1 and 0 <= potions.poison <= 1, "Invalid potion count")
    for actor, action in secret.night.witch_actions.items():
        require(secret.roles.get(actor) == RoleName.WITCH, "Non-witch submitted witch action")
        for target in action.values():
            require(target is None or target in seats, "Invalid potion target")
    queue = secret.death_skill_queue
    require(len(queue) == len(set(queue)), "Duplicate death skill")
    require(set(queue) <= public.dead, "Only dead players can have pending death skills")
    require(not set(queue) & secret.hunter_spent, "Hunter can shoot only once")
    for seat in (*queue, *secret.hunter_spent):
        require(secret.roles.get(seat) == RoleName.HUNTER, "Non-hunter has a death skill")
    if public.phase in {Phase.DEATH_SKILL, Phase.BADGE_TRANSFER}:
        require(secret.death_skill_resume in {Phase.NIGHT_WIN_CHECK, Phase.DAY_WIN_CHECK}, "Invalid skill continuation")
    if public.phase == Phase.BADGE_TRANSFER:
        require(secret.badge_transfer_pending is not None or bool(state.submitted),
                "Missing badge holder")
    if secret.badge_transfer_pending is not None:
        require(secret.badge_transfer_pending == public.sheriff and
                secret.badge_transfer_pending in public.dead, "Invalid pending badge transfer")
    if public.sheriff is not None:
        require(public.sheriff in seats, "Unknown sheriff")
    require(set(public.sheriff_signup) <= seats, "Unknown sheriff candidate")
    require(public.sheriff_withdrawn <= set(public.sheriff_signup), "Unknown withdrawal")
    require(set(public.sheriff_ballots) <= seats, "Unknown sheriff voter")
    require(set(public.sheriff_pk_candidates) <= seats, "Unknown PK candidate")
    require(set(public.speech_order) <= seats and len(public.speech_order) == len(set(public.speech_order)),
            "Invalid speech order")
    require(1 <= secret.wolf_chat_round <= state.board.wolf_chat.rounds, "Invalid wolf chat round")
    for seat, player in public.players.items():
        if player.revealed_role == RoleName.IDIOT:
            require(not player.can_vote, "Revealed idiot cannot vote")
        if player.revealed_role is not None:
            require(player.revealed_role == secret.roles[seat], "Public role reveal contradicts truth")
    hybrid_seats = {s for s, r in secret.roles.items() if r == RoleName.HYBRID}
    require(set(secret.hybrid_models) <= hybrid_seats, "Non-hybrid chose a model")
    require(set(secret.hybrid_models) == set(secret.hybrid_teams), "Hybrid alignment is missing")
    from werewolf.roles.alignment import alignment_for_model
    for seat, model in secret.hybrid_models.items():
        require(model in seats and model != seat, "Invalid hybrid model")
        require(secret.hybrid_teams[seat] == alignment_for_model(state, model), "Hybrid alignment contradicts config")
    if public.day > 0 and public.phase not in {Phase.NIGHT_START, Phase.HYBRID_CHOOSE}:
        require(set(secret.hybrid_models) == hybrid_seats, "First-night hybrid choice is missing")
    require(set(secret.winning_players) <= seats, "Unknown winning player")
    if public.winner is not None:
        from werewolf.game.win_conditions import check_winner
        require(public.winner == check_winner(state), "Declared winner contradicts canonical state")
    if public.phase == Phase.ENDED:
        require(public.winner is not None, "Ended games need a winner")
