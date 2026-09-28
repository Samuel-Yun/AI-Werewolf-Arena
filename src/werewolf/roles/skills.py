from werewolf.config import BoardConfig


def hunter_can_shoot(board: BoardConfig, causes: list[str]) -> bool:
    """A blocked cause wins over an allowed cause, including a double kill."""
    return bool(set(causes) & set(board.hunter.allowed_causes)) and not (
        set(causes) & set(board.hunter.blocked_causes)
    )
