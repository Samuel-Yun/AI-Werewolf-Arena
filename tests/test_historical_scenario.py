from pathlib import Path

import pytest

from werewolf.agents.context import build_context_for_player
from werewolf.config import SheriffRules, WolfChatRules, load_board
from werewolf.game.engine import GameEngine
from werewolf.game.errors import ReplayError
from werewolf.game.phases import Phase
from werewolf.roles import RoleName as R
from werewolf.storage.game_store import GameStore
from werewolf.storage.replay import replay_events, replay_directory


ROLES = {1: R.WEREWOLF, 2: R.VILLAGER, 3: R.WEREWOLF, 4: R.IDIOT,
         5: R.SEER, 6: R.WEREWOLF, 7: R.WITCH, 8: R.WEREWOLF,
         9: R.VILLAGER, 10: R.HYBRID, 11: R.VILLAGER, 12: R.HUNTER}


def reach(game, phase):
    for _ in range(20):
        if game.state.public.phase == phase:
            return
        assert game.next_actor() is None, (game.state.public.phase, game.next_actor())
        game.advance()
    raise AssertionError(f"Did not reach {phase}")


def night(game, *, target, check=None, save=None, shot=None):
    reach(game, Phase.WOLF)
    for seat in (1, 3, 6, 8):
        if game.state.public.players[seat].alive:
            game.submit(seat, {"action": "wolf_kill", "target": target})
    reach(game, Phase.SEER)
    if game.state.public.players[5].alive:
        game.submit(5, {"action": "seer_check", "target": check})
    reach(game, Phase.WITCH)
    if game.state.public.players[7].alive:
        game.submit(7, {"action": "witch", "save_target": save})
    if shot is not None:
        reach(game, Phase.DEATH_SKILL)
        game.submit(12, {"action": "hunter_shot", "target": shot})
    reach(game, Phase.NIGHT_WIN_CHECK)
    game.advance()
    assert game.state.public.phase == Phase.DISCUSSION


def day(game, exile, self_vote):
    while game.next_actor() is not None:
        seat = game.next_actor()
        game.submit(seat, {"action": "speech", "text": f"{seat}号独立判断。"})
    reach(game, Phase.VOTING)
    for seat in game.state.public.alive:
        if game.state.public.players[seat].can_vote:
            game.submit(seat, {"action": "vote", "target": self_vote if seat == exile else exile})
    reach(game, Phase.EXILE_RESOLUTION)
    game.advance()
    reach(game, Phase.DAY_WIN_CHECK)
    game.advance()


def test_historical_key_events_replayed_under_slaughter_rules(tmp_path):
    board = load_board(Path("configs/boards/seer_witch_hunter_idiot_hybrid.yaml")).model_copy(
        update={"sheriff": SheriffRules(enabled=False), "wolf_chat": WolfChatRules(enabled=False)})
    game = GameEngine(board, 123, role_assignments=ROLES)
    reach(game, Phase.HYBRID_CHOOSE)
    game.submit(10, {"action": "hybrid_choose", "target": 1})
    night(game, target=12, check=4, save=12)
    assert game.state.secret.night_deaths == []
    assert all(e.phase == Phase.WITCH for e in game.events if e.event_type == "WitchWindowOpened")
    day(game, 7, 1)
    assert not game.state.public.players[7].alive
    night(game, target=5, check=1)
    assert game.state.secret.check_history[5][-1]["result"] == "wolf"
    assert not game.state.public.players[5].alive
    day(game, 8, 9)
    night(game, target=12, shot=6)
    assert not game.state.public.players[12].alive
    assert not game.state.public.players[6].alive
    day(game, 3, 9)
    night(game, target=9)
    day(game, 4, 2)
    assert game.state.public.players[4].alive
    assert not game.state.public.players[4].can_vote
    night(game, target=10)
    assert not game.state.public.players[10].alive
    while game.next_actor() is not None:
        seat = game.next_actor()
        game.submit(seat, {"action": "speech", "text": f"{seat}号发言。"})
    reach(game, Phase.VOTING)
    assert not build_context_for_player(game.state, game.events, 4).legal_actions
    for seat, target in ((1, 2), (2, 1), (11, 1)):
        game.submit(seat, {"action": "vote", "target": target})
    reach(game, Phase.EXILE_RESOLUTION)
    game.advance()
    reach(game, Phase.DAY_WIN_CHECK)
    game.advance()
    assert game.state.public.winner == "good"
    assert set(game.state.public.dead) >= {1, 3, 5, 6, 7, 8, 9, 10, 12}
    assert 10 not in game.state.secret.winning_players
    assert replay_events(game.events) == game.state
    path = GameStore(tmp_path).save(game)
    assert replay_directory(path) == game.state
    director = (path / "transcript.txt").read_text()
    public = (path / "public_transcript.txt").read_text()
    assert "真实身份：" in director and "隐藏归属=wolf" in director
    assert "预言家5查验1" in director and "查验结果 5验1=wolf" in director
    assert "女巫7对12使用解药" in director and "猎人12开枪射6号" in director
    assert "白痴4翻牌免死" in director and "Winner: good" in director
    assert "真实身份：" not in public and "隐藏归属" not in public
    assert "狼聊" not in public and "查验结果" not in public
    important = [e.event_id for e in game.events if e.event_type in
                 {"HybridModelChosen", "WitchUsedAntidote", "SeerChecked", "HunterShot", "IdiotRevealed", "GameEnded"}]
    locations = [director.index(f"#{number} [") for number in important]
    assert locations == sorted(locations)
    (path / "public_transcript.txt").write_text(public + "tampered", encoding="utf-8")
    with pytest.raises(ReplayError, match="Public transcript"):
        replay_directory(path)


def test_old_game_observation_has_no_future_day_two_vote():
    path = Path("data/games/3aedbcc190e046ed865877305764a0e1/events.jsonl")
    if not path.exists():
        return
    from werewolf.game.events import Event
    events = tuple(Event.model_validate_json(line) for line in path.read_text().splitlines())
    speech = next(i for i, e in enumerate(events) if e.day == 2 and e.event_type == "PlayerSpoke" and e.actor == 1)
    current = replay_events(events[:speech], require_complete=False)
    view = build_context_for_player(current, events[:speech], 1)
    assert {5, 7} <= set(p.seat for p in view.public.players if not p.alive)
    assert (1, 7) in view.public.previous_day_votes
    assert view.public.votes == ()
    assert all(not (e.day == 2 and e.event_type == "VoteSubmitted") for e in view.events)
    future = next(e for e in events[speech:] if e.day == 2 and e.event_type == "VoteSubmitted" and e.actor == 8)
    assert future.event_id > events[speech].event_id
