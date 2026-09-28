import argparse
import json
import secrets
import sys
from pathlib import Path

from werewolf.config import default_players, load_board, load_players
from werewolf.game.engine import GameEngine
from werewolf.game.events import EventType, Visibility
from werewolf.agents.memory import SimpleMemoryStore
from werewolf.providers.environment import load_environment
from werewolf.providers.factory import create_agents
from werewolf.runner import AutoRunner
from werewolf.simulation import simulate
from werewolf.storage.game_store import GameStore, transcript, write_json
from werewolf.storage.replay import replay_directory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="werewolf", description="AI Werewolf Arena")
    commands = cli.add_subparsers(dest="command", required=True)
    for name in ("play", "simulate"):
        command = commands.add_parser(name)
        command.add_argument("--seed", type=int, default=None)
        command.add_argument("--board", type=Path, default=PROJECT_ROOT / "configs/boards/phase1.yaml")
        command.add_argument("--players", type=Path)
        command.add_argument("--data-dir", type=Path, default=Path("data/games"))
    play = commands.choices["play"]
    providers = play.add_mutually_exclusive_group()
    providers.add_argument("--mock", action="store_true", help="Force every seat to use MockProvider")
    providers.add_argument("--provider", choices=["mock", "deepseek"], help="Override provider for all seats")
    play.add_argument("--model", help="Model override for DeepSeek seats; default deepseek-flash")
    play.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    play.add_argument("--thinking", choices=["enabled", "disabled"], default="disabled")
    play.add_argument("--api-timeout", type=float, default=45)
    play.add_argument("--max-api-requests", type=int, default=240)
    play.add_argument("--test-run", action="store_true", help="Mark the run as a test and exclude it from long-term memory/history")
    play.add_argument("--progress", action="store_true", help="Print public events and API request counts during play")
    play.add_argument("--mode", choices=["auto", "director"], default="auto")
    play.add_argument("--quiet", action="store_true")
    simulation = commands.choices["simulate"]
    simulation.add_argument("--games", type=int, default=1000)
    simulation.add_argument("--report", type=Path, default=Path("data/simulations/latest.json"))
    replay = commands.add_parser("replay")
    replay.add_argument("game_id", help="Game ID or path to its directory")
    replay.add_argument("--data-dir", type=Path, default=Path("data/games"))
    return cli


def progress_callback(client):
    cursor = 0
    requests = 0
    def report(engine):
        nonlocal cursor, requests
        events = engine.events
        for event in events[cursor:]:
            if event.visibility != Visibility.PUBLIC:
                continue
            if event.event_type == EventType.NIGHT_STARTED:
                print(f"\nNight {event.day + 1}", flush=True)
        text = transcript(events[cursor:], engine.state).strip()
        if text:
            print(text, flush=True)
        cursor = len(events)
        if client is not None and client.usage.requests != requests:
            requests = client.usage.requests
            print(f"[API] requests={requests}, successful={client.usage.successful_requests}, failed={client.usage.failed_requests}", flush=True)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.command == "replay":
            path = Path(args.game_id)
            if not path.is_dir():
                path = args.data_dir / args.game_id
            state = replay_directory(path)
            print(f"Replay verified: seed={state.seed}, winner={state.public.winner}, days={state.public.day}")
            return 0
        board = load_board(args.board)
        player_path = args.players
        if player_path is None and board.players == 12:
            player_path = PROJECT_ROOT / "configs/players.yaml"
        players = load_players(player_path, board.players) if player_path else default_players(board.players)
        seed = args.seed if args.seed is not None else secrets.randbits(32)
        if args.command == "simulate":
            if any(p.provider != "mock" for p in players):
                raise ValueError("Simulation is offline and requires MockProvider players")
            stats = simulate(board, players, games=args.games, seed=seed, failure_root=args.data_dir)
            report = {"seed": seed, "board": str(args.board.resolve()), **stats.to_dict()}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.report, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if stats.success else 1
        override = "mock" if args.mock else args.provider
        if override:
            override_model = (args.model or "deepseek-flash") if override == "deepseek" else "mock"
            players = tuple(p.model_copy(update={"provider": override,
                           "model": override_model}) for p in players)
        elif args.model:
            players = tuple(p.model_copy(update={"model": args.model}) if p.provider == "deepseek" else p for p in players)
        load_environment(args.env_file)
        agents, client, catalog = create_agents(board, players, seed, timeout=args.api_timeout,
                                                max_requests=args.max_api_requests, thinking=args.thinking)
        engine = GameEngine(board, seed, players)
        def run_info():
            return {"test_run": args.test_run, "memory_policy": "disabled", "exclude_from_history": args.test_run,
                    "thinking": args.thinking, "model_catalog": catalog,
                    "api_usage": client.report() if client is not None else None,
                    "fallback_actions": sum(e.event_type == EventType.FALLBACK_USED for e in engine.events)}
        options = {"agents": agents, "memory": SimpleMemoryStore(),
                   "on_step": progress_callback(client) if args.progress else None}
        try:
            if args.mode == "director":
                from werewolf.director.cli import DirectorRunner
                DirectorRunner(engine, **options).run()
            else:
                AutoRunner(engine, **options).run()
        except Exception as exc:
            diagnostic = {
                "seed": seed, "error": type(exc).__name__, "reason": str(exc),
                "phase": engine.state.public.phase, "day": engine.state.public.day,
                "event_count": engine.state.event_count,
            }
            path = GameStore(args.data_dir).save(engine, diagnostic=diagnostic, run_info=run_info())
            print(f"FAILED GAME seed={seed}; diagnostic={path / 'diagnostic.json'}", file=sys.stderr)
            return 1
        path = GameStore(args.data_dir).save(engine, run_info=run_info())
        if not args.quiet and not args.progress:
            print(transcript(engine.events, engine.state))
        print(f"Completed: seed={seed}, winner={engine.state.public.winner}, days={engine.state.public.day}")
        print(f"Game log: {path}")
        if client is not None:
            print("API usage: " + json.dumps(client.report(), ensure_ascii=False))
            print(f"Fallback actions: {run_info()['fallback_actions']}")
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
