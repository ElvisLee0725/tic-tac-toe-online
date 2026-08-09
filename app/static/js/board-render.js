// Shared board-rendering logic, factored out of v1's board.js so it can
// also back live-board.js's polling cross-device board without
// duplicating the cell-grid rendering (DESIGN_V2.md Section 4). Only the
// cell grid itself lives here -- status text stays in each caller since
// it differs by mode (vs AI / vs local human / vs live opponent).
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

    return { renderBoard: renderBoard };
})();
