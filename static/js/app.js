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

    const requestedTab = new URLSearchParams(window.location.search).get("tab");
    if (requestedTab && tabPanels[requestedTab]) {
        const requestedBtn = document.querySelector(`.tab-btn[data-tab="${requestedTab}"]`);
        if (requestedBtn && !requestedBtn.classList.contains("active")) requestedBtn.click();
    }

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
    const liveMobile = document.getElementById("live-mobile");
    const livePhoto = document.getElementById("live-photo");
    const livePhotoBox = document.getElementById("live-photo-box");
    const liveEmail = document.getElementById("live-email");
    const liveMobileBack = document.getElementById("live-mobile-back");
    const liveDeptBack = document.getElementById("live-dept-back");
    const liveStatusBack = document.getElementById("live-status-back");
    const liveGenderBack = document.getElementById("live-gender-back");

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

    function syncCard(firstName, lastName, staffId, gender, department, jobTitle, employmentStatus, email, mobile) {
        const fullName = (firstName + " " + lastName).trim();
        setTextIfChanged(liveName, fullName || "Your Name");
        setTextIfChanged(liveTitle, jobTitle || "Job title");
        setTextIfChanged(liveDept, department || "Department");
        setTextIfChanged(liveStaffId, staffId ? "Staff ID " + staffId : "Staff ID —");
        setTextIfChanged(liveStatus, employmentStatus || "Employment Status");
        setTextIfChanged(liveGender, gender || "—");
        if (liveMobile) {
            liveMobile.style.display = mobile ? "" : "none";
            if (mobile) setTextIfChanged(liveMobile, mobile);
        }
        if (liveEmail) setTextIfChanged(liveEmail, email || "—");
        if (liveMobileBack) setTextIfChanged(liveMobileBack, mobile || "—");
        if (liveDeptBack) setTextIfChanged(liveDeptBack, department || "—");
        if (liveStatusBack) setTextIfChanged(liveStatusBack, employmentStatus || "—");
        if (liveGenderBack) setTextIfChanged(liveGenderBack, gender || "—");
        bumpCard();
        updateLivePreviewQR(firstName, lastName, staffId, jobTitle, department, email || "", mobile || "");
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

    // --- Live QR preview: a real, scannable vCard for the staff member's
    // contact details, appearing once name + Staff ID are filled. It's
    // marked "Preview" only because the Digital ID record itself hasn't
    // been created server-side yet — the vCard content is fully valid. ---
    const qrPanel = document.getElementById("qr-panel");
    const qrPlaceholder = document.getElementById("qr-placeholder");
    const qrLiveImg = document.getElementById("qr-live-img");
    let qrDebounceTimer = null;

    function buildVCard(firstName, lastName, jobTitle, department, email, mobile) {
        const lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            `FN:${(firstName + " " + lastName).trim()}`,
            "ORG:Middlesex University Dubai",
        ];
        if (jobTitle) lines.push(`TITLE:${jobTitle}`);
        if (email) lines.push(`EMAIL;TYPE=WORK:${email}`);
        if (mobile) lines.push(`TEL;TYPE=CELL:${mobile}`);
        lines.push("URL:https://www.mdx.ac.ae");
        if (department) lines.push(`NOTE:Department - ${department}`);
        lines.push("END:VCARD");
        return lines.join("\r\n");
    }

    function showQrPlaceholder() {
        if (!qrPanel) return;
        qrPanel.classList.remove("is-preview");
        qrPlaceholder.style.display = "flex";
        qrLiveImg.style.display = "none";
    }

    function renderLiveQR(firstName, lastName, jobTitle, department, email, mobile) {
        if (!qrPanel || typeof qrcode === "undefined") return;
        const text = buildVCard(firstName, lastName, jobTitle, department, email, mobile);
        try {
            const qr = qrcode(0, "M");
            qr.addData(text);
            qr.make();
            qrLiveImg.src = qr.createDataURL(9, 4);
            qrPanel.classList.add("is-preview");
            qrPlaceholder.style.display = "none";
            qrLiveImg.style.display = "block";
            qrPanel.classList.remove("pulse");
            void qrPanel.offsetWidth;
            qrPanel.classList.add("pulse");
            window.setTimeout(() => qrPanel.classList.remove("pulse"), 450);
        } catch (err) {
            showQrPlaceholder();
        }
    }

    function updateLivePreviewQR(firstName, lastName, staffId, jobTitle, department, email, mobile) {
        if (!qrPanel) return;
        const ready = firstName.trim() && lastName.trim() && staffId.trim();
        window.clearTimeout(qrDebounceTimer);
        if (!ready) {
            showQrPlaceholder();
            return;
        }
        qrDebounceTimer = window.setTimeout(() => renderLiveQR(firstName, lastName, jobTitle, department, email, mobile), 120);
    }

    function syncCardFromActiveForm() {
        syncCard(
            fieldValue("first_name"), fieldValue("last_name"), fieldValue("staff_id"),
            fieldValue("gender"), fieldValue("department"), fieldValue("job_title"),
            fieldValue("employment_status"), fieldValue("email"), fieldValue("mobile_number")
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
        const cropBtn = document.getElementById(prefix + "-photo-crop");
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
                    if (cropBtn) cropBtn.disabled = false;
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
            if (cropBtn) cropBtn.disabled = true;
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

        // --- Crop tool: a real rectangular crop step, distinct from the
        // circular zoom/pan refinement above. Operates on the full
        // original image and replaces it with the cropped result, which
        // zoom/pan then continue to apply to as usual. ---
        const cropModal = document.getElementById(prefix + "-crop-modal");
        if (cropBtn && cropModal) {
            const cropStage = document.getElementById(prefix + "-crop-stage");
            const cropImg = document.getElementById(prefix + "-crop-img");
            const cropBox = document.getElementById(prefix + "-crop-box");
            const cropCancel = document.getElementById(prefix + "-crop-cancel");
            const cropApply = document.getElementById(prefix + "-crop-apply");

            const geo = { scale: 1, offsetX: 0, offsetY: 0, dispW: 0, dispH: 0 };
            let box = { x: 0, y: 0, size: 0 };
            let dragMode = null, startPointer = { x: 0, y: 0 }, startBox = null;

            function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

            function renderBox() {
                cropBox.style.left = box.x + "px";
                cropBox.style.top = box.y + "px";
                cropBox.style.width = box.size + "px";
                cropBox.style.height = box.size + "px";
            }

            function setupStage() {
                const stageW = cropStage.clientWidth, stageH = cropStage.clientHeight;
                const scale = Math.min(stageW / cropImg.naturalWidth, stageH / cropImg.naturalHeight);
                geo.scale = scale;
                geo.dispW = cropImg.naturalWidth * scale;
                geo.dispH = cropImg.naturalHeight * scale;
                geo.offsetX = (stageW - geo.dispW) / 2;
                geo.offsetY = (stageH - geo.dispH) / 2;
                cropImg.style.width = geo.dispW + "px";
                cropImg.style.height = geo.dispH + "px";
                cropImg.style.left = geo.offsetX + "px";
                cropImg.style.top = geo.offsetY + "px";

                const size = Math.min(geo.dispW, geo.dispH);
                box = { x: geo.offsetX + (geo.dispW - size) / 2, y: geo.offsetY + (geo.dispH - size) / 2, size };
                renderBox();
            }

            cropBtn.addEventListener("click", () => {
                if (!preview.src) return;
                cropImg.onload = setupStage;
                cropImg.src = preview.src;
                if (cropImg.complete && cropImg.naturalWidth) setupStage();
                cropModal.classList.add("show");
            });

            cropCancel.addEventListener("click", () => cropModal.classList.remove("show"));

            cropBox.addEventListener("pointerdown", (e) => {
                if (e.target.classList.contains("crop-box__handle")) return;
                dragMode = "move";
                startPointer = { x: e.clientX, y: e.clientY };
                startBox = { ...box };
                cropBox.setPointerCapture(e.pointerId);
            });
            cropBox.querySelectorAll(".crop-box__handle").forEach((handle) => {
                handle.addEventListener("pointerdown", (e) => {
                    e.stopPropagation();
                    dragMode = handle.dataset.handle;
                    startPointer = { x: e.clientX, y: e.clientY };
                    startBox = { ...box };
                    cropBox.setPointerCapture(e.pointerId);
                });
            });
            cropBox.addEventListener("pointermove", (e) => {
                if (!dragMode) return;
                const dx = e.clientX - startPointer.x, dy = e.clientY - startPointer.y;
                const right = geo.offsetX + geo.dispW, bottom = geo.offsetY + geo.dispH;

                if (dragMode === "move") {
                    box = {
                        x: clamp(startBox.x + dx, geo.offsetX, right - startBox.size),
                        y: clamp(startBox.y + dy, geo.offsetY, bottom - startBox.size),
                        size: startBox.size,
                    };
                } else {
                    let anchorX, anchorY, delta;
                    if (dragMode === "se") { anchorX = startBox.x; anchorY = startBox.y; delta = Math.max(dx, dy); }
                    else if (dragMode === "nw") { anchorX = startBox.x + startBox.size; anchorY = startBox.y + startBox.size; delta = Math.max(-dx, -dy); }
                    else if (dragMode === "ne") { anchorX = startBox.x; anchorY = startBox.y + startBox.size; delta = Math.max(dx, -dy); }
                    else { anchorX = startBox.x + startBox.size; anchorY = startBox.y; delta = Math.max(-dx, dy); }

                    const maxSize = dragMode === "se" ? Math.min(right - anchorX, bottom - anchorY)
                        : dragMode === "nw" ? Math.min(anchorX - geo.offsetX, anchorY - geo.offsetY)
                        : dragMode === "ne" ? Math.min(right - anchorX, anchorY - geo.offsetY)
                        : Math.min(anchorX - geo.offsetX, bottom - anchorY);
                    const size = clamp(startBox.size + delta, 30, maxSize);

                    if (dragMode === "se") box = { x: anchorX, y: anchorY, size };
                    else if (dragMode === "nw") box = { x: anchorX - size, y: anchorY - size, size };
                    else if (dragMode === "ne") box = { x: anchorX, y: anchorY - size, size };
                    else box = { x: anchorX - size, y: anchorY, size };
                }
                renderBox();
            });
            cropBox.addEventListener("pointerup", () => { dragMode = null; });
            cropBox.addEventListener("pointercancel", () => { dragMode = null; });

            cropApply.addEventListener("click", () => {
                const sx = (box.x - geo.offsetX) / geo.scale;
                const sy = (box.y - geo.offsetY) / geo.scale;
                const ssize = box.size / geo.scale;
                const outSize = 480;
                const canvas = document.createElement("canvas");
                canvas.width = outSize; canvas.height = outSize;
                canvas.getContext("2d").drawImage(cropImg, sx, sy, ssize, ssize, 0, 0, outSize, outSize);
                const dataUrl = canvas.toDataURL("image/jpeg", 0.92);

                preview.src = dataUrl;
                resetTransform();
                cropModal.classList.remove("show");
                if (onPreview) onPreview(dataUrl);
                bumpCard();
            });
        }
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
                    syncCard(r["First Name"], r["Last Name"], r["Staff ID"], r["Gender"], r["Department"], r["Job Title"], r["Employment Status"], r["Email"], r["Mobile Number"]);
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

                syncCard(r["First Name"], r["Last Name"], r["Staff ID"], r["Gender"], r["Department"], r["Job Title"], r["Employment Status"], r["Email"]);

                actForm.style.display = "block";
            } catch (err) {
                setBadge("error", "Something went wrong looking up your record. Please try again.");
            }
        });
    }

    // --- Microsoft SSO prefill: populates the New Registration form from a
    // signed-in staff member's Graph profile (see sso_routes.py's session
    // hand-off) and, if Graph returned a profile photo, loads it into the
    // same photo-upload pipeline a manual upload would use. ---
    const ssoDataEl = document.getElementById("sso-prefill-data");
    if (ssoDataEl) {
        let ssoPayload = null;
        try {
            ssoPayload = JSON.parse(ssoDataEl.textContent);
        } catch (err) {
            ssoPayload = null;
        }

        if (ssoPayload) {
            const profile = ssoPayload.profile || {};
            const setVal = (id, value) => {
                const el = document.getElementById(id);
                if (el && value) el.value = value;
            };

            setVal("r-first-name", profile.first_name);
            setVal("r-last-name", profile.last_name);
            setVal("r-staff-id", profile.staff_id);
            setVal("r-email", profile.email);
            setVal("r-mobile", profile.mobile_number);
            setVal("r-job-title", profile.job_title);
            setVal("r-uk-it-user-id", profile.uk_it_user_id);
            setVal("r-local-login", profile.local_login);

            const selectByText = (id, value) => {
                const el = document.getElementById(id);
                if (!el || !value) return;
                const needle = value.toLowerCase();
                const options = Array.from(el.options);
                // Azure AD's "department" field is often a short code (e.g.
                // "ITAC") rather than the portal's full department name --
                // exact match first, then fall back to a substring match
                // either direction so those still land on the right option.
                const match =
                    options.find((o) => o.value.toLowerCase() === needle) ||
                    options.find((o) => o.value.toLowerCase().includes(needle) || needle.includes(o.value.toLowerCase()));
                if (match) el.value = match.value;
            };
            selectByText("r-department", profile.department);
            selectByText("r-gender", profile.gender);
            selectByText("r-employment-status", profile.employment_status);
            selectByText("r-category", profile.category);
            setVal("r-misis", profile.misis);

            if (ssoPayload.photo) {
                fetch(ssoPayload.photo)
                    .then((res) => res.blob())
                    .then((blob) => {
                        const file = new File([blob], "microsoft-profile-photo.jpg", { type: blob.type || "image/jpeg" });
                        const dt = new DataTransfer();
                        dt.items.add(file);
                        const input = document.getElementById("r-photo");
                        if (input) {
                            input.files = dt.files;
                            input.dispatchEvent(new Event("change"));
                        }
                    })
                    .catch(() => {});
            }

            syncCardFromActiveForm();
            updateStepper();
        }
    }
})();
