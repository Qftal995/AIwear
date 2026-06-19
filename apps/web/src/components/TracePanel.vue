<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  /**
   * Array of session objects:
   * { id: string, steps: [{name, status, duration, tokens, latency_ms, output_preview}], totalTokens: number, totalCost: number }
   */
  sessions: { type: Array, default: () => [] },
  /** Whether data is currently loading */
  loading: { type: Boolean, default: false },
})

const expandedSessions = ref(new Set())
const expandedSteps = ref(new Set())

const toggleSession = (id) => {
  const next = new Set(expandedSessions.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedSessions.value = next
}

const toggleStep = (key) => {
  const next = new Set(expandedSteps.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedSteps.value = next
}

const statusIcon = (s) => {
  if (s === 'done') return '✓'
  if (s === 'error') return '✗'
  if (s === 'running') return '◉'
  return '○'
}

const stepCounts = computed(() => ({
  total: props.sessions.reduce((sum, s) => sum + (s.steps?.length || 0), 0),
  done: props.sessions.reduce((sum, s) => sum + (s.steps?.filter((st) => st.status === 'done').length || 0), 0),
  running: props.sessions.reduce((sum, s) => sum + (s.steps?.filter((st) => st.status === 'running').length || 0), 0),
  error: props.sessions.reduce((sum, s) => sum + (s.steps?.filter((st) => st.status === 'error').length || 0), 0),
}))
</script>

<template>
  <div class="trace-panel">
    <!-- Loading skeleton -->
    <div v-if="loading" class="tp-loading">
      <div v-for="n in 3" :key="n" class="tp-skeleton">
        <div class="tp-skel-head"></div>
        <div class="tp-skel-steps">
          <div v-for="m in 4" :key="m" class="tp-skel-step"></div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!sessions.length" class="tp-empty">
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
        <circle cx="20" cy="20" r="16" stroke="#D0D5DD" stroke-width="1.5" fill="none" stroke-dasharray="4 4"/>
        <path d="M20 12v8l5 3" stroke="#D0D5DD" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <p class="tp-empty-text">尚无追踪数据</p>
      <p class="tp-empty-hint">开始一次对话或输入 Session ID 以查看 Agent 执行追踪</p>
    </div>

    <!-- Sessions -->
    <div v-else class="tp-sessions">
      <div class="tp-summary">
        <span class="tp-summary-item">共 {{ sessions.length }} 会话</span>
        <span class="tp-summary-item">{{ stepCounts.total }} 步骤</span>
        <span v-if="stepCounts.done" class="tp-summary-item tp-summary-done">{{ stepCounts.done }} 完成</span>
        <span v-if="stepCounts.running" class="tp-summary-item tp-summary-running">{{ stepCounts.running }} 运行中</span>
        <span v-if="stepCounts.error" class="tp-summary-item tp-summary-error">{{ stepCounts.error }} 异常</span>
      </div>

      <div
        v-for="session in sessions"
        :key="session.id"
        class="tp-session"
        :class="{ 'tp-session--expanded': expandedSessions.has(session.id) }"
      >
        <!-- Session header (collapsible) -->
        <button class="tp-session-head" @click="toggleSession(session.id)">
          <span class="tp-session-arrow" :class="{ 'tp-arrow--open': expandedSessions.has(session.id) }">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><path d="M3 1l4 4-4 4" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>
          </span>
          <span class="tp-session-id">{{ session.id }}</span>
          <span v-if="session.totalTokens" class="tp-session-stat">{{ session.totalTokens.toLocaleString() }} tokens</span>
          <span v-if="session.totalCost" class="tp-session-stat">${{ session.totalCost.toFixed(4) }}</span>
          <span class="tp-session-badge" :class="'tp-badge--' + (session.status || 'unknown')">
            {{ session.status === 'done' ? '完成' : session.status === 'running' ? '活跃' : '未知' }}
          </span>
        </button>

        <!-- Session body (steps timeline) -->
        <div v-if="expandedSessions.has(session.id)" class="tp-session-body">
          <div
            v-for="(step, si) in session.steps"
            :key="si"
            class="tp-step"
            :class="'tp-step--' + (step.status || 'waiting')"
          >
            <button class="tp-step-head" @click="toggleStep(session.id + '-' + si)">
              <span class="tp-step-dot" v-html="statusIcon(step.status || 'waiting')"></span>
              <span class="tp-step-name">{{ step.label || step.name }}</span>
              <span v-if="step.duration" class="tp-step-duration">{{ step.duration.toFixed(1) }}s</span>
              <span class="tp-step-expand-icon">
                <svg
                  width="8" height="8" viewBox="0 0 8 8" fill="currentColor"
                  :style="{ transform: expandedSteps.has(session.id + '-' + si) ? 'rotate(90deg)' : 'rotate(0deg)' }"
                >
                  <path d="M2 1l3 3-3 3" stroke="currentColor" stroke-width="1.2" fill="none"/>
                </svg>
              </span>
            </button>

            <!-- Expanded details -->
            <div v-if="expandedSteps.has(session.id + '-' + si)" class="tp-step-detail">
              <div class="tp-detail-grid">
                <div v-if="step.tokens" class="tp-detail-item">
                  <span class="tp-detail-label">Tokens</span>
                  <span class="tp-detail-value">{{ step.tokens.toLocaleString() }}</span>
                </div>
                <div v-if="step.latency_ms" class="tp-detail-item">
                  <span class="tp-detail-label">延迟</span>
                  <span class="tp-detail-value">{{ step.latency_ms }}ms</span>
                </div>
                <div v-if="step.status" class="tp-detail-item">
                  <span class="tp-detail-label">状态</span>
                  <span class="tp-detail-value" :class="'tp-detail-value--' + step.status">
                    {{ step.status === 'done' ? '完成' : step.status === 'error' ? '异常' : step.status === 'running' ? '运行中' : '等待' }}
                  </span>
                </div>
              </div>
              <div v-if="step.output_preview" class="tp-detail-output">
                <span class="tp-detail-label">输出预览</span>
                <p class="tp-detail-text">{{ step.output_preview }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ===== Trace Panel ===== */
.trace-panel {
  width: 100%;
}

/* ===== Loading Skeleton ===== */
.tp-loading {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.tp-skeleton {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tp-skel-head {
  height: 18px;
  width: 55%;
  background: linear-gradient(90deg, #F0EBE3 25%, #F8F4EF 50%, #F0EBE3 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: tp-shimmer 1.4s ease infinite;
}
.tp-skel-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 8px;
}
.tp-skel-step {
  height: 14px;
  width: 80%;
  background: linear-gradient(90deg, #F5F0E8 25%, #FDF8F2 50%, #F5F0E8 75%);
  background-size: 200% 100%;
  border-radius: 3px;
  animation: tp-shimmer 1.4s ease infinite;
}
@keyframes tp-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ===== Empty State ===== */
.tp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
  color: #B8A088;
}
.tp-empty-text {
  margin: 12px 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #8B7355;
}
.tp-empty-hint {
  margin: 0;
  font-size: 12px;
  color: #C4B5A5;
  max-width: 280px;
}

/* ===== Summary Bar ===== */
.tp-summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding: 0 2px;
}
.tp-summary-item {
  font-size: 12px;
  color: #8B7355;
  background: #FDF8F2;
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid #F0EBE3;
}
.tp-summary-done { color: #027A48; background: #ECFDF3; border-color: #A6F4C5; }
.tp-summary-running { color: #884BFF; background: rgba(136,75,255,0.08); border-color: rgba(136,75,255,0.2); }
.tp-summary-error { color: #B42318; background: #FEF3F2; border-color: #FECDCA; }

/* ===== Session ===== */
.tp-sessions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tp-session {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}
.tp-session:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.tp-session-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 12px 14px;
  border: none;
  background: #FDF8F2;
  cursor: pointer;
  font-size: 13px;
  color: #5C4A3A;
  text-align: left;
  transition: background 0.15s;
}
.tp-session-head:hover {
  background: #F5E6D3;
}
.tp-session-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  color: #B8A088;
  transition: transform 0.2s;
}
.tp-arrow--open {
  transform: rotate(90deg);
}
.tp-session-id {
  flex: 1;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  color: #8B7355;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tp-session-stat {
  font-size: 11px;
  color: #B8A088;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  flex-shrink: 0;
}
.tp-session-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  flex-shrink: 0;
}
.tp-badge--done { background: #ECFDF3; color: #027A48; }
.tp-badge--running { background: rgba(136,75,255,0.1); color: #884BFF; }
.tp-badge--unknown { background: #F5F0E8; color: #B8A088; }

/* ===== Session Body / Steps ===== */
.tp-session-body {
  border-top: 1px solid #F0EBE3;
}
.tp-step {
  border-bottom: 1px solid #F8F4EF;
}
.tp-step:last-child {
  border-bottom: none;
}
.tp-step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px 10px 18px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #5C4A3A;
  text-align: left;
  transition: background 0.15s;
}
.tp-step-head:hover {
  background: #FDF8F2;
}
.tp-step-dot {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  border-radius: 50%;
}
.tp-step--done .tp-step-dot { background: #ECFDF3; color: #12B76A; }
.tp-step--error .tp-step-dot { background: #FEF3F2; color: #F04438; }
.tp-step--running .tp-step-dot { background: rgba(136,75,255,0.12); color: #884BFF; }
.tp-step--waiting .tp-step-dot { background: #F5F0E8; color: #C4B5A5; }
.tp-step-name {
  flex: 1;
  font-weight: 500;
}
.tp-step--done .tp-step-name { color: #027A48; }
.tp-step--error .tp-step-name { color: #B42318; }
.tp-step--running .tp-step-name { color: #884BFF; }
.tp-step-duration {
  font-size: 11px;
  color: #B8A088;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.tp-step-expand-icon {
  display: flex;
  align-items: center;
  color: #C4B5A5;
  transition: color 0.15s;
}
.tp-step-head:hover .tp-step-expand-icon {
  color: #8B7355;
}

/* ===== Expanded Step Detail ===== */
.tp-step-detail {
  padding: 0 14px 12px 46px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tp-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 6px;
}
.tp-detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 10px;
  background: #FDF8F2;
  border-radius: 8px;
}
.tp-detail-label {
  font-size: 10px;
  color: #B8A088;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.tp-detail-value {
  font-size: 13px;
  font-weight: 600;
  color: #5C4A3A;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.tp-detail-value--done { color: #027A48; }
.tp-detail-value--error { color: #B42318; }
.tp-detail-value--running { color: #884BFF; }

.tp-detail-output {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tp-detail-text {
  margin: 0;
  font-size: 12px;
  color: #667085;
  line-height: 1.5;
  background: #F9FAFB;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #F0EBE3;
  max-height: 80px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
