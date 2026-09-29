from werewolf.game.state import GameState
from werewolf.roles import ROLES, Team
from werewolf.roles import RoleName
from werewolf.roles.base import SlaughterSide, slaughter_side
from werewolf.roles.alignment import counts_for_win, effective_team


def check_winner(state: GameState) -> Team | None:
    if state.board.wolf_win == "slaughter":
        alive_sides = {slaughter_side(state.secret.roles[s]) for s in state.public.alive}
        good_won = SlaughterSide.WOLF not in alive_sides
        wolf_won = SlaughterSide.GOD not in alive_sides or SlaughterSide.CIVILIAN not in alive_sides
        if good_won and wolf_won:
            return state.board.simultaneous_elimination
        if good_won:
            return Team.GOOD
        if wolf_won:
            return Team.WOLF
        return None
    counted = [s for s in state.public.alive if counts_for_win(state, s)]
    wolves = sum(effective_team(state, s) == Team.WOLF for s in counted)
    good = len(counted) - wolves
    if wolves == 0 and good == 0:
        return state.board.simultaneous_elimination
    if wolves == 0:
        return Team.GOOD
    if good == 0 or (state.board.wolf_win == "parity" and wolves >= good):
        return Team.WOLF
    return None


def winning_players(state: GameState, winner: Team) -> list[int]:
    winners = []
    for seat, role in sorted(state.secret.roles.items()):
        if role != RoleName.HYBRID:
            won = effective_team(state, seat) == winner
        else:
            match state.board.hybrid.victory:
                case "aligned_team":
                    won = effective_team(state, seat) == winner
                case "model_team":
                    model = state.secret.hybrid_models[seat]
                    won = ROLES[state.secret.roles[model]].team == winner
                case "survive":
                    won = state.public.players[seat].alive
        if won:
            winners.append(seat)
    return winners
