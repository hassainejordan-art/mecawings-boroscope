(function () {
    'use strict';

    const ENGINE_AREAS = window.ENGINE_AREAS || [
        'Fan', 'Booster', 'HPC', 'Combustion Chamber', 'HPT NGV', 'HPT Blade', 'LPT',
    ];

    const photos = [];
    let photoIdCounter = 0;

    const dropZone = document.getElementById('drop-zone');
    const photoInput = document.getElementById('photo-input');
    const gallery = document.getElementById('gallery');
    const galleryEmpty = document.getElementById('gallery-empty');
    const photosMetaInput = document.getElementById('photos_meta');
    const submitBtn = document.getElementById('submit-btn');
    const summaryBar = document.getElementById('summary-bar');
    const form = document.getElementById('report-form');

    const countEls = {
        Acceptable: document.getElementById('count-acceptable'),
        Monitor: document.getElementById('count-monitor'),
        Reject: document.getElementById('count-reject'),
        total: document.getElementById('count-total'),
    };

    if (!dropZone || !photoInput) return;

    function areaOptions(selected) {
        return ENGINE_AREAS.map((area) =>
            `<option value="${area}"${area === selected ? ' selected' : ''}>${area}</option>`
        ).join('');
    }

    function updatePhotoNumbers() {
        gallery.querySelectorAll('.photo-card').forEach((card, index) => {
            const badge = card.querySelector('.photo-number-badge');
            if (badge) badge.textContent = `#${index + 1}`;
        });
    }

    function updateSummary() {
        const counts = { Acceptable: 0, Monitor: 0, Reject: 0 };
        photos.forEach((p) => {
            if (counts[p.severity] !== undefined) counts[p.severity]++;
        });

        countEls.Acceptable.textContent = counts.Acceptable;
        countEls.Monitor.textContent = counts.Monitor;
        countEls.Reject.textContent = counts.Reject;
        countEls.total.textContent = photos.length;

        summaryBar.hidden = photos.length === 0;
        submitBtn.disabled = photos.length === 0;
        galleryEmpty.classList.toggle('hidden', photos.length > 0);
    }

    function syncMeta() {
        photosMetaInput.value = JSON.stringify(
            photos.map((p) => ({
                area: p.area,
                defect_description: p.defect_description,
                severity: p.severity,
            }))
        );
    }

    function syncFileInput() {
        const dt = new DataTransfer();
        photos.forEach((p) => dt.items.add(p.file));
        photoInput.files = dt.files;
    }

    function applySeverityStyle(select, severity) {
        select.className = `severity-select ${severity.toLowerCase()}`;
    }

    function applyCardSeverity(card, severity) {
        card.className = `photo-card severity-${severity.toLowerCase()}`;
    }

    function createPhotoCard(photo) {
        const card = document.createElement('article');
        card.className = `photo-card severity-${photo.severity.toLowerCase()}`;
        card.dataset.id = photo.id;

        card.innerHTML = `
            <div class="photo-card-image">
                <span class="photo-number-badge">#${photos.length}</span>
                <img src="${photo.previewUrl}" alt="${photo.file.name}">
                <span class="classification-badge badge-${photo.severity.toLowerCase()}">${photo.severity}</span>
            </div>
            <div class="photo-card-body">
                <p class="photo-filename" title="${photo.file.name}">${photo.file.name}</p>
                <div class="form-group">
                    <label>Area Inspected</label>
                    <select class="area-select" aria-label="Area inspected for ${photo.file.name}">
                        ${areaOptions(photo.area)}
                    </select>
                </div>
                <div class="form-group">
                    <label>Defect Description</label>
                    <textarea placeholder="Describe the defect observed…" rows="2"
                        aria-label="Defect description for ${photo.file.name}"></textarea>
                </div>
                <div class="photo-card-actions">
                    <div class="form-group form-group-inline">
                        <label>Severity</label>
                        <select class="severity-select ${photo.severity.toLowerCase()}"
                            aria-label="Severity for ${photo.file.name}">
                            <option value="Acceptable">Acceptable</option>
                            <option value="Monitor">Monitor</option>
                            <option value="Reject">Reject</option>
                        </select>
                    </div>
                    <button type="button" class="btn-remove" aria-label="Remove ${photo.file.name}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        const areaSelect = card.querySelector('.area-select');
        const textarea = card.querySelector('textarea');
        const severitySelect = card.querySelector('.severity-select');
        const removeBtn = card.querySelector('.btn-remove');
        const badge = card.querySelector('.classification-badge');

        severitySelect.value = photo.severity;

        areaSelect.addEventListener('change', () => {
            photo.area = areaSelect.value;
            syncMeta();
        });

        textarea.addEventListener('input', () => {
            photo.defect_description = textarea.value;
            syncMeta();
        });

        severitySelect.addEventListener('change', () => {
            photo.severity = severitySelect.value;
            applySeverityStyle(severitySelect, photo.severity);
            applyCardSeverity(card, photo.severity);
            badge.className = `classification-badge badge-${photo.severity.toLowerCase()}`;
            badge.textContent = photo.severity;
            updateSummary();
            syncMeta();
        });

        removeBtn.addEventListener('click', () => removePhoto(photo.id));

        return card;
    }

    function addPhotos(fileList) {
        const newFiles = Array.from(fileList).filter((f) => f.type.startsWith('image/'));
        if (newFiles.length === 0) return;

        newFiles.forEach((file) => {
            const photo = {
                id: ++photoIdCounter,
                file,
                previewUrl: URL.createObjectURL(file),
                area: ENGINE_AREAS[0],
                defect_description: '',
                severity: 'Acceptable',
            };
            photos.push(photo);
            gallery.appendChild(createPhotoCard(photo));
        });

        updatePhotoNumbers();
        syncFileInput();
        syncMeta();
        updateSummary();
    }

    function removePhoto(id) {
        const index = photos.findIndex((p) => p.id === id);
        if (index === -1) return;

        URL.revokeObjectURL(photos[index].previewUrl);
        photos.splice(index, 1);

        const card = gallery.querySelector(`[data-id="${id}"]`);
        if (card) card.remove();

        updatePhotoNumbers();
        syncFileInput();
        syncMeta();
        updateSummary();
    }

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        addPhotos(e.dataTransfer.files);
    });

    photoInput.addEventListener('change', () => {
        if (photoInput.files.length > 0) addPhotos(photoInput.files);
    });

    form.addEventListener('submit', () => {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Generating PDF…';
    });

    updateSummary();
})();
