import io
import json
from urllib.error import HTTPError, URLError

import pytest

from werewolf.agents.agent import Agent
from werewolf.agents.context import build_context_for_player
from werewolf.config import default_players
from werewolf.game.events import EventType
from werewolf.providers.environment import load_environment
from werewolf.providers.errors import FatalProviderError, ProviderError
from werewolf.providers.factory import create_agents
from werewolf.providers.openai_compatible import DeepSeekProvider, OpenAICompatibleClient
from werewolf.providers.prompts import build_messages
from werewolf.runner import AutoRunner
from werewolf.storage.game_store import GameStore
from werewolf.storage.replay import replay_directory

FAKE_KEY = "fake-test-key-never-used-on-network"


def response(content='{"action":"vote","target":7}', **extra):
    return {"model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}, **extra}


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(json.dumps(outcome).encode("utf-8"))


def client(transport, **kwargs):
    return OpenAICompatibleClient(api_key=FAKE_KEY, transport=transport, **kwargs)


def test_https_request_json_mode_timeout_and_usage():
    transport = FakeTransport([response()])
    api = client(transport, timeout=12)
    assert api.complete(model="deepseek-flash", messages=[{"role": "user", "content": "JSON"}],
                        thinking="disabled", max_tokens=256) == '{"action":"vote","target":7}'
    request, timeout = transport.calls[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert request.get_header("Authorization") == "Bearer " + FAKE_KEY
    body = json.loads(request.data)
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"} and timeout == 12
    assert api.report()["total_tokens"] == 110
    assert FAKE_KEY not in json.dumps(api.report())


@pytest.mark.parametrize("status", [401, 402, 403])
def test_fatal_http_errors_redact_credentials(status):
    error = HTTPError("https://api.deepseek.com/chat/completions", status, FAKE_KEY, {}, io.BytesIO(FAKE_KEY.encode()))
    api = client(FakeTransport([error]))
    with pytest.raises(FatalProviderError) as caught:
        api.complete(model="deepseek-flash", messages=[], thinking="disabled", max_tokens=100)
    assert FAKE_KEY not in str(caught.value)
    assert api.usage.failed_requests == 1


@pytest.mark.parametrize("outcome", [response(content=""), response(choices=[]),
                                      response(choices=[{"finish_reason": "length", "message": {"content": "{}"}}]),
                                      URLError("unavailable"), TimeoutError("timeout")])
def test_failures_are_bounded_and_reported(outcome):
    api = client(FakeTransport([outcome]))
    with pytest.raises(ProviderError):
        api.complete(model="deepseek-flash", messages=[], thinking="disabled", max_tokens=100)
    assert api.usage.requests == api.usage.failed_requests == 1


def test_consecutive_outage_stops_instead_of_mocking_entire_game():
    api = client(FakeTransport([TimeoutError()] * 3))
    for _ in range(2):
        with pytest.raises(ProviderError):
            api.complete(model="deepseek-flash", messages=[], thinking="disabled", max_tokens=100)
    with pytest.raises(FatalProviderError, match="consecutive"):
        api.complete(model="deepseek-flash", messages=[], thinking="disabled", max_tokens=100)


def test_request_budget_prevents_more_paid_requests():
    transport = FakeTransport([response()])
    api = client(transport, max_requests=1)
    api.complete(model="deepseek-flash", messages=[], thinking="disabled", max_tokens=100)
    with pytest.raises(FatalProviderError, match="MAX_API_REQUESTS"):
        api.complete(model="deepseek-flash", messages=[], thinking="disabled", max_tokens=100)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("url", ["http://api.deepseek.com", "https://user:password@api.deepseek.com", "https://api.deepseek.com?key=secret"])
def test_credentials_require_valid_https_destination(url):
    with pytest.raises(ValueError):
        client(FakeTransport([]), base_url=url)


def test_context_filter_survives_api_serialization(engine):
    from conftest import play_night
    play_night(engine)
    villager = build_context_for_player(engine.state, engine.events, 7)
    seer = build_context_for_player(engine.state, engine.events, 5)
    wolf = build_context_for_player(engine.state, engine.events, 1)
    def view(context):
        return json.loads(build_messages(context, engine.state.board)[1]["content"])["player_context"]
    assert not view(villager)["private_history"]
    assert not view(villager)["own"]["checks"]
    assert not view(villager)["own"]["wolf_teammates"]
    assert view(seer)["own"]["checks"][0]["target"] == 1
    assert not view(seer)["own"]["wolf_teammates"]
    assert view(wolf)["own"]["wolf_teammates"] == [1, 2, 3, 4]
    assert "secret" not in view(villager) and "roles" not in view(villager)
    assert view(villager)["public"]["dead_seats"] == [6]
    assert 6 not in view(villager)["public"]["alive_seats"]


def test_request_schema_explicitly_constrains_living_legal_targets(engine):
    from conftest import begin_night
    begin_night(engine)
    context = build_context_for_player(engine.state, engine.events, 1)
    view = json.loads(build_messages(context, engine.state.board)[1]["content"])["player_context"]
    schema = view["action_schemas"][0]
    assert "action" in schema["required"]
    assert schema["properties"]["target"]["enum"] == list(context.legal_actions[0].targets)
    assert not set(schema["properties"]["target"]["enum"]) & {1, 2, 3, 4}


def test_shared_client_does_not_share_messages(engine):
    transport = FakeTransport([response(), response()])
    provider = DeepSeekProvider(client(transport), engine.state.board)
    provider.generate(build_context_for_player(engine.state, engine.events, 1))
    provider.generate(build_context_for_player(engine.state, engine.events, 7))
    bodies = [json.loads(call[0].data) for call in transport.calls]
    assert len(bodies[0]["messages"]) == len(bodies[1]["messages"]) == 2
    second = json.loads(bodies[1]["messages"][1]["content"])["player_context"]
    assert second["profile"]["seat"] == 7 and not second["own"]["wolf_teammates"]
    assert FAKE_KEY not in json.dumps(bodies)


def test_all_real_seats_share_credentials_but_have_separate_providers(board, monkeypatch):
    transport = FakeTransport([{"data": [{"id": "deepseek-flash", "name": "DeepSeek-V4.1-Flash"}]}])
    api = client(transport)
    monkeypatch.setattr(OpenAICompatibleClient, "from_environment", lambda **kwargs: api)
    players = tuple(p.model_copy(update={"provider": "deepseek", "model": "deepseek-flash"}) for p in default_players(12))
    agents, shared, catalog = create_agents(board, players, 123)
    assert shared is api and len(transport.calls) == 1
    assert all(a.provider.client is api for a in agents.values())
    assert len({id(a.provider) for a in agents.values()}) == 12
    assert catalog[0]["name"] == "DeepSeek-V4.1-Flash"


def test_mixed_one_real_and_eleven_mocks(board, monkeypatch):
    from werewolf.providers.mock import MockProvider
    api = client(FakeTransport([{"data": [{"id": "deepseek-flash"}]}]))
    monkeypatch.setattr(OpenAICompatibleClient, "from_environment", lambda **kwargs: api)
    players = list(default_players(12))
    players[0] = players[0].model_copy(update={"provider": "deepseek", "model": "deepseek-flash"})
    agents, _, _ = create_agents(board, tuple(players), 123)
    assert isinstance(agents[1].provider, DeepSeekProvider)
    assert all(isinstance(agents[s].provider, MockProvider) for s in range(2, 13))


def test_unavailable_requested_model_does_not_switch_models(board, monkeypatch):
    api = client(FakeTransport([{"data": [{"id": "other-model"}]}]))
    monkeypatch.setattr(OpenAICompatibleClient, "from_environment", lambda **kwargs: api)
    players = tuple(p.model_copy(update={"provider": "deepseek", "model": "deepseek-flash"}) for p in default_players(12))
    with pytest.raises(ValueError, match="unavailable"):
        create_agents(board, players, 123)


def test_fatal_provider_error_is_not_retried_or_hidden(engine):
    class Denied:
        def generate(self, *args, **kwargs):
            raise FatalProviderError("API HTTP 401")
    runner = AutoRunner(engine, {seat: Agent(Denied()) for seat in range(1, 13)})
    with pytest.raises(FatalProviderError):
        runner.run()
    assert not any(e.event_type == EventType.FALLBACK_USED for e in engine.events)


def test_environment_file_does_not_execute_or_override(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('DEEPSEEK_API_KEY="local-test"\nEXPRESSION=$(whoami)\n', encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "existing-test")
    monkeypatch.delenv("EXPRESSION", raising=False)
    load_environment(path)
    import os
    assert os.environ["DEEPSEEK_API_KEY"] == "existing-test"
    assert os.environ["EXPRESSION"] == "$(whoami)"
    monkeypatch.delenv("EXPRESSION")


def test_test_run_is_flagged_and_still_replays(engine, tmp_path):
    AutoRunner(engine).run()
    info = {"test_run": True, "memory_policy": "disabled", "exclude_from_history": True}
    path = GameStore(tmp_path).save(engine, run_info=info)
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run"] == info
    assert replay_directory(path) == engine.state


def test_cli_test_run_overrides_all_seats_without_memory_writes(tmp_path, monkeypatch):
    import werewolf.cli as cli
    captured = []
    def factory(board, players, seed, **kwargs):
        from werewolf.agents.agent import MockAgent
        captured.extend(players)
        return {p.seat: MockAgent(seed, p.seat) for p in players}, None, []
    monkeypatch.setattr(cli, "create_agents", factory)
    status = cli.main(["play", "--provider", "deepseek", "--model", "deepseek-flash", "--test-run",
                       "--seed", "123", "--quiet", "--env-file", str(tmp_path / "missing.env"),
                       "--data-dir", str(tmp_path / "games")])
    assert status == 0
    assert len(captured) == 12 and all(p.provider == "deepseek" and p.model == "deepseek-flash" for p in captured)
    directory = next((tmp_path / "games").iterdir())
    info = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))["run"]
    assert info["test_run"] and info["exclude_from_history"] and info["memory_policy"] == "disabled"
    assert not (tmp_path / "players").exists()
