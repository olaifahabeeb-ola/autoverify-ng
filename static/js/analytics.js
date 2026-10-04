// analytics.js — extracted from templates/analytics.html to comply with CSP
document.addEventListener('DOMContentLoaded', () => {
  Chart.defaults.color = '#6b7280';
  Chart.defaults.borderColor = '#e2e6ea';
  Chart.defaults.font.family = "'Inter', 'Segoe UI', system-ui, sans-serif";

  let dailyScansChart, mismatchByMakeChart, recoveredChart, officerActivityChart;

  const rangeSelect = document.getElementById('range-select');
  const customInputs = document.getElementById('custom-range-inputs');

  if (rangeSelect) {
    rangeSelect.addEventListener('change', () => {
      customInputs.classList.toggle('d-none', rangeSelect.value !== 'custom');
    });
  }

  document.getElementById('apply-range-btn')?.addEventListener('click', loadAnalytics);

  function buildQuery() {
    const range = rangeSelect.value;
    if (range === 'custom') {
      const start = document.getElementById('range-start').value;
      const end = document.getElementById('range-end').value;
      return `range=custom&start=${start}&end=${end}`;
    }
    return `range=${range}`;
  }

  function loadAnalytics() {
    fetch(`/api/analytics-stats?${buildQuery()}`)
      .then(r => r.json())
      .then(data => {
        document.getElementById('range-label').textContent = `Showing ${data.start_date} to ${data.end_date}`;
        renderCharts(data);
        renderSummary(data.summary);
        renderOfficerPerformance(data.officer_performance);
        renderRecentScans(data.recent_scans);
      })
      .catch(err => console.warn('Could not load analytics:', err));
  }

  function renderSummary(summary) {
    document.getElementById('summary-total-scans').textContent = summary.total_scans;
    document.getElementById('summary-total-mismatches').textContent = summary.total_mismatches;
    document.getElementById('summary-total-stolen').textContent = summary.total_stolen;
    document.getElementById('summary-total-officers').textContent = summary.total_officers;
  }

  function renderOfficerPerformance(rows) {
    const tbody = document.getElementById('officer-performance-body');
    if (!rows.length) {
      tbody.innerHTML = 'No scans in this range.';
      return;
    }
    tbody.innerHTML = rows.map(r => ` <tr> <td>${r.officer}</td> <td>${r.total_scans}</td> <td>${r.mismatches}</td> <td>${r.stolen_recoveries}</td> </tr> `).join('');
  }

  function renderRecentScans(rows) {
    const tbody = document.getElementById('recent-scans-body');
    if (!rows.length) {
      tbody.innerHTML = 'No scans in this range.';
      return;
    }
    const badgeFor = (status) => {
      if (status === 'stolen') return '<span class="badge badge-stolen">\nSTOLEN\n</span>';
      if (status === 'mismatch') return '<span class="badge badge-mismatch">\nMISMATCH\n</span>';
      return '<span class="badge badge-clear">\nCLEAR\n</span>';
    };
    tbody.innerHTML = rows.map(r => ` <tr> <td>${r.timestamp}</td> <td>${r.plate_number}</td> <td>${r.officer}</td> <td>${badgeFor(r.status)}</td> </tr> `).join('');
  }

  function renderCharts(data) {
    // Daily scans (bar)
    if (dailyScansChart) dailyScansChart.destroy();
    dailyScansChart = new Chart(document.getElementById('dailyScansChart'), {
      type: 'bar',
      data: { labels: data.daily_scans.map(d => d.date), datasets: [{ label: 'Scans', data: data.daily_scans.map(d => d.count), backgroundColor: '#4caf50' }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    // Mismatches by make (horizontal bar)
    if (mismatchByMakeChart) mismatchByMakeChart.destroy();
    mismatchByMakeChart = new Chart(document.getElementById('mismatchByMakeChart'), {
      type: 'bar',
      data: { labels: data.mismatches_by_make.map(d => d.make), datasets: [{ label: 'Mismatches', data: data.mismatches_by_make.map(d => d.count), backgroundColor: '#e65100' }] },
      options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    // Recovered stolen vehicles over time (line)
    if (recoveredChart) recoveredChart.destroy();
    recoveredChart = new Chart(document.getElementById('recoveredChart'), {
      type: 'line',
      data: { labels: data.recovered_over_time.map(d => d.date), datasets: [{ label: 'Recovered', data: data.recovered_over_time.map(d => d.count), borderColor: '#2e7d32', backgroundColor: 'rgba(46,125,50,0.15)', tension: 0.3, fill: true, }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });

    // Officer activity (bar)
    if (officerActivityChart) officerActivityChart.destroy();
    officerActivityChart = new Chart(document.getElementById('officerActivityChart'), {
      type: 'bar',
      data: { labels: data.officer_activity.map(d => d.officer), datasets: [{ label: 'Scans', data: data.officer_activity.map(d => d.count), backgroundColor: '#66bb6a' }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
    });
  }

  loadAnalytics();
});
