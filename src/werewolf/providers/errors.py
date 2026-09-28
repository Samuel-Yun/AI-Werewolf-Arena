class ProviderError(RuntimeError):
    """A request failed; the runner may retry or use its legal fallback."""


class FatalProviderError(ProviderError):
    """Invalid credentials or exhausted request budget: stop the live run."""

