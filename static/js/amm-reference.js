(function () {
    'use strict';

    const modal = document.getElementById('amm-reference-modal');
    if (!modal) return;

    const keywordInput = document.getElementById('amm-modal-keyword');
    const ataInput = document.getElementById('amm-modal-ata');
    const documentNameInput = document.getElementById('amm-modal-document-name');
    const searchBtn = document.getElementById('amm-modal-search-btn');
    const resultsEl = document.getElementById('amm-modal-results');
    const emptyEl = document.getElementById('amm-modal-empty');
    const closeBtn = document.getElementById('amm-modal-close');
    const cancelBtn = document.getElementById('amm-modal-cancel');
    const backdrop = modal.querySelector('.modal-backdrop');

    let onSelectCallback = null;
    let pickerContext = {};

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

    function defaultKeywordFromArea(area) {
        if (!area) return '';
        const match = String(area).match(/[A-Za-z0-9]{2,}/);
        return match ? match[0] : area;
    }

    function renderResults(results) {
        resultsEl.innerHTML = '';
        emptyEl.hidden = results.length > 0;
        if (!results.length) {
            emptyEl.textContent = 'No matching AMM documents. Upload references in the AMM Library or adjust your search.';
        }

        results.forEach((result) => {
            const item = document.createElement('article');
            item.className = 'amm-modal-result';

            const pageLabel = result.page_number
                ? `<span class="amm-modal-result-meta">Page ${escapeHtml(result.page_number)}</span>`
                : '';

            const excerpt = result.text_excerpt
                ? `<p class="amm-modal-result-excerpt">${escapeHtml(result.text_excerpt)}</p>`
                : '';

            const statusMessage = result.message
                ? `<p class="amm-modal-result-status">${escapeHtml(result.message)}</p>`
                : '';

            item.innerHTML = `
                <div class="amm-modal-result-header">
                    <span class="amm-modal-result-name">${escapeHtml(result.document_name)}</span>
                    <span class="amm-modal-result-meta">${escapeHtml(result.ata_chapter)}</span>
                </div>
                ${pageLabel}
                ${excerpt}
                ${statusMessage}
            `;

            if (!result.not_indexed && result.text_excerpt) {
                const useBtn = document.createElement('button');
                useBtn.type = 'button';
                useBtn.className = 'btn btn-secondary btn-small amm-modal-use-btn';
                useBtn.textContent = 'Use this reference';
                useBtn.addEventListener('click', () => selectResult(result));
                item.appendChild(useBtn);
            }

            resultsEl.appendChild(item);
        });
    }

    function runSearch() {
        const ctx = getReportContext();
        const params = new URLSearchParams();
        if (ctx.aircraft_type) params.set('aircraft_type', ctx.aircraft_type);
        if (ctx.engine_type) params.set('engine_type', ctx.engine_type);

        const keyword = keywordInput ? keywordInput.value.trim() : '';
        if (keyword) params.set('keyword', keyword);
        if (ataInput && ataInput.value.trim()) params.set('ata_chapter', ataInput.value.trim());
        if (documentNameInput && documentNameInput.value.trim()) {
            params.set('document_name', documentNameInput.value.trim());
        }

        resultsEl.innerHTML = '<p class="amm-modal-empty">Searching…</p>';
        emptyEl.hidden = true;

        fetch('/api/amm-search?' + params.toString())
            .then((res) => res.json())
            .then((data) => renderResults(data.results || []))
            .catch(() => {
                resultsEl.innerHTML = '';
                emptyEl.hidden = false;
                emptyEl.textContent = 'Unable to search AMM documents.';
            });
    }

    function openModal(photoId, callback, context) {
        onSelectCallback = callback;
        pickerContext = context || {};
        modal.hidden = false;
        document.body.classList.add('modal-open');
        if (keywordInput) {
            keywordInput.value = defaultKeywordFromArea(pickerContext.inspected_area);
            keywordInput.focus();
        }
        if (ataInput) ataInput.value = '';
        if (documentNameInput) documentNameInput.value = '';
        resultsEl.innerHTML = '';
        emptyEl.hidden = true;
    }

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove('modal-open');
        onSelectCallback = null;
        pickerContext = {};
    }

    function selectResult(result) {
        if (onSelectCallback) onSelectCallback(result);
        closeModal();
    }

    searchBtn && searchBtn.addEventListener('click', runSearch);
    keywordInput && keywordInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            runSearch();
        }
    });

    closeBtn && closeBtn.addEventListener('click', closeModal);
    cancelBtn && cancelBtn.addEventListener('click', closeModal);
    backdrop && backdrop.addEventListener('click', closeModal);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) closeModal();
    });

    window.AmmReferencePicker = { open: openModal, close: closeModal };
})();
