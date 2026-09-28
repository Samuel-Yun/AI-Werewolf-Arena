class IllegalAction(ValueError):
    """The action parsed successfully but violates a game rule."""


class InvariantViolation(RuntimeError):
    """Canonical state is inconsistent; never continue silently."""


class GameLimitExceeded(RuntimeError):
    """A configured day or event budget has been exhausted."""


class ReplayError(ValueError):
    """An event log is incomplete, corrupt, or out of order."""

