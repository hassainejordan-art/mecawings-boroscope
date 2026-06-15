(function () {
    'use strict';

    const canvas = document.getElementById('signature-pad');
    const clearBtn = document.getElementById('clear-signature');
    const hiddenInput = document.getElementById('inspector_signature');
    const statusEl = document.getElementById('signature-status');
    const form = document.getElementById('report-form');

    if (!canvas || !hiddenInput) return;

    const ctx = canvas.getContext('2d');
    let drawing = false;
    let hasSignature = false;
    let loadedExisting = false;
    const hasExistingOnFile = Boolean(window.HAS_EXISTING_SIGNATURE);

    function resizeCanvas() {
        const rect = canvas.parentElement.getBoundingClientRect();
        const ratio = window.devicePixelRatio || 1;
        const width = Math.max(rect.width - 2, 300);
        const height = 180;
        const hadContent = hasSignature;

        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.strokeStyle = '#0B3D6B';
        ctx.lineWidth = 2.2;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        if (hadContent && hiddenInput.value) {
            restoreFromDataUrl(hiddenInput.value);
        } else if (loadedExisting && window.EXISTING_SIGNATURE_URL) {
            loadExistingSignature(window.EXISTING_SIGNATURE_URL);
        }
    }

    function getPoint(event) {
        const rect = canvas.getBoundingClientRect();
        const clientX = event.clientX ?? event.touches?.[0]?.clientX;
        const clientY = event.clientY ?? event.touches?.[0]?.clientY;
        return {
            x: clientX - rect.left,
            y: clientY - rect.top,
        };
    }

    function startDraw(event) {
        event.preventDefault();
        drawing = true;
        const point = getPoint(event);
        ctx.beginPath();
        ctx.moveTo(point.x, point.y);
    }

    function draw(event) {
        if (!drawing) return;
        event.preventDefault();
        const point = getPoint(event);
        ctx.lineTo(point.x, point.y);
        ctx.stroke();
        hasSignature = true;
        loadedExisting = false;
        updateStatus();
    }

    function endDraw() {
        drawing = false;
        syncSignature();
    }

    function updateStatus() {
        if (!statusEl) return;
        if (hasSignature) {
            statusEl.textContent = 'Signature captured';
            statusEl.classList.add('signature-status-active');
            return;
        }
        if (hasExistingOnFile && loadedExisting) {
            statusEl.textContent = 'Existing signature on file';
            statusEl.classList.remove('signature-status-active');
            return;
        }
        statusEl.textContent = 'No signature yet';
        statusEl.classList.remove('signature-status-active');
    }

    function syncSignature() {
        if (!hasSignature) {
            hiddenInput.value = '';
            return;
        }
        hiddenInput.value = canvas.toDataURL('image/png');
    }

    function restoreFromDataUrl(dataUrl) {
        const img = new Image();
        img.onload = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const drawWidth = parseInt(canvas.style.width, 10) || canvas.width;
            const drawHeight = parseInt(canvas.style.height, 10) || canvas.height;
            ctx.drawImage(img, 0, 0, drawWidth, drawHeight);
            hasSignature = true;
            updateStatus();
        };
        img.src = dataUrl;
    }

    function loadExistingSignature(url) {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const drawWidth = parseInt(canvas.style.width, 10) || canvas.width;
            const drawHeight = parseInt(canvas.style.height, 10) || canvas.height;
            ctx.drawImage(img, 0, 0, drawWidth, drawHeight);
            loadedExisting = true;
            hasSignature = false;
            hiddenInput.value = '';
            updateStatus();
        };
        img.onerror = () => {
            loadedExisting = false;
            updateStatus();
        };
        img.src = url;
    }

    function clearSignature() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        hasSignature = false;
        loadedExisting = false;
        hiddenInput.value = '';
        updateStatus();
    }

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    if (window.EXISTING_SIGNATURE_URL) {
        loadExistingSignature(window.EXISTING_SIGNATURE_URL);
    }

    canvas.addEventListener('mousedown', startDraw);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', endDraw);
    canvas.addEventListener('mouseleave', endDraw);

    canvas.addEventListener('touchstart', startDraw, { passive: false });
    canvas.addEventListener('touchmove', draw, { passive: false });
    canvas.addEventListener('touchend', endDraw);
    canvas.addEventListener('touchcancel', endDraw);

    if (clearBtn) clearBtn.addEventListener('click', clearSignature);

    if (form) {
        form.addEventListener('submit', () => {
            syncSignature();
        });
    }

    window.SignaturePad = {
        sync: syncSignature,
        clear: clearSignature,
        hasSignature: () => hasSignature,
        hasExistingOnFile: () => hasExistingOnFile && loadedExisting,
    };
})();
