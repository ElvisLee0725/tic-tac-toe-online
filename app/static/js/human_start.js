// Starts a local vs-Human game (FR-9/FR-10). The signed-in device owner
// is X; the opponent (O) is verified by name+PIN via POST /api/games
// itself (reusing the same create-or-signin logic as /api/session,
// server-side). On success we stash the created game's initial state in
// sessionStorage and navigate to /game?mode=human -- this keeps the
// opponent's PIN out of the URL/browser history (no GET resync endpoint
// exists yet, so board.js picks its starting state up from here instead
// of re-fetching it).
(function () {
    const form = document.getElementById("human-form");
    if (!form) return;
    const errorEl = document.getElementById("human-error");

    form.addEventListener("submit", async function (evt) {
        evt.preventDefault();
        errorEl.hidden = true;

        const opponent_name = document.getElementById("opponent_name").value.trim();
        const opponent_pin = document.getElementById("opponent_pin").value.trim();

        try {
            const res = await fetch("/api/games", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode: "human", opponent_name, opponent_pin }),
            });
            const data = await res.json();
            if (res.ok) {
                sessionStorage.setItem("ttt_pending_game", JSON.stringify(data));
                window.location.href = "/game?mode=human";
                return;
            }
            errorEl.textContent = describeError(data);
            errorEl.hidden = false;
        } catch (err) {
            errorEl.textContent = "Something went wrong. Please try again.";
            errorEl.hidden = false;
        }
    });

    function describeError(data) {
        if (data.error === "opponent_signin_failed") {
            return "That username and PIN aren't recognized -- your opponent needs an existing account.";
        }
        if (data.error === "cannot_play_self") {
            return "Enter a different player as your opponent.";
        }
        if (data.error === "validation_error") {
            return data.message || "Please check the opponent's name and PIN.";
        }
        if (data.error === "not_signed_in") {
            return "You need to be signed in to start a local game.";
        }
        return data.message || "Could not start the game.";
    }
})();
