(function () {
    'use strict';

    const modal = document.getElementById('amm-reference-modal');
    if (!modal) return;

    const keywordInput = document.getElementById('amm-modal-keyword');
    const ataInput = document.getElementById('amm-modal-ata');
    const referenceInput = document.getElementById('amm-modal-reference');
    const resultsEl = document.getElementById('amm-modal-results');
    const emptyEl = document.getElementById('amm-modal-empty');
    const closeBtn = document.getElementById('amm-modal-close');
    const cancelBtn = document.getElementById('amm-modal-cancel');
    const backdrop = modal.querySelector('.modal-backdrop');

    let onSelectCallback = null;
    let pickerContext = {};
    let searchTimer = null;

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

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
            const excerpt = doc.text_excerpt
                ? `<span class="amm-modal-result-excerpt">${escapeHtml(doc.text_excerpt)}</span>`
                : '';
            item.innerHTML = `
                <span class="amm-modal-result-name">${escapeHtml(doc.document_name)}</span>
                <span class="amm-modal-result-meta">${escapeHtml(doc.aircraft_type)} · ${escapeHtml(doc.engine_type)} · ${escapeHtml(doc.ata_chapter)}${doc.revision ? ' · Rev ' + escapeHtml(doc.revision) : ''}</span>
                ${excerpt}
            `;
            item.addEventListener('click', () => selectDocument(doc));
            resultsEl.appendChild(item);
        });
    }

    function fetchDocuments() {
        const ctx = getReportContext();
        const params = new URLSearchParams();
        if (ctx.aircraft_type) params.set('aircraft_type', ctx.aircraft_type);
        if (ctx.engine_type) params.set('engine_type', ctx.engine_type);
        const keyword = keywordInput ? keywordInput.value.trim() : '';
        const combinedKeyword = [keyword, pickerContext.inspected_area].filter(Boolean).join(' ');
        if (combinedKeyword) params.set('keyword', combinedKeyword);
        if (ataInput && ataInput.value.trim()) params.set('ata_chapter', ataInput.value.trim());
        if (referenceInput && referenceInput.value.trim()) params.set('amm_reference', referenceInput.value.trim());

        fetch('/api/amm-documents?' + params.toString())
            .then((res) => res.json())
            .then((data) => renderResults(data.documents || []))
            .catch(() => {
                resultsEl.innerHTML = '';
                emptyEl.hidden = false;
                emptyEl.textContent = 'Unable to load AMM documents.';
            });
    }

    function scheduleSearch() {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(fetchDocuments, 250);
    }

    function openModal(photoId, callback, context) {
        onSelectCallback = callback;
        pickerContext = context || {};
        modal.hidden = false;
        document.body.classList.add('modal-open');
        if (keywordInput) {
            keywordInput.value = pickerContext.inspected_area || '';
            keywordInput.focus();
        }
        if (ataInput) ataInput.value = '';
        if (referenceInput) referenceInput.value = '';
        fetchDocuments();
    }

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove('modal-open');
        onSelectCallback = null;
        pickerContext = {};
    }

    function selectDocument(doc) {
        if (onSelectCallback) onSelectCallback(doc);
        closeModal();
    }

    [keywordInput, ataInput, referenceInput].forEach((input) => {
        if (input) input.addEventListener('input', scheduleSearch);
    });

    closeBtn && closeBtn.addEventListener('click', closeModal);
    cancelBtn && cancelBtn.addEventListener('click', closeModal);
    backdrop && backdrop.addEventListener('click', closeModal);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) closeModal();
    });

    window.AmmReferencePicker = { open: openModal, close: closeModal };
})();
