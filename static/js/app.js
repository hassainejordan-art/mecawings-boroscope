(function () {
    'use strict';

    const INSPECTION_AREAS = window.INSPECTION_AREAS || window.ENGINE_AREAS || [
        'Fan Blades', 'Fan Case', 'Booster', 'LPC', 'HPC', 'Combustion Chamber',
    ];
    const DEFECT_CATEGORIES = window.DEFECT_CATEGORIES || [
        'Cracking', 'Corrosion', 'Erosion', 'Dents / Deformation', 'Coating Loss',
        'Foreign Object Damage', 'Missing Material', 'Discoloration', 'Other',
    ];

    const photos = [];
    const removedExisting = new Set();
    let photoIdCounter = 0;

    const dropZone = document.getElementById('drop-zone');
    const photoInput = document.getElementById('photo-input');
    const gallery = document.getElementById('gallery');
    const galleryEmpty = document.getElementById('gallery-empty');
    const photosMetaInput = document.getElementById('photos_meta');
    const existingPhotosMetaInput = document.getElementById('existing_photos_meta');
    const removedPhotosInput = document.getElementById('removed_photos');
    const submitBtn = document.getElementById('submit-btn');
    const summaryBar = document.getElementById('summary-bar');
    const form = document.getElementById('report-form');
    const sourceFolder = window.SOURCE_FOLDER || '';

    const countEls = {
        Acceptable: document.getElementById('count-acceptable'),
        Monitor: document.getElementById('count-monitor'),
        Reject: document.getElementById('count-reject'),
        total: document.getElementById('count-total'),
    };

    if (!dropZone || !photoInput) return;

    function reportFileUrl(storedName) {
        if (!sourceFolder || !window.REPORT_FILES_BASE) return '';
        return window.REPORT_FILES_BASE.replace('__FOLDER__', encodeURIComponent(sourceFolder))
            + 'photos/' + encodeURIComponent(storedName);
    }

    function selectOptions(items, selected) {
        return items.map((item) =>
            `<option value="${item}"${item === selected ? ' selected' : ''}>${item}</option>`
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
            if (counts[p.classification] !== undefined) counts[p.classification]++;
        });

        countEls.Acceptable.textContent = counts.Acceptable;
        countEls.Monitor.textContent = counts.Monitor;
        countEls.Reject.textContent = counts.Reject;
        countEls.total.textContent = photos.length;

        summaryBar.hidden = photos.length === 0;
        submitBtn.disabled = photos.length === 0;
        galleryEmpty.classList.toggle('hidden', photos.length > 0);
    }

    function photoMetaPayload(p) {
        return {
            area: p.area,
            defect_category: p.defect_category,
            comment: p.comment,
            classification: p.classification,
        };
    }

    function syncMeta() {
        const newPhotos = photos.filter((p) => !p.isExisting);
        const existingPhotos = photos.filter((p) => p.isExisting);

        photosMetaInput.value = JSON.stringify(newPhotos.map(photoMetaPayload));
        existingPhotosMetaInput.value = JSON.stringify(
            existingPhotos.map((p) => ({
                filename: p.filename,
                stored_name: p.stored_name,
                ...photoMetaPayload(p),
            }))
        );
        removedPhotosInput.value = JSON.stringify([...removedExisting]);
    }

    function syncFileInput() {
        const dt = new DataTransfer();
        photos.filter((p) => p.file).forEach((p) => dt.items.add(p.file));
        photoInput.files = dt.files;
    }

    function applyClassificationStyle(select, classification) {
        select.className = `classification-select ${classification.toLowerCase()}`;
    }

    function applyCardClassification(card, classification) {
        card.className = `photo-card classification-${classification.toLowerCase()}`
            + (card.dataset.existing === '1' ? ' photo-card-existing' : '');
    }

    function createPhotoCard(photo) {
        const card = document.createElement('article');
        card.className = `photo-card classification-${photo.classification.toLowerCase()}`
            + (photo.isExisting ? ' photo-card-existing' : '');
        card.dataset.id = photo.id;
        if (photo.isExisting) card.dataset.existing = '1';

        const displayName = photo.filename || (photo.file && photo.file.name) || 'Photo';

        card.innerHTML = `
            <div class="photo-card-image">
                <span class="photo-number-badge">#${photos.length}</span>
                ${photo.isExisting ? '<span class="existing-photo-badge">Saved</span>' : ''}
                <img src="${photo.previewUrl}" alt="${displayName}">
                <span class="classification-badge badge-${photo.classification.toLowerCase()}">${photo.classification}</span>
            </div>
            <div class="photo-card-body">
                <p class="photo-filename" title="${displayName}">${displayName}</p>
                <div class="form-group">
                    <label>Area</label>
                    <select class="area-select">${selectOptions(INSPECTION_AREAS, photo.area)}</select>
                </div>
                <div class="form-group">
                    <label>Defect Category</label>
                    <select class="category-select">${selectOptions(DEFECT_CATEGORIES, photo.defect_category)}</select>
                </div>
                <div class="form-group">
                    <label>Comment</label>
                    <textarea class="comment-input" placeholder="Inspection comment…" rows="2">${photo.comment || ''}</textarea>
                </div>
                <div class="photo-card-actions">
                    <div class="form-group form-group-inline">
                        <label>Classification</label>
                        <select class="classification-select ${photo.classification.toLowerCase()}">
                            <option value="Acceptable">Acceptable</option>
                            <option value="Monitor">Monitor</option>
                            <option value="Reject">Reject</option>
                        </select>
                    </div>
                    <button type="button" class="btn-remove" aria-label="Remove ${displayName}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        const areaSelect = card.querySelector('.area-select');
        const categorySelect = card.querySelector('.category-select');
        const textarea = card.querySelector('.comment-input');
        const classificationSelect = card.querySelector('.classification-select');
        const removeBtn = card.querySelector('.btn-remove');
        const badge = card.querySelector('.classification-badge');

        classificationSelect.value = photo.classification;

        areaSelect.addEventListener('change', () => { photo.area = areaSelect.value; syncMeta(); });
        categorySelect.addEventListener('change', () => { photo.defect_category = categorySelect.value; syncMeta(); });
        textarea.addEventListener('input', () => { photo.comment = textarea.value; syncMeta(); });

        classificationSelect.addEventListener('change', () => {
            photo.classification = classificationSelect.value;
            applyClassificationStyle(classificationSelect, photo.classification);
            applyCardClassification(card, photo.classification);
            badge.className = `classification-badge badge-${photo.classification.toLowerCase()}`;
            badge.textContent = photo.classification;
            updateSummary();
            syncMeta();
        });

        removeBtn.addEventListener('click', () => removePhoto(photo.id));
        return card;
    }

    function normalizeExistingPhoto(data) {
        return {
            area: data.area || INSPECTION_AREAS[0],
            defect_category: data.defect_category || DEFECT_CATEGORIES[0],
            comment: data.comment || data.defect_description || '',
            classification: data.classification || data.severity || 'Acceptable',
        };
    }

    function addExistingPhoto(data) {
        const norm = normalizeExistingPhoto(data);
        const photo = {
            id: ++photoIdCounter,
            isExisting: true,
            stored_name: data.stored_name,
            filename: data.filename || data.stored_name,
            previewUrl: reportFileUrl(data.stored_name),
            ...norm,
        };
        photos.push(photo);
        gallery.appendChild(createPhotoCard(photo));
    }

    function addPhotos(fileList) {
        const newFiles = Array.from(fileList).filter((f) => f.type.startsWith('image/'));
        if (newFiles.length === 0) return;

        newFiles.forEach((file) => {
            photos.push({
                id: ++photoIdCounter,
                file,
                previewUrl: URL.createObjectURL(file),
                area: INSPECTION_AREAS[0],
                defect_category: DEFECT_CATEGORIES[0],
                comment: '',
                classification: 'Acceptable',
            });
            gallery.appendChild(createPhotoCard(photos[photos.length - 1]));
        });

        updatePhotoNumbers();
        syncFileInput();
        syncMeta();
        updateSummary();
    }

    function removePhoto(id) {
        const index = photos.findIndex((p) => p.id === id);
        if (index === -1) return;

        const photo = photos[index];
        if (photo.isExisting && photo.stored_name) {
            removedExisting.add(photo.stored_name);
        } else if (photo.previewUrl && photo.file) {
            URL.revokeObjectURL(photo.previewUrl);
        }

        photos.splice(index, 1);
        const card = gallery.querySelector(`[data-id="${id}"]`);
        if (card) card.remove();

        updatePhotoNumbers();
        syncFileInput();
        syncMeta();
        updateSummary();
    }

    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        addPhotos(e.dataTransfer.files);
    });
    photoInput.addEventListener('change', () => {
        if (photoInput.files.length > 0) addPhotos(photoInput.files);
    });

    form.addEventListener('submit', () => {
        if (window.SignaturePad) window.SignaturePad.sync();
        submitBtn.disabled = true;
        submitBtn.textContent = sourceFolder ? 'Updating PDF…' : 'Generating PDF…';
    });

    if (Array.isArray(window.EXISTING_PHOTOS)) {
        window.EXISTING_PHOTOS.forEach(addExistingPhoto);
        updatePhotoNumbers();
        syncMeta();
        updateSummary();
    } else {
        updateSummary();
    }
})();
