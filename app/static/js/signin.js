// Small helper for the sign-in / create-profile form.
// Posts to /api/session; on success the server sets the session cookie
// and we redirect home. On failure, shows the server's error message.
(function () {
    const form = document.getElementById("signin-form");
    const errorEl = document.getElementById("signin-error");

    form.addEventListener("submit", async function (evt) {
        evt.preventDefault();
        errorEl.hidden = true;

        const display_name = document.getElementById("display_name").value.trim();
        const pin = document.getElementById("pin").value.trim();

        try {
            const res = await fetch("/api/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ display_name, pin }),
            });
            const data = await res.json();
            if (res.ok) {
                window.location.href = "/";
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
        if (data.error === "wrong_pin") {
            return "That name is taken -- enter the correct PIN or choose another name.";
        }
        if (data.error === "validation_error") {
            return data.message || "Please check your name and PIN.";
        }
        return data.message || "Sign-in failed.";
    }
})();
