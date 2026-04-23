document.addEventListener('DOMContentLoaded', function() {
    const avatarContainer = document.getElementById('avatarContainer');
    const avatarInput = document.getElementById('id_avatar');
    const avatarPreview = document.getElementById('avatarPreview');

    // Клик по аватару → открытие диалога выбора файла
    avatarContainer.addEventListener('click', function() {
        avatarInput.click();
    });

    // Мгновенное превью выбранного файла
    avatarInput.addEventListener('change', function() {
        const file = this.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                avatarPreview.src = e.target.result;
            }
            reader.readAsDataURL(file);
        }
    });
});
