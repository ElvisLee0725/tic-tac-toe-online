// Sign-out button in the shared nav (base.html). Calls DELETE
// /api/session, then redirects home so the nav re-renders signed-out.
(function () {
    const btn = document.getElementById("sign-out-btn");
    if (!btn) return;
    btn.addEventListener("click", async function () {
        TTTLoading.start(btn);
        try {
            await fetch("/api/session", { method: "DELETE" });
        } finally {
            window.location.href = "/";
        }
    });
})();
