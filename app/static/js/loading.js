// Shared .is-loading helper (DESIGN_V2.md 3.4, FR-66): every JS file that
// calls fetch() puts the triggering element into this state immediately
// before the call and takes it back out once the response resolves,
// success or failure, so the UI never appears to silently swallow a
// click. One tiny module -- same shared-module precedent as
// board-render.js -- instead of duplicating the same few lines in every
// file that calls fetch().
window.TTTLoading = (function () {
    function start(el) {
        if (!el) return;
        el.classList.add("is-loading");
        if ("disabled" in el) el.disabled = true;
    }
    function stop(el) {
        if (!el) return;
        el.classList.remove("is-loading");
        if ("disabled" in el) el.disabled = false;
    }
    return { start: start, stop: stop };
})();
