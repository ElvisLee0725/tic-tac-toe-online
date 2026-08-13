"""
AI move selection. (DESIGN.md Section 6.)

Easy, Medium, and Hard (minimax) are all implemented and dispatched via
select_move(). Human-vs-human (local and cross-device) doesn't use this
module at all -- see games_api.py and live_games_api.py.
"""

import random
from typing import List, Optional, Tuple

from app import game as game_rules

CENTER = 4
CORNERS = (0, 2, 6, 8)
EDGES = (1, 3, 5, 7)


def easy_move(board: List[str], ai_mark: str) -> int:
    """
    Easy (FR-11): uniform-random choice among currently-empty cells.
    No win/block checking at all -- deliberately weak play.
    """
    return random.choice(game_rules.legal_moves(board))


def _find_winning_cell(board: List[str], mark: str) -> Optional[int]:
    """Return an empty cell that would complete a line for `mark`, if any."""
    for cell in game_rules.legal_moves(board):
        trial = game_rules.apply_move(board, cell, mark)
        if game_rules.winner(trial) == mark:
            return cell
    return None


def medium_move(board: List[str], ai_mark: str) -> int:
    """
    Medium (FR-12, PRD Q3): fixed 3-step heuristic, in order:
      1. Immediate win if available.
      2. Else immediate block of the opponent's win if available.
      3. Else pick randomly among remaining empty cells, weighted
         center > corners > edges. No lookahead beyond one ply, so
         Medium is beatable but not trivial.
    """
    opp_mark = game_rules.other_mark(ai_mark)

    win_cell = _find_winning_cell(board, ai_mark)
    if win_cell is not None:
        return win_cell

    block_cell = _find_winning_cell(board, opp_mark)
    if block_cell is not None:
        return block_cell

    legal = game_rules.legal_moves(board)
    weights = []
    for cell in legal:
        if cell == CENTER:
            weights.append(3)
        elif cell in CORNERS:
            weights.append(2)
        else:
            weights.append(1)
    return random.choices(legal, weights=weights, k=1)[0]


def _minimax(board: List[str], mark_to_move: str, ai_mark: str, depth: int) -> Tuple[int, Optional[int]]:
    """
    Returns (score, best_cell) from the perspective of maximizing ai_mark's
    outcome. score = 10 - depth for an ai_mark win, depth - 10 for an
    ai_mark loss, 0 for a tie -- depth-scored so the AI prefers a faster
    win / slower loss (DESIGN.md Section 6).
    """
    w = game_rules.winner(board)
    if w == ai_mark:
        return 10 - depth, None
    if w is not None:  # opponent won
        return depth - 10, None
    if game_rules.is_full(board):
        return 0, None

    opp_mark = game_rules.other_mark(ai_mark)
    maximizing = mark_to_move == ai_mark
    best_score = -10_000 if maximizing else 10_000
    best_cell = None

    for cell in game_rules.legal_moves(board):
        trial = game_rules.apply_move(board, cell, mark_to_move)
        score, _ = _minimax(trial, opp_mark if mark_to_move == ai_mark else ai_mark, ai_mark, depth + 1)
        if maximizing:
            if score > best_score:
                best_score, best_cell = score, cell
        else:
            if score < best_score:
                best_score, best_cell = score, cell

    return best_score, best_cell


def hard_move(board: List[str], ai_mark: str) -> int:
    """
    Hard (FR-13, PRD Q2): full minimax over the remaining game tree.
    Never loses -- a perfectly-played game against Hard ends in a tie,
    and any suboptimal human move can be exploited into an AI win.
    Alpha-beta pruning skipped per DESIGN.md Section 6 (not needed on
    a 3x3 board).
    """
    _, best_cell = _minimax(board, ai_mark, ai_mark, 0)
    if best_cell is None:
        # Shouldn't happen if called with a non-terminal board, but fall
        # back to any legal move defensively.
        return random.choice(game_rules.legal_moves(board))
    return best_cell


SUPPORTED_DIFFICULTIES = {
    "easy": easy_move,
    "medium": medium_move,
    "hard": hard_move,
}


def select_move(board: List[str], ai_mark: str, difficulty: str) -> int:
    fn = SUPPORTED_DIFFICULTIES.get(difficulty)
    if fn is None:
        raise NotImplementedError(f"Difficulty '{difficulty}' is not implemented yet.")
    return fn(board, ai_mark)
