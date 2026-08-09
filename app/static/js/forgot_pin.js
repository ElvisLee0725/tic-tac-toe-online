// Forgot-PIN request form. Posts to /api/pin-recovery/request and shows
// whatever message the server returns verbatim -- the response is
// deliberately worded identically whether or not anything was actually
// sent (anti-enumeration, DESIGN_V2.md Section 1.4), so this file has no
// case-specific branching to get wrong.
(function () {
    const form = document.getElementById("forgot-pin-form");
    const resultEl = document.getElementById("forgot-pin-result");

    form.addEventListener("submit", async function (evt) {
        evt.preventDefault();
        resultEl.hidden = true;

        const display_name = document.getElementById("fp_display_name").value.trim();
        const email = document.getElementById("fp_email").value.trim();

        try {
            const res = await fetch("/api/pin-recovery/request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ display_name, email }),
            });
            const data = await res.json();
            resultEl.textContent = data.message || "Request submitted.";
            resultEl.hidden = false;
        } catch (err) {
            resultEl.textContent = "Something went wrong. Please try again.";
            resultEl.hidden = false;
        }
    });
})();
