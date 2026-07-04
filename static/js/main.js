// Auto-hide alerts
document.addEventListener('DOMContentLoaded', function() {
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.transition = 'opacity .3s';
            alert.style.opacity = '0';
            setTimeout(function() { alert.remove(); }, 300);
        }, 4000);
    });
});

// Mobile nav toggle
function toggleMobileNav() {
    var nav = document.getElementById('mobileNav');
    nav.classList.toggle('open');
}

// Close mobile nav on backdrop click
document.addEventListener('DOMContentLoaded', function() {
    var nav = document.getElementById('mobileNav');
    if (nav) {
        nav.addEventListener('click', function(e) {
            if (e.target === this) {
                this.classList.remove('open');
            }
        });
    }
});
