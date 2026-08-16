/* Shared UI polish used across the login/SSO, admin, welcome, and success
   pages: toast notifications, scroll-triggered reveal, count-up numbers,
   skeleton-to-loaded photo swaps, and a loading state on the admin sign-in
   button. Kept as one small vanilla module (no animation library) so it
   stays cheap to load on every page view for a portal ~300 staff use daily. */
(function () {
  "use strict";

  const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ensureToastRegion() {
    let region = document.getElementById("toast-region");
    if (!region) {
      region = document.createElement("div");
      region.id = "toast-region";
      region.className = "toast-region";
      region.setAttribute("aria-live", "polite");
      region.setAttribute("aria-atomic", "true");
      document.body.appendChild(region);
    }
    return region;
  }

  function toast(message, type) {
    if (!message) return;
    const region = ensureToastRegion();
    const el = document.createElement("div");
    el.className = `toast toast--${type || "info"}`;
    el.innerHTML = `<span>${message}</span><button type="button" class="toast__close" aria-label="Dismiss">&times;</button>`;
    region.appendChild(el);

    const remove = () => {
      el.classList.add("is-leaving");
      setTimeout(() => el.remove(), 250);
    };
    el.querySelector(".toast__close").addEventListener("click", remove);
    const timer = setTimeout(remove, 4200);
    el.addEventListener("mouseenter", () => clearTimeout(timer));
  }

  function initFlashToast() {
    const data = document.getElementById("flash-toast-data");
    if (!data) return;
    const message = data.dataset.message;
    const type = data.dataset.type || "success";
    data.remove();
    if (message) toast(message, type);
  }

  function initClickToast() {
    document.addEventListener("click", (e) => {
      const el = e.target.closest("[data-toast-message]");
      if (!el) return;
      toast(el.dataset.toastMessage, el.dataset.toastType || "success");
    });
  }

  function initScrollReveal() {
    const targets = document.querySelectorAll(".scroll-reveal");
    if (!targets.length) return;
    if (REDUCED_MOTION || !("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    targets.forEach((el) => observer.observe(el));
  }

  function animateCountUp(el) {
    const target = parseFloat(el.dataset.countup);
    if (!isFinite(target)) return;
    if (REDUCED_MOTION) {
      el.textContent = target.toLocaleString();
      return;
    }
    const duration = 1100;
    const start = performance.now();
    const from = 0;
    function tick(now) {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(from + (target - from) * eased).toLocaleString();
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initCountUp() {
    const targets = document.querySelectorAll("[data-countup]");
    if (!targets.length) return;
    if (!("IntersectionObserver" in window)) {
      targets.forEach(animateCountUp);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            animateCountUp(entry.target);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.4 }
    );
    targets.forEach((el) => observer.observe(el));
  }

  function initSkeletonPhotos() {
    document.querySelectorAll("[data-skeleton-wrap]").forEach((wrap) => {
      const img = wrap.querySelector("img");
      if (!img) {
        wrap.classList.remove("skeleton");
        return;
      }
      const clear = () => wrap.classList.remove("skeleton");
      if (img.complete) {
        clear();
      } else {
        img.addEventListener("load", clear, { once: true });
        img.addEventListener("error", clear, { once: true });
      }
    });
  }

  function initAdminSpinner() {
    document.querySelectorAll(".btn-admin-signin").forEach((btn) => {
      const form = btn.closest("form");
      if (!form) return;
      form.addEventListener("submit", () => btn.classList.add("is-loading"));
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initFlashToast();
    initClickToast();
    initScrollReveal();
    initCountUp();
    initSkeletonPhotos();
    initAdminSpinner();
  });

  window.MDXUI = { toast };
})();
