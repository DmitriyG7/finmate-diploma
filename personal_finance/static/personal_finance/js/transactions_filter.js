// static/personal_finance/js/transactions_filter.js
document.addEventListener("DOMContentLoaded", function () {
    const periodSelect = document.getElementById("id_period");
    const dateContainer = document.getElementById("date-range-container");

    function toggleDateFields() {
        if (periodSelect.value === "custom") {
            dateContainer.style.display = "block";
        } else {
            dateContainer.style.display = "none";
            // Очищаем поля при скрытии
            document.querySelector('[name="date_from"]').value = "";
            document.querySelector('[name="date_to"]').value = "";
        }
    }

    periodSelect.addEventListener("change", toggleDateFields);
    toggleDateFields(); // при загрузке
});