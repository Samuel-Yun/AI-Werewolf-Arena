import pytest

from werewolf.config import BoardConfig, SheriffRules
from werewolf.agents.context import build_context_for_player
from werewolf.game.engine import GameEngine
from werewolf.game.errors import IllegalAction
from werewolf.game.phases import Phase
from werewolf.roles import RoleName as R
from werewolf.storage.replay import replay_events


def game():
    board = BoardConfig(name="sheriff", players=5,
                        roles={R.WEREWOLF: 1, R.SEER: 1, R.VILLAGER: 3},
                        sheriff=SheriffRules(enabled=True))
    return GameEngine(board, 1, role_assignments={
        1: R.WEREWOLF, 2: R.SEER, 3: R.VILLAGER, 4: R.VILLAGER, 5: R.VILLAGER})


def reach(game, phase):
    for _ in range(30):
        if game.state.public.phase == phase:
            return
        assert game.next_actor() is None, game.state.public.phase
        game.advance()
    raise AssertionError(f"Did not reach {phase}")


def first_dawn(game):
    reach(game, Phase.WOLF)
    game.submit(1, {"action": "wolf_kill", "target": 5})
    reach(game, Phase.SEER)
    game.submit(2, {"action": "seer_check", "target": 1})
    reach(game, Phase.SHERIFF_SIGNUP)


def speak_all(game):
    while game.next_actor() is not None:
        seat = game.next_actor()
        game.submit(seat, {"action": "speech", "text": f"{seat}号给出自己的判断。"})


def test_signup_pk_speech_order_and_weighted_exile():
    g = game()
    first_dawn(g)
    for seat in (1, 2, 3, 4):
        g.submit(seat, {"action": "sheriff_signup", "run": seat in (1, 2)})
    reach(g, Phase.SHERIFF_SPEECH)
    speak_all(g)
    reach(g, Phase.SHERIFF_WITHDRAW)
    for seat in (1, 2):
        g.submit(seat, {"action": "sheriff_withdraw", "withdraw": False})
    reach(g, Phase.SHERIFF_VOTE)
    with pytest.raises(IllegalAction):
        g.submit(1, {"action": "sheriff_vote", "target": 1})
    g.submit(3, {"action": "sheriff_vote", "target": 1})
    before_reveal = build_context_for_player(g.state, g.events, 4)
    assert before_reveal.public.sheriff_ballots == ()
    assert all(e.event_type != "SheriffBallot" for e in before_reveal.events)
    g.submit(4, {"action": "sheriff_vote", "target": 2})
    reach(g, Phase.SHERIFF_PK_SPEECH)
    speak_all(g)
    reach(g, Phase.SHERIFF_PK_VOTE)
    g.submit(3, {"action": "sheriff_vote", "target": 2})
    g.submit(4, {"action": "sheriff_vote", "target": 2})
    reach(g, Phase.SPEECH_ORDER)
    assert g.state.public.sheriff == 2
    g.submit(2, {"action": "speech_order", "start": 3, "direction": "clockwise"})
    reach(g, Phase.DISCUSSION)
    assert g.state.public.speech_order == (3, 4, 1, 2)
    with pytest.raises(IllegalAction):
        g.submit(1, {"action": "speech", "text": "越位发言"})
    speak_all(g)
    reach(g, Phase.VOTING)
    g.submit(1, {"action": "vote", "target": 2})
    before_reveal = build_context_for_player(g.state, g.events, 2)
    assert before_reveal.public.votes == ()
    assert all(e.event_type != "VoteSubmitted" for e in before_reveal.events)
    for seat, target in ((2, 1), (3, 1), (4, 2)):
        g.submit(seat, {"action": "vote", "target": target})
    reach(g, Phase.EXILE_RESOLUTION)
    g.advance()
    tally = next(e.payload for e in g.events if e.event_type == "ExileTally")
    assert tally["weights"][2] == 3 and tally["totals"] == {1: 5, 2: 4}
    assert not g.state.public.players[1].alive
    reach(g, Phase.DAY_WIN_CHECK)
    g.advance()
    assert g.state.public.winner == "good"
    assert replay_events(g.events) == g.state


@pytest.mark.parametrize("recipient", [3, None])
def test_badge_transfer_or_destruction(recipient):
    g = game()
    first_dawn(g)
    for seat in (1, 2, 3, 4):
        g.submit(seat, {"action": "sheriff_signup", "run": seat == 2})
    reach(g, Phase.SPEECH_ORDER)
    g.submit(2, {"action": "speech_order", "start": 3, "direction": "clockwise"})
    reach(g, Phase.DISCUSSION)
    speak_all(g)
    reach(g, Phase.VOTING)
    for seat in (1, 2, 3, 4):
        g.submit(seat, {"action": "vote", "target": None})
    reach(g, Phase.EXILE_RESOLUTION)
    g.advance()
    reach(g, Phase.NIGHT_START)
    reach(g, Phase.WOLF)
    g.submit(1, {"action": "wolf_kill", "target": 2})
    reach(g, Phase.SEER)
    g.submit(2, {"action": "seer_check", "target": 1})
    reach(g, Phase.BADGE_TRANSFER)
    assert g.next_actor() == 2
    with pytest.raises(IllegalAction):
        g.submit(2, {"action": "badge_transfer", "target": 5})
    g.submit(2, {"action": "badge_transfer", "target": recipient})
    g.advance()
    assert g.state.public.sheriff == recipient
    assert replay_events(g.events, require_complete=False) == g.state


@pytest.mark.parametrize("case", ["none", "all_withdraw", "abstain", "pk_tie"])
def test_no_sheriff_when_election_cannot_resolve(case):
    g = game()
    first_dawn(g)
    for seat in (1, 2, 3, 4):
        g.submit(seat, {"action": "sheriff_signup", "run": case != "none" and seat in (1, 2)})
    if case == "none":
        reach(g, Phase.DISCUSSION)
    else:
        reach(g, Phase.SHERIFF_SPEECH)
        speak_all(g)
        reach(g, Phase.SHERIFF_WITHDRAW)
        for seat in (1, 2):
            g.submit(seat, {"action": "sheriff_withdraw", "withdraw": case == "all_withdraw"})
        if case == "all_withdraw":
            reach(g, Phase.DISCUSSION)
        else:
            reach(g, Phase.SHERIFF_VOTE)
            if case == "abstain":
                for seat in (3, 4):
                    g.submit(seat, {"action": "sheriff_vote", "target": None})
                reach(g, Phase.DISCUSSION)
            else:
                g.submit(3, {"action": "sheriff_vote", "target": 1})
                g.submit(4, {"action": "sheriff_vote", "target": 2})
                reach(g, Phase.SHERIFF_PK_SPEECH)
                speak_all(g)
                reach(g, Phase.SHERIFF_PK_VOTE)
                g.submit(3, {"action": "sheriff_vote", "target": 1})
                g.submit(4, {"action": "sheriff_vote", "target": 2})
                reach(g, Phase.DISCUSSION)
    assert g.state.public.sheriff is None
    assert g.state.public.speech_order == ()
    assert replay_events(g.events, require_complete=False) == g.state


def test_counterclockwise_order_keeps_sheriff_last():
    g = game()
    first_dawn(g)
    for seat in (1, 2, 3, 4):
        g.submit(seat, {"action": "sheriff_signup", "run": seat == 2})
    reach(g, Phase.SPEECH_ORDER)
    g.submit(2, {"action": "speech_order", "start": 4, "direction": "counterclockwise"})
    reach(g, Phase.DISCUSSION)
    assert g.state.public.speech_order == (4, 3, 1, 2)
