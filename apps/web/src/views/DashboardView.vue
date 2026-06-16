<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import AgentProgress from '../components/AgentProgress.vue'

const sessionStatus = ref('idle')
const sessionId = ref('')
const executedSteps = ref(0)
const totalSteps = ref(5)
const tokensRound = ref(0)
const tokensTotal = ref(45780)
const estimatedCost = ref('0.00')

const agentSteps = ref([
  { name: '衣橱检索', label: '衣橱检索', status: 'waiting', duration: 0, detail: '' },
  { name: '搭配推荐', label: '搭配推荐', status: 'waiting', duration: 0, detail: '' },
  { name: '图片生成', label: '图片生成', status: 'waiting', duration: 0, detail: '' },
  { name: '安全审核', label: '安全审核', status: 'waiting', duration: 0, detail: '' },
  { name: '文案生成', label: '文案生成', status: 'waiting', duration: 0, detail: '' },
])

const historySessions = ref([
  { id: 'def456', time: '06-16 14:30', steps: 4, tokens: 1234, status: 'done' },
  { id: 'ghi789', time: '06-16 10:15', steps: 5, tokens: 2456, status: 'done' },
  { id: 'jkl012', time: '06-15 18:42', steps: 3, tokens: 890, status: 'error' },
])

const canPause = ref(false)
const canResume = ref(false)
const canStop = ref(false)

const startDemo = () => {
  sessionId.value = 'session_' + Date.now().toString(36)
  sessionStatus.value = 'running'
  executedSteps.value = 0
  tokensRound.value = 0
  canPause.value = true
  canStop.value = true
  canResume.value = false
  agentSteps.value.forEach((s) => { s.status = 'waiting'; s.duration = 0; s.detail = '' })
  runDemoStep(0)
}

let demoInterval = null

const runDemoStep = (idx) => {
  if (idx >= agentSteps.value.length || sessionStatus.value !== 'running') return
  agentSteps.value[idx].status = 'running'
  const start = Date.now()
  demoInterval = setTimeout(() => {
    if (sessionStatus.value !== 'running') return
    agentSteps.value[idx].status = 'done'
    agentSteps.value[idx].duration = ((Date.now() - start) / 1000).toFixed(1)
    executedSteps.value = idx + 1
    tokensRound.value += Math.floor(Math.random() * 400) + 100
    if (idx + 1 < agentSteps.value.length) {
      runDemoStep(idx + 1)
    } else {
      sessionStatus.value = 'done'
      canPause.value = false
      canResume.value = false
      canStop.value = false
      historySessions.value.unshift({
        id: sessionId.value,
        time: new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }),
        steps: executedSteps.value,
        tokens: tokensRound.value,
        status: 'done',
      })
    }
  }, 1500 + Math.random() * 1000)
}

const pauseSession = () => {
  sessionStatus.value = 'paused'
  canPause.value = false
  canResume.value = true
  clearTimeout(demoInterval)
}

const resumeSession = () => {
  sessionStatus.value = 'running'
  canPause.value = true
  canResume.value = false
  const idx = agentSteps.value.findIndex((s) => s.status === 'running' || s.status === 'waiting')
  if (idx >= 0) runDemoStep(idx)
}

const stopSession = () => {
  sessionStatus.value = 'idle'
  canPause.value = false
  canResume.value = false
  canStop.value = false
  clearTimeout(demoInterval)
}

onUnmounted(() => clearTimeout(demoInterval))

const statusText = (s) => {
  const map = { idle: '未启动', running: '进行中', paused: '已暂停', done: '已完成' }
  return map[s] || s
}
const statusClass = (s) => 'status-' + s
</script>

<template>
  <div class="dashboard-page">
    <h2 class="page-title">控制面板</h2>

    <div class="dash-cards">
      <div class="dash-card">
        <h3 class="dash-card-title">当前会话状态</h3>
        <div class="dash-card-body">
          <div class="dash-row">
            <span class="dash-label">会话</span>
            <span class="dash-value">{{ sessionId || '---' }}</span>
          </div>
          <div class="dash-row">
            <span class="dash-label">状态</span>
            <span class="dash-badge" :class="statusClass(sessionStatus)">{{ statusText(sessionStatus) }}</span>
          </div>
          <div class="dash-row">
            <span class="dash-label">进度</span>
            <span class="dash-value">{{ executedSteps }} / {{ totalSteps }} 步</span>
          </div>
          <div class="dash-progress-bar">
            <div
              class="dash-progress-fill"
              :style="{ width: (executedSteps / totalSteps * 100) + '%' }"
            ></div>
          </div>
        </div>
        <div class="dash-card-actions">
          <button v-if="!sessionStatus || sessionStatus === 'idle' || sessionStatus === 'done'" class="dash-btn dash-btn-start" @click="startDemo">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            开始
          </button>
          <button v-if="canPause" class="dash-btn dash-btn-pause" @click="pauseSession">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
            暂停
          </button>
          <button v-if="canResume" class="dash-btn dash-btn-resume" @click="resumeSession">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            继续
          </button>
          <button v-if="canStop" class="dash-btn dash-btn-stop" @click="stopSession">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
            终止
          </button>
        </div>
      </div>

      <div class="dash-card">
        <h3 class="dash-card-title">Token 消耗统计</h3>
        <div class="dash-card-body">
          <div class="dash-row">
            <span class="dash-label">本轮消耗</span>
            <span class="dash-value dash-value-mono">{{ tokensRound.toLocaleString() }} tokens</span>
          </div>
          <div class="dash-row">
            <span class="dash-label">累计消耗</span>
            <span class="dash-value dash-value-mono">{{ tokensTotal.toLocaleString() }} tokens</span>
          </div>
          <div class="dash-row">
            <span class="dash-label">预估费用</span>
            <span class="dash-value">¥ {{ estimatedCost }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="dash-section">
      <h3 class="dash-section-title">Agent 工作进度</h3>
      <div class="dash-agent-list">
        <AgentProgress :steps="agentSteps" :collapsed="false" />
      </div>
    </div>

    <div class="dash-section">
      <h3 class="dash-section-title">历史会话</h3>
      <div v-if="!historySessions.length" class="dash-empty">暂无历史会话</div>
      <div v-else class="dash-history-table">
        <div class="dht-header">
          <span class="dht-col dht-col-id">会话 ID</span>
          <span class="dht-col dht-col-time">时间</span>
          <span class="dht-col dht-col-steps">步数</span>
          <span class="dht-col dht-col-tokens">Tokens</span>
          <span class="dht-col dht-col-status">状态</span>
        </div>
        <div v-for="h in historySessions" :key="h.id" class="dht-row">
          <span class="dht-col dht-col-id">{{ h.id }}</span>
          <span class="dht-col dht-col-time">{{ h.time }}</span>
          <span class="dht-col dht-col-steps">{{ h.steps }} 步</span>
          <span class="dht-col dht-col-tokens">{{ h.tokens.toLocaleString() }}</span>
          <span class="dht-col dht-col-status">
            <span class="dash-badge-sm" :class="h.status === 'done' ? 'badge-done' : 'badge-error'">
              {{ h.status === 'done' ? '完成' : '异常' }}
            </span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-page {
  max-width: 880px;
  margin: 0 auto;
}

/* 顶部双卡片 */
.dash-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-top: 12px;
}
@media (max-width: 640px) {
  .dash-cards { grid-template-columns: 1fr; }
}
.dash-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
}
.dash-card-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: #5C4A3A;
}
.dash-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}
.dash-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dash-label {
  font-size: 13px;
  color: #8B7355;
}
.dash-value {
  font-size: 13px;
  color: #5C4A3A;
  font-weight: 500;
}
.dash-value-mono {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.dash-badge {
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.status-idle { background: #F5F0E8; color: #B8A088; }
.status-running { background: #E8F0FE; color: #3538CD; }
.status-paused { background: #FEF9E7; color: #B8860B; }
.status-done { background: #ECFDF3; color: #027A48; }
.dash-badge-sm {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}
.badge-done { background: #ECFDF3; color: #027A48; }
.badge-error { background: #FEF3F2; color: #B42318; }

.dash-progress-bar {
  height: 4px;
  background: #F0EBE3;
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}
.dash-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #884BFF, #7530FE);
  border-radius: 2px;
  transition: width 0.5s ease;
}

.dash-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #F0EBE3;
}
.dash-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s;
}
.dash-btn:hover { opacity: 0.88; }
.dash-btn-start { background: #12B76A; color: #fff; }
.dash-btn-pause { background: #F5A623; color: #fff; }
.dash-btn-resume { background: #3538CD; color: #fff; }
.dash-btn-stop { background: #F04438; color: #fff; }

/* Agent 进度区域 */
.dash-section {
  margin-top: 20px;
}
.dash-section-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: #5C4A3A;
}
.dash-agent-list {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 4px;
}
.dash-empty {
  padding: 32px;
  text-align: center;
  color: #B8A088;
  font-size: 13px;
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
}

/* 历史会话表格 */
.dash-history-table {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  overflow: hidden;
}
.dht-header {
  display: grid;
  grid-template-columns: 1.5fr 1fr 0.6fr 1fr 0.8fr;
  padding: 10px 16px;
  background: #FDF8F2;
  border-bottom: 1px solid #F0EBE3;
  font-size: 12px;
  color: #8B7355;
  font-weight: 600;
}
.dht-row {
  display: grid;
  grid-template-columns: 1.5fr 1fr 0.6fr 1fr 0.8fr;
  padding: 10px 16px;
  border-bottom: 1px solid #F8F4EF;
  font-size: 13px;
  color: #5C4A3A;
  transition: background 0.15s;
}
.dht-row:last-child { border-bottom: none; }
.dht-row:hover { background: #FDF8F2; }
.dht-col-id { font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; font-size: 12px; }
</style>
