// Sign In / Create Account -- two genuinely separate actions (2026-08-06
// revision) hitting two different endpoints, not one combined form.
(function () {
    const tabSignin = document.getElementById("tab-signin");
    const tabCreate = document.getElementById("tab-create");
    const panelSignin = document.getElementById("panel-signin");
    const panelCreate = document.getElementById("panel-create");

    function showTab(which) {
        const signinActive = which === "signin";
        panelSignin.hidden = !signinActive;
        panelCreate.hidden = signinActive;
        tabSignin.classList.toggle("active", signinActive);
        tabCreate.classList.toggle("active", !signinActive);
        tabSignin.setAttribute("aria-selected", String(signinActive));
        tabCreate.setAttribute("aria-selected", String(!signinActive));
    }

    tabSignin.addEventListener("click", () => showTab("signin"));
    tabCreate.addEventListener("click", () => showTab("create"));

    async function submitForm(path, formId, errorId, describeError, fieldsForError) {
        const form = document.getElementById(formId);
        const errorEl = document.getElementById(errorId);
        const submitBtn = form.querySelector("button[type=submit]");

        function clearFieldErrors() {
            form.querySelectorAll(".is-invalid").forEach(function (el) {
                el.classList.remove("is-invalid");
            });
        }
        function markFieldsInvalid(names) {
            (names || []).forEach(function (name) {
                const el = form.querySelector(`[name=${name}]`);
                if (el) el.classList.add("is-invalid");
            });
        }

        form.addEventListener("submit", async function (evt) {
            evt.preventDefault();
            errorEl.hidden = true;
            clearFieldErrors();

            const display_name = form.querySelector("[name=display_name]").value.trim();
            const pin = form.querySelector("[name=pin]").value.trim();
            const payload = { display_name, pin };
            const recoveryEmailField = form.querySelector("[name=recovery_email]");
            if (recoveryEmailField) {
                const recovery_email = recoveryEmailField.value.trim();
                if (recovery_email) payload.recovery_email = recovery_email;
            }

            TTTLoading.start(submitBtn);
            try {
                const res = await fetch(path, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (res.ok) {
                    window.location.href = "/";
                    return;
                }
                errorEl.textContent = describeError(data);
                errorEl.hidden = false;
                markFieldsInvalid(fieldsForError(data));
            } catch (err) {
                errorEl.textContent = "Something went wrong. Please try again.";
                errorEl.hidden = false;
            } finally {
                TTTLoading.stop(submitBtn);
            }
        });
    }

    submitForm(
        "/api/session",
        "signin-form",
        "signin-error",
        function (data) {
            if (data.error === "sign_in_failed") {
                return "That username and PIN aren't recognized.";
            }
            if (data.error === "validation_error") {
                return data.message || "Please check your name and PIN.";
            }
            return data.message || "Sign-in failed.";
        },
        function () {
            return ["display_name", "pin"];
        }
    );

    submitForm(
        "/api/session/new",
        "create-form",
        "create-error",
        function (data) {
            if (data.error === "name_taken") {
                return "That name is already taken -- sign in instead or choose another name.";
            }
            if (data.error === "validation_error") {
                return data.message || "Please check your name and PIN.";
            }
            return data.message || "Could not create account.";
        },
        function (data) {
            if (data.error === "name_taken") return ["display_name"];
            return ["display_name", "pin"];
        }
    );
})();
