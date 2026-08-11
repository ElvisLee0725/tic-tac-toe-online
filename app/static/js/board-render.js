// Shared board-rendering logic, factored out of v1's board.js so it can
// also back live-board.js's polling cross-device board without
// duplicating the cell-grid rendering (DESIGN_V2.md Section 4). Used by
// both the request/response local-game flow (board.js) and the polling
// cross-device flow (live-board.js) so FR-62's visual logic (winning-line
// highlight, turn/outcome banner) lives in exactly one place.
window.TTTBoardRender = (function () {
    function renderBoard(boardEl, boardStr, opts) {
        // opts: { winningLine: [a,b,c]|null, cellsClickable: bool, onCellClick: fn(i) }
        opts = opts || {};
        const winSet = new Set(opts.winningLine || []);
        boardEl.innerHTML = "";
        for (let i = 0; i < 9; i++) {
            const btn = document.createElement("button");
            btn.className = "cell";
            if (winSet.has(i)) btn.classList.add("cell-win");
            btn.textContent = boardStr[i] === "_" ? "" : boardStr[i];
            const filled = boardStr[i] !== "_";
            btn.disabled = filled || !opts.cellsClickable;
            btn.addEventListener("click", function () {
                if (opts.onCellClick) opts.onCellClick(i);
            });
            boardEl.appendChild(btn);
        }
    }

    // Icons are plain text glyphs (no emoji/external icon set), styled
    // via CSS -- consistent with the no-framework/no-build-step approach.
    const STATE_ICONS = { win: "✓", loss: "✕", tie: "–", turn: "" };

    // Persistent turn indicator / win-loss-tie outcome banner (FR-62).
    // state: "turn" | "win" | "loss" | "tie"
    // mark: "X" | "O" | null -- when given, renders a color-coded chip
    //       with the letter always shown too (never color alone).
    function renderStatusBanner(el, state, text, mark) {
        el.innerHTML = "";
        let variant = state;
        if (state === "turn" && mark) {
            variant = "turn-" + mark.toLowerCase();
        }
        el.className = "status-banner status-banner--" + variant;

        if (mark) {
            const chip = document.createElement("span");
            chip.className = "mark-badge mark-badge--" + mark.toLowerCase();
            chip.textContent = mark;
            el.appendChild(chip);
        }

        const icon = document.createElement("span");
        icon.className = "status-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = STATE_ICONS[state] || "";
        el.appendChild(icon);

        const label = document.createElement("span");
        label.className = "status-text";
        label.textContent = text;
        el.appendChild(label);
    }

    return { renderBoard: renderBoard, renderStatusBanner: renderStatusBanner };
})();
