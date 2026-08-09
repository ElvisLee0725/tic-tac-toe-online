// fetch()-driven game board. Server is fully authoritative (DESIGN.md
// Section 4) -- this file only ever sends the mover's chosen cell.
//
// mode=ai: reads mode/difficulty/guest from the URL query string and
// creates the game itself via POST /api/games (no secrets involved).
//
// mode=human: the game was already created by human_start.js (from the
// home page, so the opponent's PIN never touches this page/URL); its
// initial state is handed off via sessionStorage under
// "ttt_pending_game". Both local players click on the same board in
// turn -- no auto AI response, no per-request identity check (same
// device/browser for both, per FR-9).
(function () {
    const boardEl = document.getElementById("board");
    const statusEl = document.getElementById("game-status");

    const params = new URLSearchParams(window.location.search);
    const mode = params.get("mode") || "ai";
    const difficulty = params.get("difficulty") || "easy";
    const guest = params.get("guest") === "true";

    let gameId = null;
    let board = "_________";
    let currentTurn = "X";
    let status = "in_progress";
    let xName = "X";
    let oName = "O";
    let busy = false;

    function applyGameState(data) {
        gameId = data.game_id;
        board = data.board;
        currentTurn = data.current_turn;
        status = data.status;
        if (data.x) xName = data.x.display_name;
        if (data.o) oName = data.o.display_name;
    }

    function render() {
        const notMyTurnYet = mode === "ai" && currentTurn !== "X";
        const cellsClickable = status === "in_progress" && !busy && !notMyTurnYet;
        TTTBoardRender.renderBoard(boardEl, board, {
            winningLine: null, // v1's response shape doesn't carry this yet (UI overhaul increment)
            cellsClickable: cellsClickable,
            onCellClick: makeMove,
        });
        renderStatus();
    }

    function renderStatus() {
        statusEl.textContent = "";
        if (mode === "human") {
            if (status === "in_progress") {
                const name = currentTurn === "X" ? xName : oName;
                statusEl.textContent = `${name}'s turn (${currentTurn})`;
            } else if (status === "x_won") {
                statusEl.textContent = `${xName} (X) wins!`;
            } else if (status === "o_won") {
                statusEl.textContent = `${oName} (O) wins!`;
            } else if (status === "tie") {
                statusEl.textContent = "It's a tie.";
            }
        } else {
            if (status === "in_progress") {
                statusEl.textContent = currentTurn === "X" ? "Your move (X)" : "AI is thinking...";
            } else if (status === "x_won") {
                statusEl.textContent = "You win!";
            } else if (status === "o_won") {
                statusEl.textContent = "AI wins.";
            } else if (status === "tie") {
                statusEl.textContent = "It's a tie.";
            }
        }
        if (status !== "in_progress") {
            const again = document.createElement("a");
            again.href = mode === "human" ? "/" : window.location.pathname + window.location.search;
            again.textContent = mode === "human" ? " Back to home to start another game" : " New game";
            statusEl.appendChild(again);
        }
    }

    async function startAiGame() {
        statusEl.textContent = "Starting game...";
        const res = await fetch("/api/games", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode, difficulty, guest }),
        });
        const data = await res.json();
        if (!res.ok) {
            statusEl.textContent = "Could not start game: " + (data.message || data.error);
            return;
        }
        applyGameState(data);
        render();
    }

    function startHumanGame() {
        const raw = sessionStorage.getItem("ttt_pending_game");
        if (!raw) {
            statusEl.textContent = "No game in progress. Start a new local game from the home page.";
            const link = document.createElement("a");
            link.href = "/";
            link.textContent = " Go home";
            statusEl.appendChild(link);
            return;
        }
        sessionStorage.removeItem("ttt_pending_game");
        applyGameState(JSON.parse(raw));
        render();
    }

    async function makeMove(cell) {
        if (busy || status !== "in_progress" || board[cell] !== "_") return;
        busy = true;
        render();
        try {
            const res = await fetch(`/api/games/${gameId}/moves`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cell }),
            });
            const data = await res.json();
            if (!res.ok) {
                statusEl.textContent = "Move rejected: " + (data.message || data.error);
                busy = false;
                render();
                return;
            }
            board = data.board;
            currentTurn = data.current_turn;
            status = data.status;
        } finally {
            busy = false;
            render();
        }
    }

    if (mode === "human") {
        startHumanGame();
    } else {
        startAiGame();
    }
})();
