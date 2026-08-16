/* Decorative mouse-parallax tilt for the sample Digital ID card on the
   login page. Purely cosmetic — never touches the real ID card renderer. */
(function () {
    "use strict";

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;

    const wrap = document.getElementById("sample-id-wrap");
    const card = document.getElementById("sample-idcard");
    if (!wrap || !card) return;

    // Tilt is applied to the wrapper, not the card itself, so it composes
    // with (rather than fights) the card's own CSS float/rotate animation.
    let raf = null;

    wrap.addEventListener("pointermove", (e) => {
        const rect = wrap.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width - 0.5;
        const py = (e.clientY - rect.top) / rect.height - 0.5;
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
            wrap.style.transform = `rotateY(${px * 10}deg) rotateX(${-py * 10}deg)`;
        });
    }, { passive: true });

    wrap.addEventListener("pointerleave", () => {
        if (raf) cancelAnimationFrame(raf);
        wrap.style.transform = "";
    }, { passive: true });
})();
