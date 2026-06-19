<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getStats, getSessionStats, getTracePanel, getAllTraces } from '../services/api'
import AgentProgress from '../components/AgentProgress.vue'
import CostChart from '../components/CostChart.vue'
import TracePanel from '../components/TracePanel.vue'

// ===== Session tracking =====
const selectedSessionId = ref('')
const sessionInput = ref('')
const trackedSessions = ref(loadTracked())

// ===== Data =====
const globalStats = ref(null)
const sessionStats = ref(null)
const traceSessions = ref([])
const initialLoading = ref(true)
const refreshing = ref(false)
const error = ref(null)
const lastRefreshed = ref(null)

// ===== Auto-refresh =====
const autoRefresh = ref(true)
const REFRESH_INTERVAL = 5000
let refreshTimer = null

// ===== Derived =====
const hasSession = computed(() => !!selectedSessionId.value)
const hasData = computed(() => !!sessionStats.value)
const showContent = computed(() => !initialLoading.value)

const tokenData = computed(() => {
  const s = sessionStats.value || {}
  const inVal = s.total_tokens_in || 0
  const outVal = s.total_tokens_out || 0
  const total = inVal + outVal || 1
  return {
    in: inVal,
    out: outVal,
    total,
    inPct: (inVal / total) * 100,
    outPct: (outVal / total) * 100,
    display: (inVal + outVal).toLocaleString(),
  }
})

const costProps = computed(() => ({
  totalCost: sessionStats.value?.total_cost_usd || 0,
  modelCosts: sessionStats.value?.model_breakdown || {},
  toolCosts: sessionStats.value?.tool_breakdown || {},
}))

const latency = computed(() => {
  const avg = sessionStats.value?.avg_latency_ms || 0
  const steps = sessionStats.value?.steps || []
  const latencies = steps.map((s) => s.latency_ms).filter((v) => v > 0).sort((a, b) => a - b)
  const len = latencies.length
  // Use backend percentiles if available, else compute from raw latency data
  const p50 = sessionStats.value?.latency_p50 ?? (len ? latencies[Math.floor(len * 0.5)] : 0)
  const p95 = sessionStats.value?.latency_p95 ?? (len ? latencies[Math.floor(len * 0.95)] : 0)
  const p99 = sessionStats.value?.latency_p99 ?? (len ? latencies[Math.floor(len * 0.99)] : 0)
  const maxLat = Math.max(p99, avg, 1)
  return { avg, p50, p95, p99, maxLat }
})

const toolUsage = computed(() => {
  const breakdown = sessionStats.value?.tool_breakdown || {}
  return Object.entries(breakdown)
    .map(([name, data]) => ({ name, count: typeof data === 'object' ? (data.count || 0) : (data || 0) }))
    .sort((a, b) => b.count - a.count)
})

const maxToolCount = computed(() => Math.max(...toolUsage.value.map((t) => t.count), 1))

const agentSteps = computed(() => {
  // Prefer flow_steps (from supervisor intermediate_steps) — correct format
  const flowSteps = sessionStats.value?.flow_steps || []
  if (flowSteps.length) {
    return flowSteps.map((s) => ({
      name: s.name,
      label: s.label || s.name,
      status: s.status || 'done',
      duration: s.duration || 0,
      detail: s.detail || {},
    }))
  }
  // Fallback: cost_tracker steps use {agent, model, tokens_in, tokens_out, latency_ms}
  const steps = sessionStats.value?.steps || []
  if (!steps.length) return []
  return steps.map((s) => ({
    name: s.agent || s.name,
    label: s.agent || s.name,
    status: 'done',
    duration: s.latency_ms ? s.latency_ms / 1000 : 0,
    detail: {},
  }))
})

// ===== Persistence =====
function loadTracked() {
  try {
    return JSON.parse(localStorage.getItem('aiwear_tracked_sessions') || '[]')
  } catch { return [] }
}
function saveTracked() {
  try { localStorage.setItem('aiwear_tracked_sessions', JSON.stringify(trackedSessions.value)) } catch {}
}

function addSession(id) {
  if (!id || trackedSessions.value.find((s) => s.id === id)) return
  trackedSessions.value.push({ id, status: 'unknown', lastSeen: Date.now(), totalTokens: 0, totalCost: 0 })
  saveTracked()
}

function removeSession(id) {
  trackedSessions.value = trackedSessions.value.filter((s) => s.id !== id)
  saveTracked()
  if (selectedSessionId.value === id) {
    selectedSessionId.value = ''
    sessionStats.value = null
    traceSessions.value = []
  }
}

function selectSession(id) {
  selectedSessionId.value = id
  sessionInput.value = id
  fetchSessionAndTrace()
}

function trackNewSession() {
  const id = sessionInput.value.trim()
  if (!id) return
  addSession(id)
  selectSession(id)
}

// ===== Fetching =====
async function fetchSessionAndTrace() {
  if (!selectedSessionId.value) return
  try {
    const [sr, tr] = await Promise.allSettled([
      getSessionStats(selectedSessionId.value),
      getTracePanel(selectedSessionId.value),
    ])
    if (sr.status === 'fulfilled') {
      const body = sr.value.data?.data || sr.value.data
      sessionStats.value = body
      const found = trackedSessions.value.find((s) => s.id === selectedSessionId.value)
      if (found) {
        found.status = 'active'
        found.lastSeen = Date.now()
        found.totalTokens = (body.total_tokens_in || 0) + (body.total_tokens_out || 0)
        found.totalCost = body.total_cost_usd || 0
        saveTracked()
      }
      if (tr.status === 'fulfilled') {
        const tBody = tr.value.data?.data || tr.value.data
        if (tBody && tBody.steps) {
          traceSessions.value = [{
            id: selectedSessionId.value,
            steps: tBody.steps,
            totalTokens: found?.totalTokens || 0,
            totalCost: found?.totalCost || 0,
            status: tBody.steps.some((s) => s.status === 'running') ? 'running' : 'done',
          }]
        }
      }
    } else {
      if (sr.reason?.response?.status === 404) {
        const found = trackedSessions.value.find((s) => s.id === selectedSessionId.value)
        if (found) { found.status = 'not_found'; saveTracked() }
      }
      // Don't set error for 404 — just means no data yet
      if (sr.reason?.response?.status !== 404) {
        error.value = sr.reason?.message || '加载会话失败'
      }
    }
  } catch (err) {
    error.value = err?.message || '加载失败'
  }
}

async function fetchGlobalStats() {
  try {
    const { data } = await getStats()
    globalStats.value = data?.data || data
  } catch (e) { console.error('fetchGlobalStats failed:', e) }
}

async function fetchRecentSessions() {
  try {
    const { data } = await getAllTraces()
    const body = data?.data || data
    const details = body?.details || {}
    const ids = Object.keys(details)
    for (const id of ids) {
      if (!trackedSessions.value.find((s) => s.id === id)) {
        trackedSessions.value.push({
          id,
          status: 'done',
          lastSeen: details[id]?.last_ts ? Date.parse(details[id].last_ts) : Date.now(),
          totalTokens: 0,
          totalCost: 0,
        })
      }
    }
    if (ids.length) saveTracked()
    if (!selectedSessionId.value && ids.length) {
      const latest = ids.sort((a, b) => {
        const ta = details[a]?.last_ts || ''
        const tb = details[b]?.last_ts || ''
        return tb.localeCompare(ta)
      })[0]
      selectSession(latest)
    }
  } catch (e) { console.error('fetchRecentSessions failed:', e) }
}

async function fetchAll() {
  const wasInitial = initialLoading.value
  if (!wasInitial) refreshing.value = true
  error.value = null
  await Promise.all([
    fetchGlobalStats(),
    fetchRecentSessions(),
    fetchSessionAndTrace(),
  ])
  lastRefreshed.value = new Date()
  initialLoading.value = false
  refreshing.value = false
}

// ===== Lifecycle =====
onMounted(() => {
  fetchAll()
  if (autoRefresh.value) startRefresh()
})
onUnmounted(() => stopRefresh())

function startRefresh() {
  stopRefresh()
  refreshTimer = setInterval(fetchAll, REFRESH_INTERVAL)
}
function stopRefresh() {
  if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
}
watch(autoRefresh, (v) => { v ? startRefresh() : stopRefresh() })

// ===== Formatting =====
function fmtTime(d) { return d ? d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }
function fmtUSD(v) { return `$${(v || 0).toFixed(4)}` }

function heatmapLevel(count) {
  const r = count / maxToolCount.value
  if (r <= 0) return 0
  if (r <= 0.2) return 1
  if (r <= 0.4) return 2
  if (r <= 0.6) return 3
  if (r <= 0.8) return 4
  return 5
}

const slabel = (s) => ({ active: '活跃', done: '完成', not_found: '未找到', idle: '空闲', unknown: '未知' })[s] || s
</script>

<template>
  <div class="dashboard">
    <!-- ===== Header ===== -->
    <div class="dash-header">
      <div class="dash-header-left">
        <h1 class="page-title" style="margin:0">控制面板</h1>
        <span v-if="globalStats" class="dash-global-hint">
          累计 {{ ((globalStats.total_tokens || 0)).toLocaleString() }} tokens
        </span>
      </div>
      <div class="dash-header-right">
        <div class="dash-session-input">
          <input
            v-model="sessionInput"
            placeholder="输入 Session ID..."
            class="ui-input dash-input-slim"
            @keydown.enter="trackNewSession"
          />
          <button class="ui-btn ui-btn-primary dash-btn-slim" @click="trackNewSession" :disabled="!sessionInput.trim()">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            追踪
          </button>
        </div>
        <button class="ui-btn ui-btn-soft dash-btn-slim" :class="{ 'dash-spin': refreshing }" @click="fetchAll" :disabled="initialLoading">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6"/><path d="M2 11.5a10 10 0 0118.8-4.2M22 12.5a10 10 0 01-18.8 4.2"/></svg>
          刷新
        </button>
        <label class="dash-toggle">
          <input type="checkbox" v-model="autoRefresh" />
          <span class="dash-toggle-track"><span class="dash-toggle-knob"></span></span>
          <span class="dash-toggle-label">5s</span>
        </label>
      </div>
    </div>

    <!-- Auto-refresh status bar -->
    <div v-if="lastRefreshed" class="dash-status-bar">
      <span class="dash-status-dot" :class="{ 'dash-status-dot--active': refreshing }"></span>
      <span class="dash-status-text">
        {{ refreshing ? '刷新中...' : `上次更新 ${fmtTime(lastRefreshed)}` }}
      </span>
      <span v-if="!hasSession" class="dash-status-hint">输入 Session ID 查看详细统计</span>
      <span v-else-if="hasSession && !hasData" class="dash-status-hint">等待数据...</span>
    </div>

    <!-- Error banner (only when no data to show) -->
    <div v-if="error && !sessionStats" class="dash-error-banner">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F04438" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>{{ error }}</span>
      <button class="dash-retry-btn" @click="fetchAll">重试</button>
    </div>

    <!-- ===== Initial Loading Skeleton ===== -->
    <div v-if="initialLoading" class="dash-skel-wrap">
      <div class="dash-stats-grid">
        <div v-for="n in 3" :key="n" class="dash-card dash-card--skel">
          <div class="dash-skel-h"></div>
          <div class="dash-skel-vspace"></div>
          <div class="dash-skel-l w-70"></div>
          <div class="dash-skel-l w-90"></div>
          <div class="dash-skel-l w-50"></div>
        </div>
      </div>
      <div class="dash-skel-section">
        <div class="dash-skel-l w-40"></div>
        <div class="dash-skel-grid-4">
          <div v-for="n in 4" :key="n" class="dash-skel-box"></div>
        </div>
      </div>
    </div>

    <!-- ===== Content ===== -->
    <template v-else>
      <!-- No session placeholder -->
      <div v-if="!hasSession && !sessionStats" class="dash-welcome">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="20" stroke="#D0D5DD" stroke-width="1.5" fill="none" stroke-dasharray="4 4"/>
          <path d="M24 14v10l6 4" stroke="#D0D5DD" stroke-width="1.5" stroke-linecap="round"/>
          <path d="M14 34c2-4 6-6 10-6s8 2 10 6" stroke="#D0D5DD" stroke-width="1.5" stroke-linecap="round" fill="none"/>
        </svg>
        <h3 class="dash-welcome-title">监控中心</h3>
        <p class="dash-welcome-text">输入 Session ID 开始追踪 Agent 执行统计与费用</p>
      </div>

      <!-- Stats Cards -->
      <div class="dash-stats-grid">
        <!-- 1. Token Usage -->
        <div class="dash-card">
          <h3 class="dash-card-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#884BFF" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 3v18"/></svg>
            Token 用量
          </h3>
          <div class="dash-card-body">
            <div v-if="!hasData" class="dash-card-empty">等待数据...</div>
            <template v-else>
              <div class="dash-token-row">
                <span class="dash-token-label">输入</span>
                <span class="dash-token-count">{{ tokenData.in.toLocaleString() }}</span>
              </div>
              <div class="dash-token-track">
                <div class="dash-token-fill dash-token-fill--in" :style="{ width: tokenData.inPct + '%' }"></div>
              </div>
              <div class="dash-token-row">
                <span class="dash-token-label">输出</span>
                <span class="dash-token-count">{{ tokenData.out.toLocaleString() }}</span>
              </div>
              <div class="dash-token-track">
                <div class="dash-token-fill dash-token-fill--out" :style="{ width: tokenData.outPct + '%' }"></div>
              </div>
              <div class="dash-token-total">
                总计 <strong>{{ tokenData.display }}</strong> tokens
              </div>
            </template>
          </div>
        </div>

        <!-- 2. Cost -->
        <div class="dash-card">
          <h3 class="dash-card-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#12B76A" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>
            费用
          </h3>
          <div class="dash-card-body dash-card-body--compact">
            <CostChart
              v-if="hasData"
              :total-cost="costProps.totalCost"
              :model-costs="costProps.modelCosts"
              :tool-costs="costProps.toolCosts"
              :loading="false"
            />
            <div v-else class="dash-card-empty">等待数据...</div>
          </div>
        </div>

        <!-- 3. Latency -->
        <div class="dash-card">
          <h3 class="dash-card-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3538CD" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            延迟
          </h3>
          <div class="dash-card-body">
            <div v-if="!hasData" class="dash-card-empty">等待数据...</div>
            <template v-else>
              <div class="dash-latency-hero">{{ latency.avg }}<span class="dash-latency-unit"> ms</span></div>
              <div class="dash-latency-hero-label">平均延迟</div>
              <div class="dash-latency-bars">
                <div class="dash-latency-row">
                  <span class="dash-latency-name">p50</span>
                  <div class="dash-latency-track">
                    <div class="dash-latency-fill dash-latency-fill--p50" :style="{ width: (latency.p50 / latency.maxLat * 100) + '%' }"></div>
                  </div>
                  <span class="dash-latency-val">{{ latency.p50 }}ms</span>
                </div>
                <div class="dash-latency-row">
                  <span class="dash-latency-name">p95</span>
                  <div class="dash-latency-track">
                    <div class="dash-latency-fill dash-latency-fill--p95" :style="{ width: (latency.p95 / latency.maxLat * 100) + '%' }"></div>
                  </div>
                  <span class="dash-latency-val">{{ latency.p95 }}ms</span>
                </div>
                <div class="dash-latency-row">
                  <span class="dash-latency-name">p99</span>
                  <div class="dash-latency-track">
                    <div class="dash-latency-fill dash-latency-fill--p99" :style="{ width: (latency.p99 / latency.maxLat * 100) + '%' }"></div>
                  </div>
                  <span class="dash-latency-val">{{ latency.p99 }}ms</span>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- Tool Usage Heatmap -->
      <div class="dash-section">
        <h3 class="dash-section-title">工具调用热力图</h3>
        <div v-if="!hasData" class="dash-empty">选择会话后显示工具调用统计</div>
        <div v-else-if="!toolUsage.length" class="dash-empty">暂无工具调用数据</div>
        <div v-else class="dash-heatmap">
          <div
            v-for="tool in toolUsage"
            :key="tool.name"
            class="dash-heatmap-cell"
            :class="'dash-heatmap-lvl-' + heatmapLevel(tool.count)"
            :title="`${tool.name}: ${tool.count} 次`"
          >
            <span class="dash-heatmap-name">{{ tool.name }}</span>
            <span class="dash-heatmap-count">{{ tool.count }}</span>
          </div>
        </div>
      </div>

      <!-- Agent Pipeline -->
      <div class="dash-section">
        <h3 class="dash-section-title">Agent 流水线</h3>
        <div class="dash-pipeline-card">
          <AgentProgress :steps="agentSteps" :collapsed="false" />
        </div>
      </div>

      <!-- Active Sessions -->
      <div class="dash-section">
        <h3 class="dash-section-title">追踪会话</h3>
        <div v-if="!trackedSessions.length" class="dash-empty">
          尚无追踪会话。输入 Session ID 并点击"追踪"开始监控。
        </div>
        <div v-else class="dash-sessions">
          <div
            v-for="s in trackedSessions"
            :key="s.id"
            class="dash-session-row"
            :class="{ 'dash-session-row--sel': s.id === selectedSessionId }"
            @click="selectSession(s.id)"
          >
            <span class="dash-ss-dot" :class="'dash-ss-dot--' + s.status"></span>
            <span class="dash-ss-id">{{ s.id }}</span>
            <span v-if="s.totalTokens" class="dash-ss-stat">{{ s.totalTokens.toLocaleString() }} tok</span>
            <span v-if="s.totalCost" class="dash-ss-stat">${{ s.totalCost.toFixed(4) }}</span>
            <span class="dash-ss-badge" :class="'dash-ss-badge--' + s.status">{{ slabel(s.status) }}</span>
            <button class="dash-ss-rm" @click.stop="removeSession(s.id)" title="移除">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Trace Timeline -->
      <div class="dash-section">
        <h3 class="dash-section-title">执行追踪</h3>
        <div class="dash-trace-card">
          <TracePanel
            :sessions="traceSessions"
            :loading="false"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 960px;
  margin: 0 auto;
}

/* ===== Header ===== */
.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 6px;
}
.dash-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dash-global-hint {
  font-size: 12px;
  color: #B8A088;
  background: #FDF8F2;
  padding: 2px 10px;
  border-radius: 12px;
}
.dash-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dash-session-input {
  display: flex;
  gap: 4px;
  align-items: center;
}
.dash-input-slim {
  width: 170px !important;
  padding: 5px 10px !important;
  font-size: 12px !important;
}
.dash-btn-slim {
  padding: 5px 10px !important;
  font-size: 12px !important;
  gap: 4px !important;
  white-space: nowrap;
}
.dash-spin svg {
  animation: dash-rotate 0.8s linear infinite;
}
@keyframes dash-rotate { to { transform: rotate(360deg); } }

/* ===== Toggle Switch ===== */
.dash-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  user-select: none;
}
.dash-toggle input { display: none; }
.dash-toggle-track {
  position: relative;
  width: 30px;
  height: 16px;
  background: #E0D8CC;
  border-radius: 10px;
  transition: background 0.2s;
}
.dash-toggle input:checked + .dash-toggle-track {
  background: linear-gradient(135deg, #884BFF, #7530FE);
}
.dash-toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.dash-toggle input:checked + .dash-toggle-track .dash-toggle-knob {
  transform: translateX(14px);
}
.dash-toggle-label {
  font-size: 11px;
  color: #8B7355;
  font-weight: 500;
}

/* ===== Status Bar ===== */
.dash-status-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #B8A088;
  margin-bottom: 12px;
  padding: 0 2px;
}
.dash-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #D0D5DD;
  flex-shrink: 0;
}
.dash-status-dot--active {
  background: #12B76A;
  box-shadow: 0 0 6px rgba(18, 183, 106, 0.4);
  animation: dash-pulse-dot 1.2s ease-in-out infinite;
}
@keyframes dash-pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}
.dash-status-hint {
  color: #C4B5A5;
  margin-left: 4px;
}

/* ===== Error Banner ===== */
.dash-error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #FEF3F2;
  border: 1px solid #FECDCA;
  border-radius: 10px;
  font-size: 13px;
  color: #B42318;
  margin-bottom: 12px;
}
.dash-retry-btn {
  margin-left: auto;
  padding: 3px 12px;
  border: 1px solid #FECDCA;
  border-radius: 6px;
  background: #fff;
  color: #B42318;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.dash-retry-btn:hover { background: #FEF3F2; }

/* ===== Welcome ===== */
.dash-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  text-align: center;
  color: #B8A088;
}
.dash-welcome-title {
  margin: 14px 0 4px;
  font-size: 17px;
  font-weight: 600;
  color: #5C4A3A;
}
.dash-welcome-text {
  margin: 0;
  font-size: 13px;
  color: #C4B5A5;
}

/* ===== Skeleton ===== */
.dash-skel-wrap { display: flex; flex-direction: column; gap: 16px; }
.dash-card--skel { min-height: 130px; }
.dash-skel-h {
  height: 16px;
  width: 40%;
  background: linear-gradient(90deg, #F0EBE3 25%, #F8F4EF 50%, #F0EBE3 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: dash-shimmer 1.4s ease infinite;
}
.dash-skel-vspace { height: 12px; }
.dash-skel-l {
  height: 14px;
  background: linear-gradient(90deg, #F5F0E8 25%, #FDF8F2 50%, #F5F0E8 75%);
  background-size: 200% 100%;
  border-radius: 3px;
  animation: dash-shimmer 1.4s ease infinite;
  margin-bottom: 8px;
}
.w-70 { width: 70%; }
.w-90 { width: 90%; }
.w-50 { width: 50%; }
.w-40 { width: 40%; }
.dash-skel-section { display: flex; flex-direction: column; gap: 10px; }
.dash-skel-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.dash-skel-box {
  height: 50px;
  border-radius: 8px;
  background: linear-gradient(90deg, #F5F0E8 25%, #FDF8F2 50%, #F5F0E8 75%);
  background-size: 200% 100%;
  animation: dash-shimmer 1.4s ease infinite;
}
@keyframes dash-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ===== Stats Grid ===== */
.dash-stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
@media (max-width: 780px) {
  .dash-stats-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 520px) {
  .dash-stats-grid { grid-template-columns: 1fr; }
}

.dash-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 16px;
  display: flex;
  flex-direction: column;
}
.dash-card-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #5C4A3A;
  display: flex;
  align-items: center;
  gap: 6px;
}
.dash-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dash-card-body--compact {
  padding: 0;
  gap: 0;
}
.dash-card-empty {
  font-size: 12px;
  color: #C4B5A5;
  text-align: center;
  padding: 12px 0;
}

/* ===== Token Usage ===== */
.dash-token-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.dash-token-label {
  color: #8B7355;
}
.dash-token-count {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  color: #5C4A3A;
  font-weight: 600;
}
.dash-token-track {
  height: 10px;
  background: #F0EBE3;
  border-radius: 5px;
  overflow: hidden;
  margin-bottom: 4px;
}
.dash-token-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.6s ease;
  min-width: 2%;
}
.dash-token-fill--in {
  background: linear-gradient(90deg, #B388FF, #884BFF);
}
.dash-token-fill--out {
  background: linear-gradient(90deg, #884BFF, #7530FE);
}
.dash-token-total {
  text-align: right;
  font-size: 11px;
  color: #B8A088;
  margin-top: 2px;
}
.dash-token-total strong {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  color: #5C4A3A;
}

/* ===== Latency ===== */
.dash-latency-hero {
  font-size: 26px;
  font-weight: 800;
  color: #3538CD;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  line-height: 1.1;
}
.dash-latency-unit {
  font-size: 14px;
  font-weight: 600;
  color: #8B7355;
}
.dash-latency-hero-label {
  font-size: 11px;
  color: #B8A088;
  margin-bottom: 10px;
}
.dash-latency-bars {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dash-latency-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dash-latency-name {
  width: 24px;
  font-size: 10px;
  color: #B8A088;
  font-weight: 600;
  flex-shrink: 0;
}
.dash-latency-track {
  flex: 1;
  height: 8px;
  background: #F0EBE3;
  border-radius: 4px;
  overflow: hidden;
}
.dash-latency-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
  min-width: 4px;
}
.dash-latency-fill--p50 { background: linear-gradient(90deg, #12B76A, #27D17A); }
.dash-latency-fill--p95 { background: linear-gradient(90deg, #F5A623, #F7B84A); }
.dash-latency-fill--p99 { background: linear-gradient(90deg, #F04438, #F97066); }
.dash-latency-val {
  width: 38px;
  font-size: 10px;
  color: #5C4A3A;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  text-align: right;
  flex-shrink: 0;
}

/* ===== Section ===== */
.dash-section {
  margin-bottom: 16px;
}
.dash-section-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #5C4A3A;
}
.dash-empty {
  text-align: center;
  padding: 20px;
  color: #C4B5A5;
  font-size: 13px;
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 12px;
}

/* ===== Heatmap ===== */
.dash-heatmap {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 6px;
}
.dash-heatmap-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px 8px;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: background 0.3s, transform 0.15s;
  cursor: default;
}
.dash-heatmap-cell:hover {
  transform: translateY(-1px);
}
.dash-heatmap-lvl-0 { background: #F9FAFB; border-color: #F0EBE3; }
.dash-heatmap-lvl-1 { background: rgba(136, 75, 255, 0.06); border-color: rgba(136, 75, 255, 0.1); }
.dash-heatmap-lvl-2 { background: rgba(136, 75, 255, 0.14); border-color: rgba(136, 75, 255, 0.18); }
.dash-heatmap-lvl-3 { background: rgba(136, 75, 255, 0.25); border-color: rgba(136, 75, 255, 0.3); }
.dash-heatmap-lvl-4 { background: rgba(136, 75, 255, 0.40); border-color: transparent; }
.dash-heatmap-lvl-5 { background: rgba(136, 75, 255, 0.60); border-color: transparent; }
.dash-heatmap-name {
  font-size: 11px;
  font-weight: 500;
  color: #5C4A3A;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  white-space: nowrap;
}
.dash-heatmap-lvl-4 .dash-heatmap-name,
.dash-heatmap-lvl-5 .dash-heatmap-name { color: #fff; }
.dash-heatmap-count {
  font-size: 18px;
  font-weight: 700;
  color: #884BFF;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  margin-top: 2px;
}
.dash-heatmap-lvl-4 .dash-heatmap-count,
.dash-heatmap-lvl-5 .dash-heatmap-count { color: #fff; }

/* ===== Pipeline Card ===== */
.dash-pipeline-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 8px 16px;
}

/* ===== Sessions List ===== */
.dash-sessions {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 12px;
  overflow: hidden;
}
.dash-session-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.12s;
  border-bottom: 1px solid #F8F4EF;
}
.dash-session-row:last-child { border-bottom: none; }
.dash-session-row:hover { background: #FDF8F2; }
.dash-session-row--sel {
  background: rgba(136, 75, 255, 0.06) !important;
  box-shadow: inset 3px 0 0 #884BFF;
}
.dash-ss-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dash-ss-dot--active { background: #12B76A; box-shadow: 0 0 6px rgba(18,183,106,0.3); }
.dash-ss-dot--done { background: #B8A088; }
.dash-ss-dot--not_found { background: #F04438; }
.dash-ss-dot--unknown { background: #D0D5DD; }
.dash-ss-id {
  flex: 1;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  color: #5C4A3A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dash-ss-stat {
  font-size: 11px;
  color: #B8A088;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  flex-shrink: 0;
}
.dash-ss-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 8px;
  font-weight: 500;
  flex-shrink: 0;
}
.dash-ss-badge--active { background: #ECFDF3; color: #027A48; }
.dash-ss-badge--done { background: #F5F0E8; color: #8B7355; }
.dash-ss-badge--not_found { background: #FEF3F2; color: #B42318; }
.dash-ss-badge--unknown { background: #F5F0E8; color: #C4B5A5; }
.dash-ss-rm {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #C4B5A5;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  flex-shrink: 0;
}
.dash-ss-rm:hover {
  background: #FEF3F2;
  color: #F04438;
}

/* ===== Trace Card ===== */
.dash-trace-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 12px;
}
</style>
