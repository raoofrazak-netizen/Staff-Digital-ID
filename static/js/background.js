/* Firefly ambient background engine — Canvas2D. Three depth layers of warm
   floating light particles (ivory / champagne / muted gold, with a rare MDX
   red accent), each wandering along a slowly-turning heading rather than a
   straight line or flow-field vector, so no two fireflies ever move the
   same way at the same time. A handful of foreground particles occasionally
   flash brighter ("hero" flickers), a few carry a soft trailing light, and
   only very close foreground pairs ever draw a connecting thread — brief,
   faint, and never a persistent mesh. Cursor influence is a light drift-away,
   not a repulsion field.
   A CSS-level grain overlay (see .grain in style.css) sits above all of it. */
(function () {
    "use strict";

    const canvas = document.getElementById("bg-canvas");
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // --- Cubic-bezier evaluator, used to shape the cursor drift-away's
    // falloff curve (cubic-bezier(0.16, 1, 0.3, 1) — quick, no-overshoot decay). ---
    function cubicBezierY(x, x1, y1, x2, y2) {
        let t = x;
        for (let i = 0; i < 6; i++) {
            const cx = 3 * (1 - t) * (1 - t) * t * x1 + 3 * (1 - t) * t * t * x2 + t * t * t;
            const dx = cx - x;
            if (Math.abs(dx) < 1e-4) break;
            const dCx = 3 * (1 - t) * (1 - t) * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t * t * (1 - x2);
            t -= dx / (dCx || 1e-6);
            t = Math.min(1, Math.max(0, t));
        }
        return 3 * (1 - t) * (1 - t) * t * y1 + 3 * (1 - t) * t * t * y2 + t * t * t;
    }
    function driftFalloff(proximity) { return cubicBezierY(proximity, 0.16, 1, 0.3, 1); }

    // Weighted palette -- mostly warm ivory/champagne/gold, MDX red is a rare accent.
    const IVORY = [255, 244, 232];
    const CHAMPAGNE = [232, 199, 162];
    const GOLD = [201, 163, 143];
    const MDX_RED = [227, 6, 19];
    function pickColor() {
        const r = Math.random();
        if (r < 0.44) return IVORY;
        if (r < 0.78) return CHAMPAGNE;
        if (r < 0.95) return GOLD;
        return MDX_RED;
    }

    // --- Layer definitions: back to front. Background is smaller, dimmer,
    // slower and rendered with a slight blur; foreground is brighter,
    // larger and more visibly glowing. ---
    const LAYER_SPECS = {
        bg: { sizeMin: 0.7, sizeMax: 1.5, alphaMin: 0.14, alphaMax: 0.3, speedMin: 0.035, speedMax: 0.09, glow: 3, blurPx: 1.1, haloChance: 0.04, heroChance: 0 },
        mid: { sizeMin: 1.3, sizeMax: 2.3, alphaMin: 0.32, alphaMax: 0.55, speedMin: 0.08, speedMax: 0.18, glow: 7, blurPx: 0, haloChance: 0.14, heroChance: 0.05 },
        fg: { sizeMin: 2.1, sizeMax: 3.3, alphaMin: 0.55, alphaMax: 0.85, speedMin: 0.1, speedMax: 0.22, glow: 13, blurPx: 0, haloChance: 0.4, heroChance: 0.22 },
    };

    // --- Performance tiers: fewer, more deliberate fireflies than a dense
    // technical particle field -- this is meant to read as calm, not busy. ---
    function tierCounts() {
        const w = window.innerWidth;
        if (w < 640) return { bg: 34, mid: 20, fg: 7 };
        if (w < 1100) return { bg: 62, mid: 38, fg: 12 };
        return { bg: 92, mid: 54, fg: 18 };
    }

    let W = 0, H = 0, DPR = 1;
    let particles = [];
    const mouse = { x: -9999, y: -9999, active: false };
    const MOUSE_DRIFT_RADIUS = 90;
    const MAX_TRAILS = 4;
    const LINK_DIST = 46;
    let links = [];

    function resize() {
        W = window.innerWidth;
        H = window.innerHeight;
        if (!W || !H) { requestAnimationFrame(resize); return; }
        DPR = Math.min(window.devicePixelRatio || 1, 1.5);
        canvas.width = W * DPR;
        canvas.height = H * DPR;
        canvas.style.width = W + "px";
        canvas.style.height = H + "px";
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        seed();
    }

    function makeParticle(layer) {
        const spec = LAYER_SPECS[layer];
        const speed = spec.speedMin + Math.random() * (spec.speedMax - spec.speedMin);
        return {
            layer,
            x: Math.random() * W,
            y: Math.random() * H,
            angle: Math.random() * Math.PI * 2,
            turnSpeed: 0.15 + Math.random() * 0.35,
            speed,
            baseSpeed: speed,
            size: spec.sizeMin + Math.random() * (spec.sizeMax - spec.sizeMin),
            baseAlpha: spec.alphaMin + Math.random() * (spec.alphaMax - spec.alphaMin),
            color: pickColor(),
            glow: spec.glow,
            hasHalo: Math.random() < spec.haloChance,
            pulsePhase: Math.random() * Math.PI * 2,
            pulseSpeed: 0.25 + Math.random() * 0.5,
            driftBiasY: -(0.006 + Math.random() * 0.014),
            isHeroCandidate: Math.random() < spec.heroChance,
            heroActive: false,
            heroStart: 0,
            heroDuration: 1.6 + Math.random() * 1.2,
            nextHeroAt: 4 + Math.random() * 16,
            trailActive: false,
            trailUntil: 0,
            trail: [],
        };
    }

    function seed() {
        activeTrailCount = 0;
        if (reduceMotion) {
            // Static field: present, but fixed -- no wandering, pulsing,
            // hero flashes, trails or links once painted.
            const counts = { bg: 26, mid: 16, fg: 6 };
            particles = ["bg", "mid", "fg"].flatMap((layer) =>
                Array.from({ length: counts[layer] }, () => makeParticle(layer))
            );
            return;
        }
        const counts = tierCounts();
        particles = ["bg", "mid", "fg"].flatMap((layer) =>
            Array.from({ length: counts[layer] }, () => makeParticle(layer))
        );
        links = [];
    }

    function updateParticle(p, t, dt) {
        // Organic wander: heading drifts smoothly rather than snapping,
        // speed idles up and down a little too, so motion never reads as
        // mechanical or synchronized between particles.
        p.angle += (Math.random() - 0.5) * p.turnSpeed * dt;
        p.speed += (Math.random() - 0.5) * 0.01 * dt * 60;
        p.speed = Math.max(p.baseSpeed * 0.5, Math.min(p.baseSpeed * 1.5, p.speed));

        let vx = Math.cos(p.angle) * p.speed;
        let vy = Math.sin(p.angle) * p.speed + p.driftBiasY;

        if (mouse.active) {
            const dx = p.x - mouse.x, dy = p.y - mouse.y;
            const dist = Math.hypot(dx, dy) || 1;
            if (dist < MOUSE_DRIFT_RADIUS) {
                const force = driftFalloff(1 - dist / MOUSE_DRIFT_RADIUS) * 0.05;
                vx += (dx / dist) * force;
                vy += (dy / dist) * force;
            }
        }

        p.x += vx * dt * 60;
        p.y += vy * dt * 60;

        if (p.x < -10) p.x = W + 10; if (p.x > W + 10) p.x = -10;
        if (p.y < -12) p.y = H + 12; if (p.y > H + 12) p.y = -12;

        // Hero flicker: a rare, brief brighten-then-fade, never in sync --
        // each candidate schedules its own next flash independently.
        if (p.isHeroCandidate) {
            if (!p.heroActive && t >= p.nextHeroAt) {
                p.heroActive = true;
                p.heroStart = t;
            }
            if (p.heroActive && t - p.heroStart > p.heroDuration) {
                p.heroActive = false;
                p.nextHeroAt = t + 9 + Math.random() * 18;
            }
        }

        // Trails: only ever a couple of foreground particles at a time,
        // brief, and cleared quickly once done.
        if (p.layer === "fg") {
            if (!p.trailActive && Math.random() < 0.0009 && activeTrailCount < MAX_TRAILS) {
                p.trailActive = true;
                p.trailUntil = t + 1.4 + Math.random() * 1.6;
                p.trail = [];
                activeTrailCount++;
            }
            if (p.trailActive) {
                p.trail.push({ x: p.x, y: p.y, t });
                if (p.trail.length > 14) p.trail.shift();
                if (t > p.trailUntil) {
                    p.trailActive = false;
                    p.trail = [];
                    activeTrailCount--;
                }
            }
        }
    }

    function brightnessFor(p, t) {
        let mul = 0.75 + 0.25 * Math.sin(t * p.pulseSpeed + p.pulsePhase);
        if (p.heroActive) {
            const progress = (t - p.heroStart) / p.heroDuration;
            const envelope = Math.sin(Math.min(1, Math.max(0, progress)) * Math.PI);
            mul += envelope * 1.4;
        }
        return mul;
    }

    function drawParticle(p, t) {
        const mul = brightnessFor(p, t);
        const alpha = Math.min(1, p.baseAlpha * mul);
        const [r, g, b] = p.color;

        if (p.trail.length > 1) {
            for (let i = 1; i < p.trail.length; i++) {
                const a = p.trail[i], prev = p.trail[i - 1];
                const age = (t - a.t) / 1.5;
                const trailAlpha = Math.max(0, (1 - age)) * 0.14;
                if (trailAlpha <= 0.002) continue;
                ctx.strokeStyle = `rgba(${r},${g},${b},${trailAlpha.toFixed(3)})`;
                ctx.lineWidth = Math.max(0.4, p.size * 0.35);
                ctx.beginPath();
                ctx.moveTo(prev.x, prev.y);
                ctx.lineTo(a.x, a.y);
                ctx.stroke();
            }
        }

        if (p.hasHalo) {
            const haloR = p.size * (p.heroActive ? 9 : 6);
            const g2 = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, haloR);
            g2.addColorStop(0, `rgba(${r},${g},${b},${(alpha * 0.16).toFixed(3)})`);
            g2.addColorStop(1, `rgba(${r},${g},${b},0)`);
            ctx.fillStyle = g2;
            ctx.beginPath();
            ctx.arc(p.x, p.y, haloR, 0, Math.PI * 2);
            ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * (p.heroActive ? 1.3 : 1), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
        ctx.shadowColor = `rgba(${r},${g},${b},${Math.min(1, alpha * 1.4).toFixed(3)})`;
        ctx.shadowBlur = p.glow * (p.heroActive ? 1.6 : 1);
        ctx.fill();
        ctx.shadowBlur = 0;
    }

    function updateLinks(dt) {
        const fg = particles.filter((p) => p.layer === "fg");
        for (let i = 0; i < fg.length; i++) {
            for (let j = i + 1; j < fg.length; j++) {
                const dx = fg[i].x - fg[j].x, dy = fg[i].y - fg[j].y;
                const dist = Math.hypot(dx, dy);
                if (dist < LINK_DIST && Math.random() < 0.01) {
                    const already = links.some((l) => (l.a === fg[i] && l.b === fg[j]) || (l.a === fg[j] && l.b === fg[i]));
                    if (!already) links.push({ a: fg[i], b: fg[j], life: 0.5, maxLife: 0.5 });
                }
            }
        }
        for (let i = links.length - 1; i >= 0; i--) {
            links[i].life -= dt;
            const dist = Math.hypot(links[i].a.x - links[i].b.x, links[i].a.y - links[i].b.y);
            if (links[i].life <= 0 || dist > LINK_DIST * 1.6) links.splice(i, 1);
        }
    }

    function drawLinks() {
        links.forEach((l) => {
            const t = Math.max(0, l.life / l.maxLife);
            ctx.strokeStyle = `rgba(232,199,162,${(t * 0.1).toFixed(3)})`;
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            ctx.moveTo(l.a.x, l.a.y);
            ctx.lineTo(l.b.x, l.b.y);
            ctx.stroke();
        });
    }

    function drawAmbientGlow(t) {
        const fields = [
            { x: W * 0.12, y: H * 0.85, r: Math.max(W, H) * 0.5, c: "227,6,19", a: 0.05 },
            { x: W * 0.9, y: H * 0.1, r: Math.max(W, H) * 0.45, c: "232,199,162", a: 0.05 },
        ];
        fields.forEach((f, i) => {
            const dx = Math.sin(t * 0.015 + i) * W * 0.015;
            const dy = Math.cos(t * 0.012 + i) * H * 0.015;
            const g = ctx.createRadialGradient(f.x + dx, f.y + dy, 0, f.x + dx, f.y + dy, f.r);
            g.addColorStop(0, `rgba(${f.c},${f.a})`);
            g.addColorStop(1, `rgba(${f.c},0)`);
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, W, H);
        });
    }

    let activeTrailCount = 0;
    let lastTime = 0, running = true;

    function frame(now) {
        if (!running) return;
        if (!W || !H) { requestAnimationFrame(frame); return; }
        const t = now / 1000;
        const dt = Math.min(0.05, (now - lastTime) / 1000 || 0);
        lastTime = now;

        ctx.clearRect(0, 0, W, H);
        drawAmbientGlow(t);

        if (!reduceMotion) {
            particles.forEach((p) => updateParticle(p, t, dt));
            updateLinks(dt);
        }

        ["bg", "mid", "fg"].forEach((layer) => {
            const spec = LAYER_SPECS[layer];
            ctx.filter = spec.blurPx ? `blur(${spec.blurPx}px)` : "none";
            particles.filter((p) => p.layer === layer).forEach((p) => drawParticle(p, reduceMotion ? 0 : t));
        });
        ctx.filter = "none";

        if (!reduceMotion) {
            drawLinks();
            requestAnimationFrame(frame);
        }
    }

    window.addEventListener("resize", () => { resize(); }, { passive: true });
    window.addEventListener("pointermove", (e) => {
        mouse.x = e.clientX; mouse.y = e.clientY;
        mouse.active = true;
    }, { passive: true });
    window.addEventListener("pointerleave", () => { mouse.active = false; }, { passive: true });

    document.addEventListener("visibilitychange", () => {
        running = !document.hidden;
        if (running && !reduceMotion) { lastTime = performance.now(); requestAnimationFrame(frame); }
    });

    resize();
    requestAnimationFrame(frame);
})();
