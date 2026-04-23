document.addEventListener("DOMContentLoaded", function () {
    const badges = document.querySelectorAll('.category-badge');

    function updateBadgeStyle(b, checked) {
        if (checked) {
            b.classList.remove("bg-light", "text-dark", "border");
            b.classList.add("bg-primary", "text-white");
        } else {
            b.classList.add("bg-light", "text-dark", "border");
            b.classList.remove("bg-primary", "text-white");
        }
    }

    badges.forEach((b) => {
        const inputCheckbox = b.querySelector('input[type="checkbox"]');
        inputCheckbox.addEventListener("change", (event) => {
            updateBadgeStyle(b, event.target.checked);
        });
    });
});