// static/js/category-toggle.js
document.addEventListener('DOMContentLoaded', function() {
    const categorySelect = document.getElementById('id_category');
    const newCategoryField = document.getElementById('new-category-field');
    const newCategoryInput = document.getElementById('id_new_category_name');
    const showButton = document.getElementById('show-new-category');


    // Показываем поле ввода при клике на кнопку
    showButton.addEventListener('click', function() {
        newCategoryField.style.display = 'block';
        newCategoryInput.focus();
        categorySelect.value = ''; // Сбрасываем выбор в списке
    });

    // Скрываем поле ввода, если выбрана категория из списка
    categorySelect.addEventListener('change', function() {
        if (this.value) {
            newCategoryField.style.display = 'none';
            newCategoryInput.value = '';
        }
    });
});
