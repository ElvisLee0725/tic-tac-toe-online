// Polling variant of the board UI (DESIGN_V2.md Section 2.1/2.3). Polls
// GET /api/live-games/{id} every 2s while the tab is visible (paused via
// the Page Visibility API when backgrounded, per Section 2.1), POSTs
// moves the same authoritative-server way v1's board.js does. Shares
// cell-grid rendering with board.js via board-render.js (Section 4).
(function () {
    const cfg = window.TTT_LIVE_GAME;
    const boardEl = document.getElementById("board");
    const statusEl = document.getElementById("game-status");
    const POLL_MS = 2000;

    let board = "_________";
    let currentTurn = "X";
    let status = "in_progress";
    let winningLine = null;
    let opponentState = "connected";
    let busy = false;
    let pollTimer = null;

    function opponentName() {
        return cfg.myMark === "X" ? cfg.oName : cfg.xName;
    }

    function render() {
        const cellsClickable = status === "in_progress" && currentTurn === cfg.myMark && !busy;
        TTTBoardRender.renderBoard(boardEl, board, {
            winningLine: winningLine,
            cellsClickable: cellsClickable,
            onCellClick: makeMove,
        });
        renderStatus();
    }

    function renderStatus() {
        let state, text, mark;

        if (status === "in_progress") {
            state = "turn";
            mark = currentTurn;
            text = currentTurn === cfg.myMark ? "Your move" : `Waiting for ${opponentName()}...`;
            if (opponentState === "stale") {
                text += ` (${opponentName()} seems to have gone quiet...)`;
            }
        } else if (status === "x_won" || status === "o_won") {
            const winnerMark = status === "x_won" ? "X" : "O";
            mark = winnerMark;
            state = winnerMark === cfg.myMark ? "win" : "loss";
            text = winnerMark === cfg.myMark ? "You win!" : `${opponentName()} wins.`;
        } else if (status === "tie") {
            state = "tie";
            text = "It's a tie.";
        } else if (status === "forfeited_x" || status === "forfeited_o") {
            const forfeitingMark = status === "forfeited_x" ? "X" : "O";
            const iWon = forfeitingMark !== cfg.myMark;
            state = iWon ? "win" : "loss";
            text = iWon
                ? `${opponentName()} was inactive too long -- you win by forfeit.`
                : `You were inactive too long -- ${opponentName()} wins by forfeit.`;
        }

        TTTBoardRender.renderStatusBanner(statusEl, state, text, mark);

        if (status !== "in_progress") {
            stopPolling();
            const link = document.createElement("a");
            link.href = "/challenges";
            link.textContent = "Back to Challenges";
            statusEl.appendChild(link);
        }
    }

    function applyState(data) {
        board = data.board;
        currentTurn = data.current_turn;
        status = data.status;
        winningLine = data.winning_line;
        opponentState = data.opponent_state;
    }

    async function poll() {
        if (document.hidden) return;
        try {
            const res = await fetch(`/api/live-games/${cfg.gameId}`);
            if (!res.ok) return;
            const data = await res.json();
            applyState(data);
            render();
        } catch (err) {
            // Silent -- try again next interval.
        }
    }

    async function makeMove(cell) {
        if (busy || status !== "in_progress" || currentTurn !== cfg.myMark || board[cell] !== "_") return;
        busy = true;
        render();
        try {
            const res = await fetch(`/api/live-games/${cfg.gameId}/moves`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cell: cell }),
            });
            const data = await res.json();
            if (data && data.board) {
                applyState(data);
            }
        } finally {
            busy = false;
            render();
        }
    }

    function startPolling() {
        if (pollTimer) return;
        poll();
        pollTimer = setInterval(poll, POLL_MS);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    document.addEventListener("visibilitychange", function () {
        if (document.hidden) {
            stopPolling();
        } else if (status === "in_progress") {
            startPolling();
        }
    });

    startPolling();
})();
