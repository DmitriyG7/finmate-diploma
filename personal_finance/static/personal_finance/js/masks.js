// static/js/masks.js
function initMasks() {
    // Настройки маски для денег
    const moneyConfig = {
        alias: "decimal",
        groupSeparator: " ",
        radixPoint: ".",
        autoGroup: true,
        digits: 2,
        digitsOptional: false,
        placeholder: "0",
        rightAlign: false,
        suffix: " ₽",
        removeMaskOnSubmit: true
    };

    // Настройки маски для даты
    const dateConfig = {
        alias: "datetime",
        inputFormat: "dd.mm.yyyy",
        placeholder: "дд.мм.гггг",
        min: "01.01.1900",
        max: "31.12.2099",
        showMaskOnHover: false
    };

    // Применяем маски по селекторам классов
    Inputmask(moneyConfig).mask(document.querySelectorAll('.money-mask'));
    Inputmask(dateConfig).mask(document.querySelectorAll('.date-mask'));
}

document.addEventListener("DOMContentLoaded", initMasks);