from werewolf.game.state import GameState
from werewolf.roles import ROLES, RoleName, Team


def alignment_for_model(state: GameState, model: int) -> Team:
    rule = state.board.hybrid.alignment
    if rule == "follow_model":
        return ROLES[state.secret.roles[model]].team
    return Team(rule)


def effective_team(state: GameState, seat: int) -> Team:
    if state.secret.roles[seat] == RoleName.HYBRID:
        return state.secret.hybrid_teams.get(seat, Team.GOOD)
    return ROLES[state.secret.roles[seat]].team


def counts_for_win(state: GameState, seat: int) -> bool:
    return state.secret.roles[seat] != RoleName.HYBRID or state.board.hybrid.counts_for_win
