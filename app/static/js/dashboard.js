const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');

const simStatus = document.getElementById('simStatus');
const stepVal = document.getElementById('stepVal');
const dosFlag = document.getElementById('dosFlag');
const pdrVal = document.getElementById('pdrVal');
const lossVal = document.getElementById('lossVal');
const throughputVal = document.getElementById('throughputVal');
const attackList = document.getElementById('attackList');
const logBox = document.getElementById('logBox');

const errorCtx = document.getElementById('errorChart');
const metricsCtx = document.getElementById('metricsChart');

const errorChart = new Chart(errorCtx, {
  type: 'bar',
  data: {
    labels: ['S0', 'S1', 'S2', 'S3', 'S4'],
    datasets: [{
      label: 'Estimation Error',
      data: [0, 0, 0, 0, 0],
      backgroundColor: ['#06b6d4', '#22c55e', '#f59e0b', '#fb7185', '#60a5fa'],
      borderRadius: 6
    }]
  },
  options: {
    responsive: true,
    plugins: { legend: { labels: { color: '#e2e8f0' } } },
    scales: {
      x: { ticks: { color: '#e2e8f0' } },
      y: { ticks: { color: '#e2e8f0' }, beginAtZero: true }
    }
  }
});

const metricsChart = new Chart(metricsCtx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [
      {
        label: 'Delivery Ratio',
        data: [],
        borderColor: '#06b6d4',
        tension: 0.25
      },
      {
        label: 'Packet Loss %',
        data: [],
        borderColor: '#ef4444',
        tension: 0.25
      }
    ]
  },
  options: {
    responsive: true,
    plugins: { legend: { labels: { color: '#e2e8f0' } } },
    scales: {
      x: { ticks: { color: '#e2e8f0' } },
      y: { ticks: { color: '#e2e8f0' }, beginAtZero: true }
    }
  }
});

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  return await res.json();
}

startBtn.addEventListener('click', async () => {
  const payload = {
    sensors: 5,
    step_interval_sec: 0.5,
    relay_buffer_size: 50,
    base_bandwidth_packets: 3,
    attack_profiles: [
      { attack_type: 'packet_drop', attack_probability: 0.12, attack_duration: 8, target_link: 'Hop1' },
      { attack_type: 'delay', attack_probability: 0.10, attack_duration: 10, target_link: 'Hop2' },
      { attack_type: 'bandwidth_flood', attack_probability: 0.08, attack_duration: 7, target_link: 'Hop2' }
    ]
  };
  await api('/start_simulation', { method: 'POST', body: JSON.stringify(payload) });
});

stopBtn.addEventListener('click', async () => {
  await api('/stop_simulation', { method: 'POST' });
});

function renderAttacks(data) {
  attackList.innerHTML = '';
  const active = data.active_attacks || [];
  if (!active.length) {
    attackList.innerHTML = '<li class="text-emerald-300">No active attacks</li>';
    return;
  }
  active.forEach((a) => {
    const li = document.createElement('li');
    li.className = 'bg-white/10 rounded-lg p-2';
    li.textContent = `${a.attack_type} on ${a.target_link} (remaining: ${a.remaining})`;
    attackList.appendChild(li);
  });
}

function renderLogs(logs) {
  const packets = logs.packet_logs || [];
  logBox.innerHTML = packets
    .slice(0, 20)
    .map((p) => `<div class="bg-white/10 rounded p-2">[Step ${p.step}] S${p.sensor_id} ${p.event} @ ${p.link} delay=${p.delay_steps}</div>`)
    .join('');
}

function updateMetricsChart(step, pdr, loss) {
  const labels = metricsChart.data.labels;
  const d0 = metricsChart.data.datasets[0].data;
  const d1 = metricsChart.data.datasets[1].data;

  labels.push(String(step));
  d0.push((pdr * 100).toFixed(2));
  d1.push(loss.toFixed(2));

  if (labels.length > 40) {
    labels.shift();
    d0.shift();
    d1.shift();
  }

  metricsChart.update('none');
}

async function refresh() {
  try {
    const [network, attacks, estimation, logs] = await Promise.all([
      api('/network_status'),
      api('/attack_status'),
      api('/estimation_data?limit=80'),
      api('/logs?limit=60')
    ]);

    simStatus.textContent = network.running ? 'Running' : 'Idle';
    stepVal.textContent = network.step ?? 0;
    dosFlag.textContent = network.dos_detected ? 'Yes' : 'No';
    dosFlag.className = network.dos_detected ? 'font-semibold text-rose-300' : 'font-semibold text-emerald-300';

    const pdr = network.packet_delivery_ratio ?? 0;
    const loss = network.packet_loss_percentage ?? 0;
    pdrVal.textContent = `${(pdr * 100).toFixed(1)}%`;
    lossVal.textContent = `${loss.toFixed(1)}%`;
    throughputVal.textContent = `${network.throughput ?? 0}`;

    const live = estimation.live || [];
    const errors = [0, 0, 0, 0, 0];
    for (const row of live) {
      if (row.sensor_id < errors.length) {
        errors[row.sensor_id] = row.estimation_error;
      }
    }
    errorChart.data.datasets[0].data = errors;
    errorChart.update('none');

    updateMetricsChart(network.step ?? 0, pdr, loss);
    renderAttacks(attacks);
    renderLogs(logs);
  } catch (err) {
    simStatus.textContent = 'Backend unavailable';
  }
}

setInterval(refresh, 1000);
refresh();
