// fetch()-driven game board. Reads mode/difficulty/guest from the URL
// query string, creates a game via POST /api/games, then plays it via
// POST /api/games/{id}/moves. Server is fully authoritative (DESIGN.md
// Section 4) -- this file only ever sends the human's chosen cell.
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
    let busy = false;

    function render() {
        boardEl.innerHTML = "";
        for (let i = 0; i < 9; i++) {
            const btn = document.createElement("button");
            btn.className = "cell";
            btn.textContent = board[i] === "_" ? "" : board[i];
            const disabled = board[i] !== "_" || status !== "in_progress" || busy || currentTurn !== "X";
            btn.disabled = disabled;
            btn.addEventListener("click", () => makeMove(i));
            boardEl.appendChild(btn);
        }
        renderStatus();
    }

    function renderStatus() {
        if (status === "in_progress") {
            statusEl.textContent = currentTurn === "X" ? "Your move (X)" : "AI is thinking...";
        } else if (status === "x_won") {
            statusEl.textContent = "You win!";
        } else if (status === "o_won") {
            statusEl.textContent = "AI wins.";
        } else if (status === "tie") {
            statusEl.textContent = "It's a tie.";
        }
        if (status !== "in_progress") {
            const again = document.createElement("a");
            again.href = window.location.pathname + window.location.search;
            again.textContent = " New game";
            statusEl.appendChild(again);
        }
    }

    async function startGame() {
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
        gameId = data.game_id;
        board = data.board;
        currentTurn = data.current_turn;
        status = data.status;
        render();
    }

    async function makeMove(cell) {
        if (busy || status !== "in_progress" || currentTurn !== "X" || board[cell] !== "_") return;
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

    startGame();
})();
