(function () {
    "use strict";
    const dot = document.getElementById("nav-status-dot");
    const text = document.getElementById("nav-status-text");
    if (!dot) return;

    fetch("/healthz")
        .then((r) => { if (!r.ok) throw new Error("bad status"); return r.json(); })
        .then(() => { dot.classList.remove("is-down"); })
        .catch(() => {
            dot.classList.add("is-down");
            if (text) text.textContent = text.textContent + " · offline";
        });
})();
