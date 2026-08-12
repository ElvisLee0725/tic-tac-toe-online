// Forgot-PIN request form. Posts to /api/pin-recovery/request and shows
// whatever message the server returns verbatim -- the response is
// deliberately worded identically whether or not anything was actually
// sent (anti-enumeration, DESIGN_V2.md Section 1.4), so this file has no
// case-specific branching to get wrong.
(function () {
    const form = document.getElementById("forgot-pin-form");
    const resultEl = document.getElementById("forgot-pin-result");
    const submitBtn = form.querySelector("button[type=submit]");

    form.addEventListener("submit", async function (evt) {
        evt.preventDefault();
        resultEl.hidden = true;
        resultEl.className = "muted";

        const display_name = document.getElementById("fp_display_name").value.trim();
        const email = document.getElementById("fp_email").value.trim();

        TTTLoading.start(submitBtn);
        try {
            const res = await fetch("/api/pin-recovery/request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ display_name, email }),
            });
            const data = await res.json();
            // Deliberately generic wording either way (anti-enumeration,
            // DESIGN_V2.md Section 1.4) -- shown as a neutral status
            // message, not styled as an error, since it isn't one.
            resultEl.textContent = data.message || "Request submitted.";
            resultEl.hidden = false;
        } catch (err) {
            // This branch IS a genuine error (request never reached the
            // server), so it gets the distinct error treatment.
            resultEl.textContent = "Something went wrong. Please try again.";
            resultEl.className = "field-error";
            resultEl.hidden = false;
        } finally {
            TTTLoading.stop(submitBtn);
        }
    });
})();
