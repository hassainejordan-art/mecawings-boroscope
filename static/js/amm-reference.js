(function () {
    'use strict';

    const modal = document.getElementById('amm-reference-modal');
    if (!modal) return;

    const searchInput = document.getElementById('amm-modal-search');
    const resultsEl = document.getElementById('amm-modal-results');
    const emptyEl = document.getElementById('amm-modal-empty');
    const closeBtn = document.getElementById('amm-modal-close');
    const cancelBtn = document.getElementById('amm-modal-cancel');
    const backdrop = modal.querySelector('.modal-backdrop');

    let activePhotoId = null;
    let onSelectCallback = null;
    let searchTimer = null;

    function getReportContext() {
        const aircraftPreset = document.getElementById('aircraft_preset');
        const aircraftCustom = document.getElementById('aircraft_custom');
        const enginePreset = document.getElementById('engine_type_preset');
        const engineCustom = document.getElementById('engine_type_custom');
        const customOption = window.CUSTOM_OPTION || '__custom__';

        let aircraftType = aircraftPreset ? aircraftPreset.value : '';
        if (aircraftType === customOption && aircraftCustom) {
            aircraftType = aircraftCustom.value.trim();
        }

        let engineType = enginePreset ? enginePreset.value : '';
        if (engineType === customOption && engineCustom) {
            engineType = engineCustom.value.trim();
        }

        return { aircraft_type: aircraftType, engine_type: engineType };
    }

    function renderResults(documents) {
        resultsEl.innerHTML = '';
        emptyEl.hidden = documents.length > 0;

        documents.forEach((doc) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'amm-modal-result';
            item.innerHTML = `
                <span class="amm-modal-result-name">${doc.document_name}</span>
                <span class="amm-modal-result-meta">${doc.aircraft_type} · ${doc.engine_type} · ${doc.ata_chapter}${doc.revision ? ' · Rev ' + doc.revision : ''}</span>
            `;
            item.addEventListener('click', () => selectDocument(doc));
            resultsEl.appendChild(item);
        });
    }

    function fetchDocuments(query) {
        const ctx = getReportContext();
        const params = new URLSearchParams();
        if (ctx.aircraft_type) params.set('aircraft_type', ctx.aircraft_type);
        if (ctx.engine_type) params.set('engine_type', ctx.engine_type);
        if (query) params.set('document_name', query);

        fetch('/api/amm-documents?' + params.toString())
            .then((res) => res.json())
            .then((data) => renderResults(data.documents || []))
            .catch(() => {
                resultsEl.innerHTML = '';
                emptyEl.hidden = false;
                emptyEl.textContent = 'Unable to load AMM documents.';
            });
    }

    function openModal(photoId, callback) {
        activePhotoId = photoId;
        onSelectCallback = callback;
        modal.hidden = false;
        document.body.classList.add('modal-open');
        if (searchInput) {
            searchInput.value = '';
            searchInput.focus();
        }
        fetchDocuments('');
    }

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove('modal-open');
        activePhotoId = null;
        onSelectCallback = null;
    }

    function selectDocument(doc) {
        if (onSelectCallback) onSelectCallback(doc);
        closeModal();
    }

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => fetchDocuments(searchInput.value.trim()), 250);
        });
    }

    closeBtn && closeBtn.addEventListener('click', closeModal);
    cancelBtn && cancelBtn.addEventListener('click', closeModal);
    backdrop && backdrop.addEventListener('click', closeModal);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) closeModal();
    });

    window.AmmReferencePicker = { open: openModal, close: closeModal };
})();
