// verify.js — extracted camera, capture, offline and alert logic from templates/verify.html
document.addEventListener('DOMContentLoaded', () => {
  const video = document.getElementById('camera-video');
  const canvas = document.getElementById('camera-canvas');
  const startBtn = document.getElementById('start-camera');
  const captureBtn = document.getElementById('capture-btn');
  const form = document.getElementById('verify-form');
  const imageDataInput = document.getElementById('image_data');
  const gpsLatInput = document.getElementById('gps_lat');
  const gpsLonInput = document.getElementById('gps_lon');
  const cameraStatus = document.getElementById('camera-status');

  const manualForm = document.getElementById('manual-form');
  const manualGpsLat = document.getElementById('manual_gps_lat');
  const manualGpsLon = document.getElementById('manual_gps_lon');

  let stream = null;
  let lastGpsLat = null;
  let lastGpsLon = null;

  function showCameraStatus(message, type = 'info') {
    cameraStatus.className = `alert mt-3 mb-0 alert-${type}`;
    cameraStatus.textContent = message;
    cameraStatus.classList.remove('d-none');
  }

  function hideCameraStatus() {
    cameraStatus.classList.add('d-none');
    cameraStatus.textContent = '';
  }

  startBtn?.addEventListener('click', async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showCameraStatus('This browser cannot access the camera. Use a modern phone browser or desktop camera-enabled browser.', 'danger');
        return;
      }
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      video.srcObject = stream;
      captureBtn.disabled = false;
      startBtn.textContent = 'Camera Active';
      startBtn.disabled = true;
      showCameraStatus('Camera ready. Capture the plate in clear light for the best OCR result.', 'success');
    } catch (err) {
      showCameraStatus('Could not access camera: ' + (err && err.message ? err.message : 'permission denied') + '. Grant camera permission and retry.', 'danger');
    }
  });

  function refreshGps() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      lastGpsLat = pos.coords.latitude;
      lastGpsLon = pos.coords.longitude;
      gpsLatInput.value = lastGpsLat;
      gpsLonInput.value = lastGpsLon;
      manualGpsLat.value = lastGpsLat;
      manualGpsLon.value = lastGpsLon;
    }, () => { /* ignore */ });
  }
  refreshGps();
  setInterval(refreshGps, 15000);

  captureBtn?.addEventListener('click', () => {
    if (!stream || !video.videoWidth || !video.videoHeight) {
      showCameraStatus('Camera is not ready yet. Start the camera and wait for the live view to load.', 'warning');
      return;
    }

    try {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const dataUrl = canvas.toDataURL('image/png');
      if (!dataUrl || dataUrl.length < 200) {
        showCameraStatus('The photo could not be captured. Please retry the scan.', 'danger');
        return;
      }

      imageDataInput.value = dataUrl;
      document.getElementById('manual_image_data').value = dataUrl;

      captureBtn.disabled = true;
      captureBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Verifying...';
      showCameraStatus('Capturing and verifying the plate...', 'info');

      submitWithOfflineCheck(form, imageDataInput.value);
    } catch (err) {
      showCameraStatus('The camera capture failed. Please retry and keep the plate in clear view.', 'danger');
    }
  });

  manualForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    const plateInput = manualForm.querySelector('[name="manual_plate"]');
    if (!plateInput || !plateInput.value.trim()) {
      showCameraStatus('Enter a plate number before submitting the manual check.', 'warning');
      plateInput.focus();
      return;
    }
    hideCameraStatus();
    submitWithOfflineCheck(manualForm, null);
  });

  // copy submitWithOfflineCheck and related helpers from original file
  const HOTLIST_CACHE_KEY = 'autoverify_hotlist_cache';
  const HOTLIST_SYNCED_KEY = 'autoverify_hotlist_synced_at';

  async function syncHotlistCache() {
    try {
      const resp = await fetch('/api/hotlist');
      if (!resp.ok) throw new Error('bad response');
      const data = await resp.json();
      localStorage.setItem(HOTLIST_CACHE_KEY, JSON.stringify(data.plates || []));
      localStorage.setItem(HOTLIST_SYNCED_KEY, new Date().toISOString());
      setOnlineBanner(false);
    } catch (err) {
      setOnlineBanner(true);
    }
  }

  function getCachedHotlist() {
    try { return JSON.parse(localStorage.getItem(HOTLIST_CACHE_KEY) || '[]'); } catch (e) { return []; }
  }

  function setOnlineBanner(offline) {
    const banner = document.getElementById('offline-banner');
    const syncedAt = localStorage.getItem(HOTLIST_SYNCED_KEY);
    document.getElementById('cache-synced-at').textContent = syncedAt ? new Date(syncedAt).toLocaleString() : 'never';
    banner.classList.toggle('d-none', !offline);
  }

  async function submitWithOfflineCheck(formEl, dataUrl) {
    if (!navigator.onLine) {
      setOnlineBanner(true);
      showCameraStatus('You are offline. Use the cached hotlist check until the connection returns.', 'warning');
      const manualPlate = formEl.querySelector('[name="manual_plate"]');
      if (manualPlate && manualPlate.value) {
        const plate = manualPlate.value.toUpperCase().replace(/\s/g, '');
        const cached = getCachedHotlist().map(p => p.toUpperCase().replace(/[\s-]/g, ''));
        if (cached.includes(plate.replace(/-/g, ''))) {
          triggerFullAlert('stolen', `🚨 OFFLINE MATCH: ${manualPlate.value} appears on the cached stolen hotlist! Verify manually and contact control room — live confirmation will run once you're back online.`);
          return;
        }
      }
    }

    try {
      showCameraStatus('Submitting scan to the verification system...', 'info');
      const formData = new FormData(formEl);
      const response = await fetch(formEl.action || window.location.pathname, { method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' } });

      if (!response.ok) throw new Error('Submission failed');
      const html = await response.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const replacement = doc.getElementById('scan-results-panel');
      const target = document.getElementById('scan-results-panel');
      if (replacement && target) target.innerHTML = replacement.innerHTML;
      if (formEl.id === 'verify-form') {
        captureBtn.disabled = false;
        captureBtn.innerHTML = '<i class="fa-solid fa-camera"></i> Capture &amp; Verify';
      }
      hideCameraStatus();
    } catch (err) {
      showCameraStatus('The scan could not be submitted. Check your connection and retry.', 'danger');
      if (formEl.id === 'verify-form') {
        captureBtn.disabled = false;
        captureBtn.innerHTML = '<i class="fa-solid fa-camera"></i> Capture &amp; Verify';
      }
    }
  }

  window.addEventListener('online', () => syncHotlistCache());
  window.addEventListener('offline', () => setOnlineBanner(true));
  syncHotlistCache();

  // Full-screen alert helpers (triggerFullAlert, speakAlert) and dismissal
  function triggerFullAlert(status, message) {
    const overlay = document.getElementById('full-alert-overlay');
    const title = document.getElementById('full-alert-title');
    const msgEl = document.getElementById('full-alert-message');
    const sound = document.getElementById('alert-sound');
    overlay.classList.remove('d-none', 'alert-stolen', 'alert-mismatch');
    overlay.classList.add(status === 'stolen' ? 'alert-stolen' : 'alert-mismatch');
    title.textContent = status === 'stolen' ? '🚨 STOLEN VEHICLE 🚨' : '⚠️ VEHICLE MISMATCH ⚠️';
    msgEl.textContent = message;
    sound.currentTime = 0;
    sound.play().catch(() => {});
    if (navigator.vibrate) navigator.vibrate([300,150,300,150,300]);
  }

  function speakAlert(status, count) {
    if (!('speechSynthesis' in window)) return;
    let text;
    if (status === 'stolen') text = count > 1 ? `Warning! Stolen vehicle detected among ${count} vehicles scanned.` : 'Warning! Stolen vehicle detected.';
    else if (status === 'mismatch') text = count > 1 ? `Warning! Plate mismatch detected among ${count} vehicles scanned.` : 'Warning! Plate does not match vehicle.'; else return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0; utterance.pitch = 1.0; window.speechSynthesis.cancel(); window.speechSynthesis.speak(utterance);
  }

  document.getElementById('dismiss-alert-btn')?.addEventListener('click', () => {
    const overlay = document.getElementById('full-alert-overlay');
    const sound = document.getElementById('alert-sound');
    overlay.classList.add('d-none'); sound.pause();
  });

  document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll('#vehicle-result-list [data-status]');
    if (!cards.length) return;
    let worstStatus = null; let worstMessage = ''; let alertCount = 0;
    cards.forEach(card => {
      const status = card.dataset.status; if (status === 'stolen' || status === 'mismatch') { alertCount++; if (status === 'stolen' && worstStatus !== 'stolen') { worstStatus = 'stolen'; worstMessage = card.dataset.message; } else if (status === 'mismatch' && worstStatus === null) { worstStatus = 'mismatch'; worstMessage = card.dataset.message; } }
    });
    if (worstStatus) { triggerFullAlert(worstStatus, worstMessage); speakAlert(worstStatus, alertCount); }
  });
});
