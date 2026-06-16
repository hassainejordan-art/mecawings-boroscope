(function () {
    'use strict';

    const CUSTOM = window.CUSTOM_OPTION || '__custom__';

    function bindPresetToggle(selectId, wrapId, customInputId) {
        const select = document.getElementById(selectId);
        const wrap = document.getElementById(wrapId);
        const customInput = document.getElementById(customInputId);
        if (!select || !wrap) return;

        function sync() {
            const isCustom = select.value === CUSTOM;
            wrap.hidden = !isCustom;
            if (customInput) customInput.required = isCustom;
        }

        select.addEventListener('change', sync);
        sync();
    }

    bindPresetToggle('upload_aircraft_type', 'upload-aircraft-custom-wrap', 'upload_aircraft_custom');
    bindPresetToggle('upload_engine_type', 'upload-engine-custom-wrap', 'upload_engine_custom');
})();
