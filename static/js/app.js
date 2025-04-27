document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', (e) => {
            const submitButton = form.querySelector('button[type="submit"]');
            const spinner = document.createElement('div');
            spinner.className = 'spinner';
            submitButton.disabled = true;
            submitButton.appendChild(spinner);
            spinner.style.display = 'block';
        });
    });

    // Display notification if present in URL
    const urlParams = new URLSearchParams(window.location.search);
    const message = urlParams.get('message');
    const messageType = urlParams.get('type');
    if (message) {
        const notification = document.createElement('div');
        notification.className = messageType === 'success' ? 'success' : 'error';
        notification.textContent = message;
        document.querySelector('main').prepend(notification);
        setTimeout(() => notification.remove(), 5000); // Hide after 5 seconds
    }
});
