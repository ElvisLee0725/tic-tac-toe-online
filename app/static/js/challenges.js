// Polls GET /api/challenges for the nav badge (DESIGN_V2.md Section
// 2.2.1), on every page (loaded from base.html when signed in). If the
// current page also has the full incoming/outgoing list markup (the
// /challenges page), this same poll also renders those lists and wires
// up send/accept/decline/cancel -- one file, per the v2 project
// structure (Section 4), rather than splitting badge vs. page logic.
(function () {
    const POLL_INTERVAL_MS = 10000;

    const badge = document.getElementById("challenge-badge");
    const incomingList = document.getElementById("incoming-list");
    const outgoingList = document.getElementById("outgoing-list");
    const sendForm = document.getElementById("send-challenge-form");
    const sendError = document.getElementById("send-challenge-error");

    function renderBadge(count) {
        if (!badge) return;
        if (count > 0) {
            badge.textContent = String(count);
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    }

    function renderList(el, items, kind) {
        if (!el) return;
        el.innerHTML = "";
        if (items.length === 0) {
            const li = document.createElement("li");
            li.className = "muted";
            li.textContent = kind === "incoming" ? "No incoming challenges." : "No outgoing challenges.";
            el.appendChild(li);
            return;
        }
        for (const item of items) {
            const li = document.createElement("li");
            const label = document.createElement("span");
            label.textContent =
                kind === "incoming"
                    ? `${item.challenger_name} challenged you`
                    : `You challenged ${item.invitee_name}`;
            li.appendChild(label);

            if (kind === "incoming") {
                li.appendChild(makeActionButton("Accept", () => respond(item.challenge_id, "accept")));
                li.appendChild(makeActionButton("Decline", () => respond(item.challenge_id, "decline")));
            } else {
                li.appendChild(makeActionButton("Cancel", () => respond(item.challenge_id, "cancel")));
            }
            el.appendChild(li);
        }
    }

    function makeActionButton(text, onClick) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = text;
        btn.className = "btn btn-secondary btn-sm list-action";
        btn.addEventListener("click", onClick);
        return btn;
    }

    async function respond(challengeId, action) {
        const method = action === "cancel" ? "DELETE" : "POST";
        const url =
            action === "cancel"
                ? `/api/challenges/${challengeId}`
                : `/api/challenges/${challengeId}/${action}`;
        try {
            const res = await fetch(url, { method: method });
            if (action === "accept" && res.ok) {
                const data = await res.json();
                if (data.game_id) {
                    window.location.href = `/play/live/${data.game_id}`;
                    return;
                }
            }
        } finally {
            refresh();
        }
    }

    async function refresh() {
        try {
            const res = await fetch("/api/challenges");
            if (!res.ok) {
                renderBadge(0);
                return;
            }
            const data = await res.json();
            renderBadge((data.incoming || []).length);
            if (incomingList) renderList(incomingList, data.incoming || [], "incoming");
            if (outgoingList) renderList(outgoingList, data.outgoing || [], "outgoing");
        } catch (err) {
            // Silent -- a failed poll shouldn't disrupt the rest of the page.
        }
    }

    if (sendForm) {
        sendForm.addEventListener("submit", async function (evt) {
            evt.preventDefault();
            sendError.hidden = true;
            const invitee_name = document.getElementById("invitee_name").value.trim();
            try {
                const res = await fetch("/api/challenges", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ invitee_name }),
                });
                const data = await res.json();
                if (!res.ok) {
                    sendError.textContent = data.message || "Could not send challenge.";
                    sendError.hidden = false;
                    return;
                }
                document.getElementById("invitee_name").value = "";
                refresh();
            } catch (err) {
                sendError.textContent = "Something went wrong. Please try again.";
                sendError.hidden = false;
            }
        });
    }

    refresh();
    setInterval(refresh, POLL_INTERVAL_MS);
})();
