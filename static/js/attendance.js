function updateRow(row) {
    const cb = row.querySelector('input[type="checkbox"]');
    row.className = cb.checked ? 'present' : 'absent';
}

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', function() {
            updateRow(this.closest('tr'));
            updateCounts();
        });
        updateRow(cb.closest('tr'));
    });
    updateCounts();
});

function updateCounts() {
    const total = document.querySelectorAll('tr[data-reg]').length;
    const present = document.querySelectorAll('input:checked').length;
    const absent = total - present;
    document.getElementById('total').textContent = total;
    document.getElementById('present').textContent = present;
    document.getElementById('absent').textContent = absent;
    document.getElementById('submitBtn').disabled = total === 0;
}

function loadStudents() {
    document.querySelector('form').submit();
}
