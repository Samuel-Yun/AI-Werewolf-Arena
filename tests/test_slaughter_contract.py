import pytest

from werewolf.agents.context import build_context_for_player
from werewolf.config import load_board
from werewolf.game.engine import GameEngine
from werewolf.game.phases import Phase
from werewolf.game.win_conditions import check_winner, winning_players
from werewolf.roles import RoleName as R, Team


ROLES = {1: R.WEREWOLF, 2: R.VILLAGER, 3: R.WEREWOLF, 4: R.IDIOT,
         5: R.SEER, 6: R.WEREWOLF, 7: R.WITCH, 8: R.WEREWOLF,
         9: R.VILLAGER, 10: R.HYBRID, 11: R.VILLAGER, 12: R.HUNTER}


def full_game():
    board = load_board(__import__("pathlib").Path("configs/boards/seer_witch_hunter_idiot_hybrid.yaml"))
    return GameEngine(board, 123, role_assignments=ROLES)


def choose_model(game, target):
    game.advance()
    game.advance()
    assert game.state.public.phase == Phase.HYBRID_CHOOSE
    game.submit(10, {"action": "hybrid_choose", "target": target})


@pytest.mark.parametrize("model", [1, 2])
@pytest.mark.parametrize("alive,expected", [
    ({1, 3, 6, 8, 4, 5, 7, 12, 10}, None),  # Three ordinary civilians die; hybrid remains.
    ({1, 2, 4}, None),                      # Hybrid dies; an ordinary civilian remains.
    ({1, 4, 5, 7, 12}, Team.WOLF),          # All four civilian slots die.
    ({1, 2, 10}, Team.WOLF),                # All four gods die.
    ({1, 2, 4}, None),                      # Revealed idiot remains alive and is still a god.
    ({1, 3, 6, 8, 2, 4}, None),            # Numerical wolf advantage does not win.
    ({2, 4, 10}, Team.GOOD),                # All actual wolves die.
])
def test_slaughter_uses_fixed_role_side_not_hybrid_alignment(model, alive, expected):
    game = full_game()
    choose_model(game, model)
    state = game.state
    for seat, player in state.public.players.items():
        player.alive = seat in alive
    if 4 in alive:
        state.public.players[4].revealed_role = R.IDIOT
        state.public.players[4].can_vote = False
    assert check_winner(state) == expected


@pytest.mark.parametrize("model,team", [(1, Team.WOLF), (2, Team.GOOD)])
def test_hybrid_hidden_victory_and_no_wolf_rights(model, team):
    game = full_game()
    choose_model(game, model)
    game.advance()
    assert game.state.public.phase == Phase.WOLF_CHAT
    hybrid = build_context_for_player(game.state, game.events, 10)
    wolf = build_context_for_player(game.state, game.events, 1)
    assert game.state.secret.hybrid_teams[10] == team
    assert hybrid.own.hybrid_model == model
    assert hybrid.own.team is None and hybrid.own.wolf_teammates == ()
    assert hybrid.legal_actions == ()
    assert wolf.own.wolf_teammates == (1, 3, 6, 8)
    assert (10 in winning_players(game.state, team))
    assert (10 not in winning_players(game.state, Team.GOOD if team == Team.WOLF else Team.WOLF))
    game.submit(1, {"action": "wolf_chat", "target": 7, "text": "建议刀7号，明天解释票型。"})
    teammate = build_context_for_player(game.state, game.events, 3)
    hybrid = build_context_for_player(game.state, game.events, 10)
    villager = build_context_for_player(game.state, game.events, 2)
    assert any(e.event_type == "WolfChatMessage" for e in teammate.events)
    assert all(e.event_type != "WolfChatMessage" for e in hybrid.events + villager.events)
    assert "建议刀7号" not in str(hybrid.model_dump())


def test_wolf_chat_is_private_in_saved_public_record(tmp_path):
    from werewolf.runner import AutoRunner
    from werewolf.storage.game_store import GameStore
    from werewolf.storage.replay import replay_directory

    game = AutoRunner(full_game()).run()
    path = GameStore(tmp_path).save(game)
    private = [e for e in game.events if e.event_type == "WolfChatMessage"]
    assert private and all(e.visibility == "PRIVATE_WOLVES" for e in private)
    assert any(e.event_type == "WolfKillSelected" for e in game.events)
    public = (path / "public_transcript.txt").read_text()
    director = (path / "transcript.txt").read_text()
    assert "狼聊第" in director and "最终刀口=" in director
    assert "狼聊第" not in public and "最终刀口=" not in public
    assert "真实身份：" not in public
    assert replay_directory(path) == game.state


def test_lone_wolf_has_two_private_chat_turns_without_invented_teammates():
    from werewolf.config import BoardConfig, WolfChatRules
    board = BoardConfig(name="lone_wolf", players=3,
                        roles={R.WEREWOLF: 1, R.VILLAGER: 2},
                        wolf_chat=WolfChatRules(enabled=True, rounds=2))
    game = GameEngine(board, 7, role_assignments={1: R.WEREWOLF, 2: R.VILLAGER, 3: R.VILLAGER})
    game.advance()
    game.advance()
    assert game.state.public.phase == Phase.WOLF_CHAT
    assert build_context_for_player(game.state, game.events, 1).own.wolf_teammates == (1,)
    game.submit(1, {"action": "wolf_chat", "target": 2, "text": "我独自决定先考虑2号。"})
    game.advance()
    assert game.state.secret.wolf_chat_round == 2 and game.next_actor() == 1
    game.submit(1, {"action": "wolf_chat", "target": 3, "text": "第二轮改刀3号。"})
    game.advance()
    assert game.state.public.phase == Phase.WOLF
    chat = [e for e in game.events if e.event_type == "WolfChatMessage"]
    assert [e.payload["round"] for e in chat] == [1, 2]
    assert all(e.actor == 1 and e.visibility == "PRIVATE_WOLVES" for e in chat)
    assert all(e.event_type != "WolfChatMessage"
               for e in build_context_for_player(game.state, game.events, 2).events)
