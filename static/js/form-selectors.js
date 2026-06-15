(function () {
    'use strict';

    const CUSTOM = '__custom__';

    function initPresetField(presetId, customWrapId, customInputId, targetName) {
        const preset = document.getElementById(presetId);
        const wrap = document.getElementById(customWrapId);
        const custom = document.getElementById(customInputId);
        if (!preset) return;

        function sync() {
            const isCustom = preset.value === CUSTOM;
            if (wrap) wrap.hidden = !isCustom;
            if (custom) custom.required = isCustom;
        }

        preset.addEventListener('change', sync);
        sync();
    }

    initPresetField('aircraft_preset', 'aircraft-custom-wrap', 'aircraft_custom', 'aircraft');
    initPresetField('engine_type_preset', 'engine-type-custom-wrap', 'engine_type_custom', 'engine_type');
})();
