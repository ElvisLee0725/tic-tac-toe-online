// New-PIN form landed on via the emailed reset link (?token=...). Posts
// to /api/pin-recovery/reset; on success sends the player to sign in
// with their new PIN (this does NOT sign them in automatically -- all
// sessions were just invalidated server-side as part of the reset).
(function () {
    const form = document.getElementById("reset-pin-form");
    if (!form) return;
    const errorEl = document.getElementById("reset-pin-error");
    const token = document.getElementById("reset_token").value;
    const newPinField = document.getElementById("new_pin");
    const submitBtn = form.querySelector("button[type=submit]");

    form.addEventListener("submit", async function (evt) {
        evt.preventDefault();
        errorEl.hidden = true;
        newPinField.classList.remove("is-invalid");

        const new_pin = newPinField.value.trim();

        TTTLoading.start(submitBtn);
        try {
            const res = await fetch("/api/pin-recovery/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, new_pin }),
            });
            const data = await res.json();
            if (res.ok) {
                window.location.href = "/signin";
                return;
            }
            errorEl.textContent = describeError(data);
            errorEl.hidden = false;
            if (data.error === "validation_error") {
                newPinField.classList.add("is-invalid");
            }
        } catch (err) {
            errorEl.textContent = "Something went wrong. Please try again.";
            errorEl.hidden = false;
        } finally {
            TTTLoading.stop(submitBtn);
        }
    });

    function describeError(data) {
        if (data.error === "invalid_or_expired_token") {
            return "This link is invalid or expired. Request a new one from the Forgot PIN page.";
        }
        if (data.error === "validation_error") {
            return data.message || "Please enter a 4-digit PIN.";
        }
        return data.message || "Could not reset PIN.";
    }
})();
