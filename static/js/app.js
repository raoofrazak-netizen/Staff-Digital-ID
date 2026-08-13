(function () {
    "use strict";

    const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
    const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
    const REDUCE_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // --- Tab switching ---
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabPanels = {
        register: document.getElementById("tab-register"),
        activate: document.getElementById("tab-activate"),
    };

    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.classList.contains("active")) return;
            const currentPanel = document.querySelector(".tab-panel.active");
            const nextPanel = tabPanels[btn.dataset.tab];
            if (!nextPanel || currentPanel === nextPanel) return;

            tabButtons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            const swapIn = () => {
                if (currentPanel) currentPanel.classList.remove("active", "leaving");
                nextPanel.classList.add("active");
                nextPanel.classList.remove("entering");
                void nextPanel.offsetWidth; // restart the slide-in animation
                nextPanel.classList.add("entering");
                syncCardFromActiveForm();
            };

            if (REDUCE_MOTION || !currentPanel) {
                swapIn();
                return;
            }
            currentPanel.classList.add("leaving");
            window.setTimeout(swapIn, 150);
        });
    });

    function spawnPhotoBurst(container) {
        if (!container || REDUCE_MOTION) return;
        container.innerHTML = "";
        const count = 10;
        for (let i = 0; i < count; i++) {
            const span = document.createElement("span");
            const angle = (Math.PI * 2 * i) / count + Math.random() * 0.4;
            const dist = 30 + Math.random() * 22;
            span.style.setProperty("--bx", Math.cos(angle) * dist + "px");
            span.style.setProperty("--by", Math.sin(angle) * dist + "px");
            span.style.background = i % 2 === 0 ? "var(--mdx-tangerine)" : "var(--mdx-red)";
            container.appendChild(span);
        }
        window.setTimeout(() => { container.innerHTML = ""; }, 650);
    }

    // Fired on dragenter — particles emanate from the drop-zone's ring
    // perimeter outward, distinct from the center-outward burst on a
    // successful drop.
    function spawnPerimeterBurst(container) {
        if (!container || REDUCE_MOTION) return;
        container.innerHTML = "";
        const count = 8;
        const ringRadius = 50;
        for (let i = 0; i < count; i++) {
            const span = document.createElement("span");
            const angle = (Math.PI * 2 * i) / count + Math.random() * 0.3;
            const outDist = 12 + Math.random() * 10;
            span.style.setProperty("--start-x", Math.cos(angle) * ringRadius + "px");
            span.style.setProperty("--start-y", Math.sin(angle) * ringRadius + "px");
            span.style.setProperty("--bx", Math.cos(angle) * (ringRadius + outDist) + "px");
            span.style.setProperty("--by", Math.sin(angle) * (ringRadius + outDist) + "px");
            span.style.background = "var(--mdx-red)";
            container.appendChild(span);
        }
        window.setTimeout(() => { container.innerHTML = ""; }, 500);
    }

    // --- Live card elements ---
    const idcard = document.getElementById("idcard");
    const liveName = document.getElementById("live-name");
    const liveTitle = document.getElementById("live-title");
    const liveDept = document.getElementById("live-dept");
    const liveStaffId = document.getElementById("live-staff-id");
    const liveStatus = document.getElementById("live-status");
    const liveGender = document.getElementById("live-gender");
    const livePhoto = document.getElementById("live-photo");
    const livePhotoBox = document.getElementById("live-photo-box");

    function fieldValue(name) {
        const panel = document.querySelector(".tab-panel.active");
        if (!panel) return "";
        const el = panel.querySelector(`[data-live="${name}"]`);
        if (!el || !el.value) return "";
        if (el.tagName === "SELECT") {
            return el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : "";
        }
        return el.value;
    }

    function bumpCard() {
        idcard.classList.remove("updated");
        // force reflow so the animation can restart on the next keystroke
        void idcard.offsetWidth;
        idcard.classList.add("updated");
    }

    function setTextIfChanged(el, value) {
        if (el.textContent === value) return;
        el.textContent = value;
        if (REDUCE_MOTION) return;
        el.classList.remove("text-pop");
        void el.offsetWidth;
        el.classList.add("text-pop");
    }

    function syncCard(firstName, lastName, staffId, gender, department, jobTitle, employmentStatus) {
        const fullName = (firstName + " " + lastName).trim();
        setTextIfChanged(liveName, fullName || "Your Name");
        setTextIfChanged(liveTitle, jobTitle || "Job title");
        setTextIfChanged(liveDept, department || "Department");
        setTextIfChanged(liveStaffId, staffId ? "Staff ID " + staffId : "Staff ID —");
        setTextIfChanged(liveStatus, employmentStatus || "Employment Status");
        setTextIfChanged(liveGender, gender || "—");
        bumpCard();
        updateLivePreviewQR(firstName, lastName, staffId);
        updateStepper();
    }

    // --- Intelligent form-progress stepper ---
    const stepDetails = document.getElementById("step-details");
    const stepPhoto = document.getElementById("step-photo");
    const stepPreview = document.getElementById("step-preview");
    const stepWallet = document.getElementById("step-wallet");

    function setStepState(el, state) {
        if (!el) return;
        el.classList.remove("is-current", "is-done");
        if (state === "done") el.classList.add("is-done");
        else if (state === "current") el.classList.add("is-current");

        const numEl = el.querySelector(".stepper__num");
        if (numEl) {
            const wantsCheck = state === "done";
            const isCheck = numEl.textContent.trim() === "✓";
            if (wantsCheck !== isCheck) {
                numEl.textContent = wantsCheck ? "✓" : numEl.dataset.num;
            }
        }
    }

    function updateStepper() {
        if (!stepDetails) return;
        const activePanel = document.querySelector(".tab-panel.active");
        if (!activePanel) return;

        let detailsDone, photoDone;
        if (activePanel.id === "tab-register") {
            detailsDone = ["r-first-name", "r-last-name", "r-staff-id", "r-email", "r-department", "r-job-title", "r-employment-status", "r-gender"]
                .every((id) => ((document.getElementById(id) || {}).value || "").trim());
            photoDone = document.getElementById("r-photo-drop").classList.contains("has-photo");
        } else {
            detailsDone = !!((document.getElementById("act-staff-id") || {}).value || "").trim();
            photoDone = document.getElementById("a-photo-drop").classList.contains("has-photo");
        }

        setStepState(stepDetails, detailsDone ? "done" : "current");
        setStepState(stepPhoto, !detailsDone ? "pending" : (photoDone ? "done" : "current"));
        setStepState(stepPreview, (detailsDone && photoDone) ? "current" : "pending");
        setStepState(stepWallet, "pending");
    }

    // --- University-email domain hint (amber warning, not a hard error) ---
    const rEmail = document.getElementById("r-email");
    const rEmailHint = document.getElementById("r-email-hint");
    if (rEmail && rEmailHint) {
        rEmail.addEventListener("input", () => {
            const v = rEmail.value.trim().toLowerCase();
            const looksOff = v.includes("@") && !v.endsWith("@mdx.ac.ae");
            rEmailHint.classList.toggle("show", looksOff);
            rEmail.classList.toggle("is-warning", looksOff);
        });
    }

    // --- Reusable subtle tilt + cursor-follow highlight, for glass panels ---
    function attachTilt(el, maxDeg) {
        if (!el || REDUCE_MOTION) return;
        el.addEventListener("pointermove", (e) => {
            const r = el.getBoundingClientRect();
            const px = (e.clientX - r.left) / r.width;
            const py = (e.clientY - r.top) / r.height;
            el.style.transform = `perspective(1000px) rotateX(${(0.5 - py) * maxDeg * 2}deg) rotateY(${(px - 0.5) * maxDeg * 2}deg)`;
            el.style.setProperty("--gx", (px * 100) + "%");
            el.style.setProperty("--gy", (py * 100) + "%");
        });
        el.addEventListener("pointerleave", () => {
            el.style.transform = "perspective(1000px) rotateX(0deg) rotateY(0deg)";
        });
    }
    document.querySelectorAll("[data-tilt]").forEach((el) => attachTilt(el, 2));

    // --- ID card tilt + cursor-follow sheen (subtle — max ~3deg) ---
    const tiltWrap = document.getElementById("idcard-tilt-wrap");
    const idcardSheen = document.getElementById("idcard-sheen");
    if (tiltWrap && !REDUCE_MOTION) {
        tiltWrap.addEventListener("pointermove", (e) => {
            const r = tiltWrap.getBoundingClientRect();
            const px = (e.clientX - r.left) / r.width;
            const py = (e.clientY - r.top) / r.height;
            const rotY = (px - 0.5) * 6;
            const rotX = (0.5 - py) * 6;
            idcard.style.transform = `perspective(1000px) rotateX(${rotX}deg) rotateY(${rotY}deg)`;
            idcardSheen.style.setProperty("--gx", (px * 100) + "%");
            idcardSheen.style.setProperty("--gy", (py * 100) + "%");
        });
        tiltWrap.addEventListener("pointerleave", () => {
            idcard.style.transform = "perspective(1000px) rotateX(0deg) rotateY(0deg)";
        });
    }

    // --- Live QR preview: appears once the key identity fields are filled.
    // This is a clearly-marked, client-side-only PREVIEW — the real,
    // secure verification QR is still generated server-side after
    // submission (it encodes an unguessable token, never raw staff data). ---
    const qrPanel = document.getElementById("qr-panel");
    const qrPlaceholder = document.getElementById("qr-placeholder");
    const qrLiveImg = document.getElementById("qr-live-img");
    let qrDebounceTimer = null;

    function showQrPlaceholder() {
        if (!qrPanel) return;
        qrPanel.classList.remove("is-preview");
        qrPlaceholder.style.display = "flex";
        qrLiveImg.style.display = "none";
    }

    function renderLiveQR(firstName, lastName, staffId) {
        if (!qrPanel || typeof qrcode === "undefined") return;
        // URL-shaped payload matching the real /verify/<token> route, so a
        // curious scan lands on our own graceful "Invalid ID" page rather
        // than a bare 404 — but the token can never resolve to a real
        // record, since the real one only exists after server submission.
        const previewToken = "PREVIEW-" + staffId.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
        const text = window.location.origin + "/verify/" + encodeURIComponent(previewToken);
        try {
            const qr = qrcode(0, "M");
            qr.addData(text);
            qr.make();
            qrLiveImg.src = qr.createDataURL(6, 4);
            qrPanel.classList.add("is-preview");
            qrPlaceholder.style.display = "none";
            qrLiveImg.style.display = "block";
            qrPanel.classList.remove("pulse");
            void qrPanel.offsetWidth;
            qrPanel.classList.add("pulse");
        } catch (err) {
            showQrPlaceholder();
        }
    }

    function updateLivePreviewQR(firstName, lastName, staffId) {
        if (!qrPanel) return;
        const ready = firstName.trim() && lastName.trim() && staffId.trim();
        window.clearTimeout(qrDebounceTimer);
        if (!ready) {
            showQrPlaceholder();
            return;
        }
        qrDebounceTimer = window.setTimeout(() => renderLiveQR(firstName, lastName, staffId), 120);
    }

    function syncCardFromActiveForm() {
        syncCard(
            fieldValue("first_name"), fieldValue("last_name"), fieldValue("staff_id"),
            fieldValue("gender"), fieldValue("department"), fieldValue("job_title"),
            fieldValue("employment_status")
        );
    }

    document.querySelectorAll("[data-live]").forEach((el) => {
        el.addEventListener("input", syncCardFromActiveForm);
        el.addEventListener("change", syncCardFromActiveForm);
    });

    syncCardFromActiveForm();

    // --- Photo field: drag & drop / click-to-browse / preview / zoom+pan / remove ---
    function setupPhotoField(prefix, onPreview) {
        const drop = document.getElementById(prefix + "-photo-drop");
        const input = document.getElementById(prefix + "-photo");
        const preview = document.getElementById(prefix + "-photo-preview");
        const frame = document.getElementById(prefix + "-photo-frame");
        const changeBtn = document.getElementById(prefix + "-photo-change");
        const removeBtn = document.getElementById(prefix + "-photo-remove");
        const errorEl = document.getElementById(prefix + "-photo-error");
        const zoomRow = document.getElementById(prefix + "-photo-zoom");
        const zoomRange = document.getElementById(prefix + "-photo-zoom-range");
        const zoomHint = document.getElementById(prefix + "-photo-zoom-hint");
        const burst = document.getElementById(prefix + "-photo-burst");
        if (!drop || !input) return;

        let panX = 0, panY = 0, zoom = 1;

        function applyTransform() {
            preview.style.setProperty("--zoom", zoom);
            preview.style.setProperty("--pan-x", panX + "px");
            preview.style.setProperty("--pan-y", panY + "px");
        }

        function clampPan() {
            const max = (zoom - 1) * 45;
            panX = Math.max(-max, Math.min(max, panX));
            panY = Math.max(-max, Math.min(max, panY));
        }

        function resetTransform() {
            zoom = 1; panX = 0; panY = 0;
            zoomRange.value = 1;
            applyTransform();
        }

        function showError(msg) {
            errorEl.textContent = msg;
            errorEl.classList.add("show");
        }
        function clearError() {
            errorEl.textContent = "";
            errorEl.classList.remove("show");
        }

        function validate(file) {
            if (!ALLOWED_TYPES.includes(file.type)) {
                showError("Unsupported format — please use JPEG, PNG, or WebP.");
                return false;
            }
            if (file.size > MAX_PHOTO_BYTES) {
                showError("File is too large — max 5MB.");
                return false;
            }
            return true;
        }

        function loadFile(file) {
            if (!validate(file)) return;
            clearError();
            drop.classList.remove("is-loading");
            void drop.offsetWidth; // allow the progress-ring animation to restart
            drop.classList.add("is-loading");
            const reader = new FileReader();
            reader.onload = (e) => {
                window.setTimeout(() => {
                    drop.classList.remove("is-loading");
                    drop.classList.add("has-photo");
                    resetTransform();
                    preview.src = e.target.result;
                    removeBtn.disabled = false;
                    zoomRow.classList.add("show");
                    zoomHint.style.display = "block";
                    spawnPhotoBurst(burst);
                    if (onPreview) onPreview(e.target.result);
                    updateStepper();
                }, 350); // brief, deliberate pause so the progress ring reads as real feedback
            };
            reader.onerror = () => {
                drop.classList.remove("is-loading");
                showError("Couldn't read that file — it may be corrupted.");
            };
            reader.readAsDataURL(file);
        }

        input.addEventListener("change", () => {
            const file = input.files && input.files[0];
            if (file) loadFile(file);
        });

        changeBtn.addEventListener("click", () => input.click());

        removeBtn.addEventListener("click", () => {
            input.value = "";
            drop.classList.remove("has-photo");
            preview.src = "";
            removeBtn.disabled = true;
            zoomRow.classList.remove("show");
            zoomHint.style.display = "none";
            clearError();
            resetTransform();
            if (onPreview) onPreview(null);
            updateStepper();
        });

        zoomRange.addEventListener("input", () => {
            zoom = parseFloat(zoomRange.value);
            clampPan();
            applyTransform();
        });

        // Drag-to-reposition within the circular frame
        let dragging = false, startX = 0, startY = 0, startPanX = 0, startPanY = 0;
        frame.addEventListener("pointerdown", (e) => {
            if (!drop.classList.contains("has-photo")) return;
            dragging = true;
            startX = e.clientX; startY = e.clientY;
            startPanX = panX; startPanY = panY;
            frame.setPointerCapture(e.pointerId);
        });
        frame.addEventListener("pointermove", (e) => {
            if (!dragging) return;
            panX = startPanX + (e.clientX - startX);
            panY = startPanY + (e.clientY - startY);
            clampPan();
            applyTransform();
        });
        frame.addEventListener("pointerup", () => { dragging = false; });
        frame.addEventListener("pointercancel", () => { dragging = false; });

        let dragBurstFired = false;
        drop.addEventListener("dragenter", () => {
            if (!dragBurstFired) { spawnPerimeterBurst(burst); dragBurstFired = true; }
        });
        drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag-over"); });
        drop.addEventListener("dragleave", () => { drop.classList.remove("drag-over"); dragBurstFired = false; });
        drop.addEventListener("drop", (e) => {
            e.preventDefault();
            drop.classList.remove("drag-over");
            const file = e.dataTransfer.files && e.dataTransfer.files[0];
            if (file) {
                input.files = e.dataTransfer.files;
                loadFile(file);
            }
        });
        drop.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
        });
    }

    setupPhotoField("r", (dataUrl) => {
        if (dataUrl) {
            livePhoto.src = dataUrl;
            livePhotoBox.classList.add("has-photo");
        } else {
            livePhotoBox.classList.remove("has-photo");
        }
        bumpCard();
    });
    setupPhotoField("a", (dataUrl) => {
        if (dataUrl) {
            livePhoto.src = dataUrl;
            livePhotoBox.classList.add("has-photo");
        } else {
            livePhotoBox.classList.remove("has-photo");
        }
        bumpCard();
    });

    // --- Track ID lookup: retrieves an already-created Digital ID (with its
    // saved photo) by short Track ID, or falls back to a Staff ID match
    // against the HR directory for staff who haven't created one yet. ---
    const lookupBtn = document.getElementById("lookup-btn");
    if (lookupBtn) {
        const badge = document.getElementById("track-badge");
        const badgeIcon = document.getElementById("track-badge-icon");
        const badgeText = document.getElementById("track-badge-text");
        const viewBtn = document.getElementById("track-view-btn");

        function setBadge(state, message) {
            badge.className = "track-badge show " + state;
            badgeIcon.textContent = state === "success" ? "✓" : (state === "error" ? "✕" : "…");
            badgeText.textContent = message;
        }

        lookupBtn.addEventListener("click", async () => {
            const query = document.getElementById("a-track-id").value.trim();
            const actForm = document.getElementById("act-form");

            actForm.style.display = "none";
            viewBtn.style.display = "none";

            if (!query) {
                setBadge("error", "Enter your Track ID or Staff ID.");
                return;
            }
            setBadge("searching", "Searching…");

            try {
                const res = await fetch("/api/track", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query: query }),
                });
                const data = await res.json();

                if (!data.found) {
                    setBadge("error", "No match found. Check your Track ID or Staff ID, or use New Staff Registration.");
                    return;
                }

                const r = data.record;

                if (data.type === "digital_id") {
                    setBadge("success", "Digital ID found for " + r["First Name"] + " " + r["Last Name"] + ".");
                    syncCard(r["First Name"], r["Last Name"], r["Staff ID"], r["Gender"], r["Department"], r["Job Title"], r["Employment Status"]);
                    if (data.photo_url) {
                        livePhoto.src = data.photo_url;
                        livePhotoBox.classList.add("has-photo");
                    }
                    setStepState(stepDetails, "done");
                    setStepState(stepPhoto, "done");
                    setStepState(stepPreview, "done");
                    viewBtn.href = data.success_url;
                    viewBtn.style.display = "inline-flex";
                    return;
                }

                // type === "directory": known to HR but no Digital ID yet — let them complete one.
                setBadge("success", "Staff record found — upload a photo below to finish creating your Digital ID.");

                document.getElementById("act-first-name").value = r["First Name"];
                document.getElementById("act-last-name").value = r["Last Name"];
                document.getElementById("act-staff-id").value = r["Staff ID"];
                document.getElementById("act-email").value = r["Email"];
                document.getElementById("act-department").value = r["Department"];
                document.getElementById("act-job-title").value = r["Job Title"];
                document.getElementById("act-gender").value = r["Gender"];
                document.getElementById("act-employment-status").value = r["Employment Status"];

                syncCard(r["First Name"], r["Last Name"], r["Staff ID"], r["Gender"], r["Department"], r["Job Title"], r["Employment Status"]);

                actForm.style.display = "block";
            } catch (err) {
                setBadge("error", "Something went wrong looking up your record. Please try again.");
            }
        });
    }
})();
