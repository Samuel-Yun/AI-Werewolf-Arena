import json
import os
from dataclasses import asdict, dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from werewolf.agents.context import AgentContext
from werewolf.config import BoardConfig
from werewolf.providers.errors import FatalProviderError, ProviderError
from werewolf.providers.prompts import build_messages


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class APIUsage:
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0


class OpenAICompatibleClient:
    """Stateless HTTPS transport. Shared credentials never share conversation history."""

    def __init__(self, *, api_key: str, base_url: str = "https://api.deepseek.com",
                 timeout: float = 45, max_requests: int = 240,
                 transport: Callable | None = None):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API base URL must be an HTTPS origin/path without credentials or query")
        if not api_key.strip():
            raise ValueError("API key is missing")
        if timeout <= 0 or max_requests < 1:
            raise ValueError("Timeout and request budget must be positive")
        self._api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_requests = max_requests
        self.usage = APIUsage()
        self.models_used: dict[str, int] = {}
        self._consecutive_failures = 0
        self._transport = transport or build_opener(NoRedirects()).open

    @classmethod
    def from_environment(cls, *, timeout: float = 45, max_requests: int = 240):
        return cls(api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                   base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                   timeout=timeout, max_requests=max_requests)

    def _request(self, path: str, body: dict | None = None) -> dict:
        request = Request(self.base_url + path,
                          data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None,
                          headers={"Authorization": "Bearer " + self._api_key,
                                   "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self._transport(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ProviderError("API response exceeds size limit")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ProviderError("API response must be a JSON object")
                return result
        except HTTPError as exc:
            # Do not record remote bodies, authorization headers, or secret-bearing requests.
            status = exc.code
            if status in {401, 403, 402}:
                raise FatalProviderError(f"API HTTP {status}: authentication, access, or balance failure") from None
            raise ProviderError(f"API HTTP {status}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"API connection failed ({type(exc).__name__})") from None
        except (ValueError, UnicodeError):
            raise ProviderError("API returned invalid JSON") from None

    def list_models(self) -> list[dict]:
        data = self._request("/models").get("data")
        if not isinstance(data, list) or any(not isinstance(m, dict) for m in data):
            raise ProviderError("Malformed model list")
        return data

    def complete(self, *, model: str, messages: list[dict[str, str]],
                 thinking: str, max_tokens: int) -> str:
        if self.usage.requests >= self.max_requests:
            raise FatalProviderError("MAX_API_REQUESTS exceeded")
        self.usage.requests += 1
        body = {"model": model, "messages": messages, "response_format": {"type": "json_object"},
                "thinking": {"type": thinking}, "max_tokens": max_tokens, "stream": False}
        if thinking == "enabled":
            body["reasoning_effort"] = "low"
        try:
            result = self._request("/chat/completions", body)
            usage = result.get("usage", {})
            if not isinstance(usage, dict):
                usage = {}
            for name in ("prompt_tokens", "completion_tokens", "total_tokens",
                         "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                value = usage.get(name, 0)
                if isinstance(value, int) and value >= 0:
                    setattr(self.usage, name, getattr(self.usage, name) + value)
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ProviderError("API response was truncated or interrupted")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ProviderError("API returned empty content")
        except (KeyError, IndexError, TypeError):
            self.usage.failed_requests += 1
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                raise FatalProviderError("API unavailable after three consecutive failures") from None
            raise ProviderError("Malformed chat completion") from None
        except ProviderError:
            self.usage.failed_requests += 1
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                raise FatalProviderError("API unavailable after three consecutive failures") from None
            raise
        self.usage.successful_requests += 1
        self._consecutive_failures = 0
        resolved_model = result.get("model", model)
        if not isinstance(resolved_model, str):
            resolved_model = model
        self.models_used[resolved_model] = self.models_used.get(resolved_model, 0) + 1
        return content

    def report(self) -> dict:
        return {**asdict(self.usage), "models_used": dict(self.models_used)}


class DeepSeekProvider:
    def __init__(self, client: OpenAICompatibleClient, board: BoardConfig, *, model: str = "deepseek-flash",
                 thinking: str = "disabled"):
        if thinking not in {"enabled", "disabled"}:
            raise ValueError("Invalid thinking mode")
        self.client = client
        self.board = board.model_copy(deep=True)
        self.model = model
        self.thinking = thinking

    def generate(self, context: AgentContext, *, feedback: str | None = None,
                 nudge: str | None = None) -> object:
        speech = any(a.action == "speech" for a in context.legal_actions)
        return self.client.complete(
            model=self.model, messages=build_messages(context, self.board, feedback=feedback, nudge=nudge),
            thinking=self.thinking, max_tokens=4096 if self.thinking == "enabled" else 1000 if speech else 256,
        )
