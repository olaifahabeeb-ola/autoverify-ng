// batch.js — extracted batch progress indicator logic
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('batch-form');
  form?.addEventListener('submit', function () {
    const btn = document.getElementById('batch-submit-btn');
    const progress = document.getElementById('batch-progress');
    const fileCount = document.getElementById('batch-images')?.files.length || 0;
    progress.classList.remove('d-none');
    document.getElementById('batch-progress-bar').textContent = `Processing ${fileCount} image(s), please wait...`;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
  });
});
