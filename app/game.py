"""
Board rules: win/tie detection, move validation. (DESIGN.md Section 5.)

Board representation: a 9-character list, index 0-8 mapped
left-to-right, top-to-bottom (0 1 2 / 3 4 5 / 6 7 8), '_' for empty.
"""

from typing import List, Optional

EMPTY = "_"

LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columns
    (0, 4, 8), (2, 4, 6),              # diagonals
]


def new_board() -> List[str]:
    return [EMPTY] * 9


def other_mark(mark: str) -> str:
    return "O" if mark == "X" else "X"


def winner(board: List[str]) -> Optional[str]:
    """Return 'X' or 'O' if that mark has a completed line, else None."""
    for a, b, c in LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return None


def is_full(board: List[str]) -> bool:
    return EMPTY not in board


def is_terminal(board: List[str]) -> bool:
    return winner(board) is not None or is_full(board)


def game_status(board: List[str]) -> str:
    """Return one of: 'in_progress', 'x_won', 'o_won', 'tie'."""
    w = winner(board)
    if w == "X":
        return "x_won"
    if w == "O":
        return "o_won"
    if is_full(board):
        return "tie"
    return "in_progress"


def legal_moves(board: List[str]) -> List[int]:
    return [i for i, v in enumerate(board) if v == EMPTY]


def is_legal_move(board: List[str], cell: int) -> bool:
    if not isinstance(cell, int) or cell < 0 or cell > 8:
        return False
    return board[cell] == EMPTY


def apply_move(board: List[str], cell: int, mark: str) -> List[str]:
    """Return a new board with `mark` placed at `cell`. Caller must validate first."""
    new = list(board)
    new[cell] = mark
    return new
