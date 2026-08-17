/* Warm ambient background engine — Canvas2D (no WebGL/Three.js dependency
   needed for this decorative layer; renders identically across GPUs).
   Four layers, back to front:
     1. Slow warm light fields   — three huge, near-static radial gradients
        that drift almost imperceptibly (breathing light, not motion)
     2. Morphing ambient blobs   — 5 soft warm-toned shapes that breathe
        (radius pulses) and drift independently, never a hard edge
     3. Noise-driven dust field  — particles following a value-noise flow
        field, colour-cycling through red/tangerine/gold/coral
     4. Cursor constellation     — a smaller set of nodes that link with
        faint lines, repelled by fast cursor movement and gently orbiting
        it once the cursor has been idle for ~650ms
   A CSS-level grain overlay (see .grain in style.css) sits above all of it. */
(function () {
    "use strict";

    const canvas = document.getElementById("bg-canvas");
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // --- Compact value-noise (deterministic hash + bilinear smoothstep) ---
    function hash(x, y) {
        const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453123;
        return s - Math.floor(s);
    }
    function fade(t) { return t * t * (3 - 2 * t); }

    // --- Cubic-bezier evaluator, used to shape the repel force's falloff
    // curve (cubic-bezier(0.16, 1, 0.3, 1) — a quick, no-overshoot decay). ---
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
    function repelFalloff(proximity) { return cubicBezierY(proximity, 0.16, 1, 0.3, 1); }
    function noise2D(x, y) {
        const xi = Math.floor(x), yi = Math.floor(y);
        const xf = x - xi, yf = y - yi;
        const u = fade(xf), v = fade(yf);
        const a = hash(xi, yi), b = hash(xi + 1, yi);
        const c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
        return (a + (b - a) * u) * (1 - v) + (c + (d - c) * u) * v;
    }

    const WARM_BLOB_COLORS = [
        [47, 37, 82],    // MDX indigo
        [47, 37, 82],    // MDX indigo (double weight -- indigo-led palette)
        [227, 6, 19],    // MDX red
        [229, 0, 89],    // MDX pink
        [244, 125, 7],   // MDX tangerine
    ];
    const DUST_COLORS = [
        [47, 37, 82],    // MDX indigo
        [227, 6, 19],    // MDX red
        [244, 125, 7],   // MDX tangerine
        [229, 0, 89],    // MDX pink
    ];

    // --- Performance tiers ---
    // Text now sits on glass panels (heavy blur shields it from whatever's
    // behind), so the field can read as a genuine live feature again
    // without the earlier legibility fight — just not back to the extreme.
    function tierCounts() {
        const w = window.innerWidth;
        if (w < 640) return { dust: 80, nodes: 20 };
        if (w < 1100) return { dust: 150, nodes: 38 };
        return { dust: 220, nodes: 55 };
    }

    let W = 0, H = 0, DPR = 1;
    let blobs = [], dust = [], nodes = [];
    const mouse = { x: -9999, y: -9999, active: false, lastX: 0, lastY: 0, speed: 0, idleSince: 0 };
    const pulses = [];

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

    function seed() {
        blobs = WARM_BLOB_COLORS.map((color, i) => ({
            color,
            baseX: (0.1 + 0.22 * (i % 3)) * W + i * 40,
            baseY: (0.08 + 0.3 * Math.floor(i / 3)) * H + i * 30,
            baseR: Math.max(W, H) * (0.22 + 0.04 * i),
            phase: i * 2.1,
            driftSpeed: 0.02 + i * 0.006,
            breatheSpeed: 0.15 + i * 0.03,
            alpha: i < 2 ? 0.38 : 0.24,
        }));

        const counts = reduceMotion ? { dust: 0, nodes: 0 } : tierCounts();

        dust = Array.from({ length: counts.dust }, () => ({
            x: Math.random() * W,
            y: Math.random() * H,
            speed: 0.28 + Math.random() * 0.5,
            size: 1.6 + Math.random() * 2.2,
            colorPhase: Math.random() * Math.PI * 2,
            colorSpeed: 0.1 + Math.random() * 0.15,
            alphaPhase: Math.random() * Math.PI * 2,
        }));

        nodes = Array.from({ length: counts.nodes }, () => ({
            x: Math.random() * W,
            y: Math.random() * H,
            vx: (Math.random() - 0.5) * 0.2,
            vy: (Math.random() - 0.5) * 0.2,
        }));
    }

    function lerpColor(a, b, t) {
        return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
    }

    function drawLightFields(t) {
        const fields = [
            { x: W * 0.08, y: H * 0.05, r: Math.max(W, H) * 0.55, c: "47,37,82", a: 0.16 },
            { x: W * 0.95, y: H * 0.15, r: Math.max(W, H) * 0.5, c: "227,6,19", a: 0.06 },
            { x: W * 0.5, y: H * 1.0, r: Math.max(W, H) * 0.6, c: "47,37,82", a: 0.14 },
        ];
        fields.forEach((f, i) => {
            const dx = Math.sin(t * 0.02 + i) * W * 0.02;
            const dy = Math.cos(t * 0.015 + i) * H * 0.02;
            const g = ctx.createRadialGradient(f.x + dx, f.y + dy, 0, f.x + dx, f.y + dy, f.r);
            g.addColorStop(0, `rgba(${f.c},${f.a})`);
            g.addColorStop(1, `rgba(${f.c},0)`);
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, W, H);
        });
    }

    function drawBlobs(t) {
        blobs.forEach((b) => {
            const dx = Math.cos(t * b.driftSpeed + b.phase) * W * 0.05;
            const dy = Math.sin(t * b.driftSpeed * 0.8 + b.phase) * H * 0.05;
            const breathe = 1 + Math.sin(t * b.breatheSpeed + b.phase) * 0.12;
            const x = b.baseX + dx, y = b.baseY + dy, r = b.baseR * breathe;
            const g = ctx.createRadialGradient(x, y, 0, x, y, r);
            g.addColorStop(0, `rgba(${b.color[0]},${b.color[1]},${b.color[2]},${b.alpha})`);
            g.addColorStop(0.6, `rgba(${b.color[0]},${b.color[1]},${b.color[2]},${b.alpha * 0.35})`);
            g.addColorStop(1, `rgba(${b.color[0]},${b.color[1]},${b.color[2]},0)`);
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, W, H);
        });
    }

    const NOISE_SCALE = 0.0016;

    function updateAndDrawDust(t, dt) {
        dust.forEach((p) => {
            const angle = noise2D(p.x * NOISE_SCALE, p.y * NOISE_SCALE + t * 0.05) * Math.PI * 4;
            p.x += Math.cos(angle) * p.speed * dt * 60;
            p.y += Math.sin(angle) * p.speed * dt * 60;

            if (p.x < -10) p.x = W + 10; if (p.x > W + 10) p.x = -10;
            if (p.y < -10) p.y = H + 10; if (p.y > H + 10) p.y = -10;

            const colorT = (Math.sin(t * p.colorSpeed + p.colorPhase) + 1) / 2;
            const idx = colorT * (DUST_COLORS.length - 1);
            const i0 = Math.floor(idx), i1 = Math.min(i0 + 1, DUST_COLORS.length - 1);
            const [r, g, bC] = lerpColor(DUST_COLORS[i0], DUST_COLORS[i1], idx - i0);
            const alpha = 0.32 + 0.34 * ((Math.sin(t * 0.4 + p.alphaPhase) + 1) / 2);

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${r | 0},${g | 0},${bC | 0},${alpha.toFixed(2)})`;
            ctx.fill();
        });
    }

    const LINK_DIST = 130;
    const MOUSE_REPEL_RADIUS = 180;
    const IDLE_ORBIT_RADIUS = 170;
    const IDLE_THRESHOLD_MS = 650;

    function updateNodes(dt) {
        const idleFor = mouse.active ? performance.now() - mouse.idleSince : Infinity;
        const orbiting = mouse.active && idleFor > IDLE_THRESHOLD_MS;
        const fastMove = mouse.speed > 1.4;

        nodes.forEach((p) => {
            if (mouse.active) {
                const dx = p.x - mouse.x, dy = p.y - mouse.y;
                const dist = Math.hypot(dx, dy) || 1;

                if (fastMove && dist < MOUSE_REPEL_RADIUS) {
                    const force = repelFalloff(1 - dist / MOUSE_REPEL_RADIUS) * 0.8;
                    p.vx += (dx / dist) * force * dt;
                    p.vy += (dy / dist) * force * dt;
                } else if (orbiting && dist < IDLE_ORBIT_RADIUS) {
                    // Gentle tangential pull + weak centring, reads as a loose orbit
                    const tx = -dy / dist, ty = dx / dist;
                    const pull = (1 - dist / IDLE_ORBIT_RADIUS) * 0.14;
                    p.vx += tx * pull * dt * 12 - (dx / dist) * pull * dt * 3;
                    p.vy += ty * pull * dt * 12 - (dy / dist) * pull * dt * 3;
                }
            }

            for (let i = pulses.length - 1; i >= 0; i--) {
                const pulse = pulses[i];
                const dx = p.x - pulse.x, dy = p.y - pulse.y;
                const dist = Math.hypot(dx, dy) || 1;
                if (dist < pulse.radius) {
                    const force = (1 - dist / pulse.radius) * pulse.strength;
                    p.vx += (dx / dist) * force;
                    p.vy += (dy / dist) * force;
                }
            }

            p.vx *= 0.95;
            p.vy *= 0.95;
            p.x += p.vx * dt * 60;
            p.y += p.vy * dt * 60;

            if (p.x < -20) p.x = W + 20; if (p.x > W + 20) p.x = -20;
            if (p.y < -20) p.y = H + 20; if (p.y > H + 20) p.y = -20;
        });

        for (let i = pulses.length - 1; i >= 0; i--) {
            pulses[i].radius += 380 * dt;
            pulses[i].strength *= 0.9;
            if (pulses[i].strength < 0.02) pulses.splice(i, 1);
        }
    }

    function drawNodes() {
        ctx.lineWidth = 1;
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
                const dist = Math.hypot(dx, dy);
                if (dist < LINK_DIST) {
                    const t = 1 - dist / LINK_DIST;
                    ctx.strokeStyle = `rgba(227,6,19,${(t * 0.3).toFixed(2)})`;
                    ctx.beginPath();
                    ctx.moveTo(nodes[i].x, nodes[i].y);
                    ctx.lineTo(nodes[j].x, nodes[j].y);
                    ctx.stroke();
                }
            }
        }

        nodes.forEach((p) => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(227,6,19,0.6)";
            ctx.shadowColor = "rgba(255,107,0,0.6)";
            ctx.shadowBlur = 4;
            ctx.fill();
            ctx.shadowBlur = 0;
        });
    }

    let lastTime = 0, running = true;

    function frame(now) {
        if (!running) return;
        if (!W || !H) { requestAnimationFrame(frame); return; }
        const t = now / 1000;
        const dt = Math.min(0.05, (now - lastTime) / 1000 || 0);
        lastTime = now;

        ctx.clearRect(0, 0, W, H);
        drawLightFields(reduceMotion ? 0 : t);
        drawBlobs(reduceMotion ? 0 : t);
        if (!reduceMotion) {
            updateAndDrawDust(t, dt);
            updateNodes(dt);
            drawNodes();
        }

        if (!reduceMotion) requestAnimationFrame(frame);
    }

    window.addEventListener("resize", () => { resize(); }, { passive: true });
    window.addEventListener("pointermove", (e) => {
        const dx = e.clientX - mouse.lastX, dy = e.clientY - mouse.lastY;
        mouse.speed = Math.hypot(dx, dy);
        mouse.lastX = e.clientX; mouse.lastY = e.clientY;
        mouse.x = e.clientX; mouse.y = e.clientY;
        mouse.active = true;
        mouse.idleSince = performance.now();
    }, { passive: true });
    window.addEventListener("pointerleave", () => { mouse.active = false; }, { passive: true });
    window.addEventListener("pointerdown", (e) => {
        pulses.push({ x: e.clientX, y: e.clientY, radius: 10, strength: 3.5 });
    }, { passive: true });

    document.addEventListener("visibilitychange", () => {
        running = !document.hidden;
        if (running && !reduceMotion) { lastTime = performance.now(); requestAnimationFrame(frame); }
    });

    resize();
    requestAnimationFrame(frame);
})();
