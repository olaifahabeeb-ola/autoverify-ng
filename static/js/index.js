// index.js — extracted live-clock logic from templates/index.html
document.addEventListener('DOMContentLoaded', () => {
  function updateClock() {
    const now = new Date();
    const clock = document.getElementById('live-clock');
    const dateEl = document.getElementById('live-date');
    if (!clock || !dateEl) return;
    clock.textContent = now.toLocaleTimeString();
    dateEl.textContent = now.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  }
  updateClock();
  setInterval(updateClock, 1000);
});
