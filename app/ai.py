"""
AI move selection. (DESIGN.md Section 6.)

Scope note (2026-08-03 stakeholder direction): today's deliverable is
scoped to U1 (profiles) + U2 (play a full game vs. Easy AI) only.
Medium and Hard (minimax) are explicitly deferred to a later slice and
are NOT implemented yet -- `select_move` only supports difficulty
"easy" right now and raises NotImplementedError for "medium"/"hard" so
that's obvious if something tries to call them early. games_api.py
also rejects "medium"/"hard" at the request-validation layer with a
clear error, before ever reaching here.
"""

import random
from typing import List

from app import game as game_rules


def easy_move(board: List[str], ai_mark: str) -> int:
    """
    Easy (FR-11): uniform-random choice among currently-empty cells.
    No win/block checking at all -- deliberately weak play.
    """
    return random.choice(game_rules.legal_moves(board))


def medium_move(board: List[str], ai_mark: str) -> int:
    raise NotImplementedError("Medium AI is deferred to a later slice.")


def hard_move(board: List[str], ai_mark: str) -> int:
    raise NotImplementedError("Hard AI (minimax) is deferred to a later slice.")


SUPPORTED_DIFFICULTIES = {"easy": easy_move}


def select_move(board: List[str], ai_mark: str, difficulty: str) -> int:
    fn = SUPPORTED_DIFFICULTIES.get(difficulty)
    if fn is None:
        raise NotImplementedError(f"Difficulty '{difficulty}' is not implemented yet.")
    return fn(board, ai_mark)
