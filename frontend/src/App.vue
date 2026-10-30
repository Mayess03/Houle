<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

interface Stats {
  total_buoys: number;
  online_buoys: number;
  silent_buoys: number;
  buoys_with_low_battery: number;
  buoys_with_high_waves: number;
  total_active_alerts: number;
}

interface Measurement {
  measurement_id: string;
  buoy_id: string;
  measured_at: string;
  received_at: string;
  wave_height: number;
  battery_level: number;
  latitude: number;
  longitude: number;
}

interface Buoy {
  buoy_id: string;
  status: string;
  last_seen_at: string;
  latest_measurement: Measurement | null;
  alerts: string[] | null;
}

interface Alert {
  buoy_id: string;
  type: string;
  severity: string;
  message: string;
  value: number;
  threshold: number;
}

const stats = ref<Stats | null>(null);
const buoys = ref<Buoy[]>([]);
const alerts = ref<Alert[]>([]);
const loading = ref(true);
const error = ref("");

let refreshInterval: ReturnType<typeof setInterval> | undefined;
let inFlight = false;

async function fetchDashboard() {
  if (inFlight) return; // évite les requêtes qui se chevauchent
  inFlight = true;

  try {
    const [statsResponse, buoysResponse, alertsResponse] = await Promise.all([
      fetch("/api/stats"),
      fetch("/api/buoys"),
      fetch("/api/alerts"),
    ]);

    if (!statsResponse.ok || !buoysResponse.ok || !alertsResponse.ok) {
      throw new Error("Impossible de récupérer les données du serveur.");
    }

    const [statsData, buoysData, alertsData] = await Promise.all([
      statsResponse.json(),
      buoysResponse.json(),
      alertsResponse.json(),
    ]);

    stats.value = statsData;
    buoys.value = Array.isArray(buoysData) ? buoysData : [];
    alerts.value = Array.isArray(alertsData) ? alertsData : [];
    error.value = "";
  } catch (err) {
    error.value = "Backend inaccessible. Vérifie que le port-forward est actif.";
    console.error(err);
  } finally {
    loading.value = false;
    inFlight = false;
  }
}

function formatDate(date?: string | null) {
  if (!date) return "N/A";
  const d = new Date(date);
  return Number.isNaN(d.getTime()) ? "N/A" : d.toLocaleString();
}

function formatNumber(value: number | null | undefined, digits: number) {
  return typeof value === "number" ? value.toFixed(digits) : "N/A";
}

function formatAlertType(type: string) {
  return (type ?? "").replaceAll("_", " ");
}

onMounted(() => {
  fetchDashboard();
  refreshInterval = setInterval(fetchDashboard, 5000);
});

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval);
});
</script>

<template>
  <div class="dashboard">
    <header class="header">
      <div>
        <h1>Houle</h1>
        <p>Ocean Buoy Monitoring Platform</p>
      </div>
      <span class="live-indicator">● LIVE MONITORING</span>
    </header>

    <main class="content">
      <div v-if="error" class="error-banner">{{ error }}</div>

      <div v-if="loading" class="loading">Loading dashboard...</div>

      <template v-else-if="stats">
        <section class="stats-grid">
          <div class="stat-card">
            <span>Total Buoys</span>
            <strong>{{ stats.total_buoys }}</strong>
          </div>

          <div class="stat-card">
            <span>Online Buoys</span>
            <strong class="green">{{ stats.online_buoys }}</strong>
          </div>

          <div class="stat-card">
            <span>Silent Buoys</span>
            <strong class="red">{{ stats.silent_buoys }}</strong>
          </div>

          <div class="stat-card">
            <span>Active Alerts</span>
            <strong class="orange">{{ stats.total_active_alerts }}</strong>
          </div>
        </section>

        <section class="secondary-stats">
          <span>Low battery: <strong>{{ stats.buoys_with_low_battery }}</strong></span>
          <span>High waves: <strong>{{ stats.buoys_with_high_waves }}</strong></span>
        </section>

        <section class="panel">
          <h2>Fleet Overview</h2>

          <div class="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Buoy ID</th>
                  <th>Status</th>
                  <th>Wave Height</th>
                  <th>Battery</th>
                  <th>Last Seen</th>
                </tr>
              </thead>

              <tbody>
                <tr v-for="buoy in buoys" :key="buoy.buoy_id">
                  <td class="buoy-id">{{ buoy.buoy_id }}</td>
                  <td>
                    <span
                      class="status"
                      :class="(buoy.status ?? 'unknown').toLowerCase()"
                    >
                      {{ buoy.status ?? "unknown" }}
                    </span>
                  </td>
                  <td>
                    {{ formatNumber(buoy.latest_measurement?.wave_height, 2) }} m
                  </td>
                  <td
                    :class="{
                      'low-battery': buoy.alerts?.includes('low_battery')
                    }"
                  >
                    {{ formatNumber(buoy.latest_measurement?.battery_level, 1) }}%
                  </td>
                  <td>{{ formatDate(buoy.last_seen_at) }}</td>
                </tr>

                <tr v-if="buoys.length === 0">
                  <td colspan="5" class="empty">No buoys found.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <h2>Active Alerts</h2>

          <div v-if="alerts.length === 0" class="empty">
            No active alerts. All systems operational.
          </div>

          <div v-else class="alerts-list">
            <div
              v-for="(alert, index) in alerts"
              :key="`${alert.buoy_id}-${alert.type}-${index}`"
              class="alert-item"
            >
              <div>
                <strong>{{ alert.buoy_id }}</strong>
                <p>{{ alert.message }}</p>
                <small>{{ formatAlertType(alert.type) }}</small>
              </div>

              <span class="alert-value">
                {{ alert.value }} / {{ alert.threshold }}
              </span>
            </div>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style>
:root {
  font-family: Inter, Arial, sans-serif;
  color: #172033;
  background: #f3f6fb;
  font-synthesis: none;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
}

.header {
  background: #101d35;
  color: white;
  padding: 24px 6%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header h1 {
  margin: 0;
  font-size: 28px;
}

.header p {
  margin: 5px 0 0;
  color: #aab8ce;
}

.live-indicator {
  color: #65e6a5;
  font-size: 12px;
  font-weight: bold;
}

.content {
  max-width: 1200px;
  margin: 35px auto;
  padding: 0 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
}

.stat-card,
.panel {
  background: white;
  border: 1px solid #e5eaf1;
  border-radius: 12px;
  padding: 22px;
}

.stat-card span {
  display: block;
  color: #758197;
  font-size: 14px;
}

.stat-card strong {
  display: block;
  margin-top: 12px;
  font-size: 32px;
}

.green { color: #159b68; }
.red { color: #dc4b4b; }
.orange { color: #e58a28; }

.secondary-stats {
  display: flex;
  gap: 30px;
  padding: 22px 4px;
  color: #68758a;
  font-size: 14px;
}

.panel {
  margin-bottom: 24px;
}

.panel h2 {
  margin: 0 0 22px;
  font-size: 19px;
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  white-space: nowrap;
}

th {
  color: #8290a4;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

th, td {
  padding: 15px 12px;
  border-bottom: 1px solid #edf0f5;
}

td {
  font-size: 14px;
}

.buoy-id {
  font-weight: bold;
}

.status {
  padding: 5px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: bold;
  background: #e5f7ef;
  color: #16845b;
}

.status.silent,
.status.offline,
.status.unknown {
  background: #fdeaea;
  color: #c53c3c;
}

.low-battery {
  color: #d97706;
  font-weight: bold;
}

.alerts-list {
  display: grid;
  gap: 12px;
}

.alert-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
  padding: 16px;
  background: #fff8ed;
  border: 1px solid #f5dfbd;
  border-radius: 9px;
}

.alert-item p {
  margin: 6px 0;
  font-size: 14px;
}

.alert-item small {
  color: #9a7650;
}

.alert-value {
  font-size: 13px;
  color: #a66b22;
  white-space: nowrap;
}

.empty,
.loading {
  color: #8290a4;
  padding: 18px 0;
}

.error-banner {
  background: #fdeaea;
  color: #b83232;
  padding: 14px;
  border-radius: 8px;
  margin-bottom: 20px;
}

@media (max-width: 750px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .header {
    gap: 15px;
    flex-wrap: wrap;
  }

  .secondary-stats {
    flex-wrap: wrap;
    gap: 12px;
  }
}
</style>