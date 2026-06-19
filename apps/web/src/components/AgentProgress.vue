<script setup>
import { computed } from 'vue'

const props = defineProps({
  steps: {
    type: Array,
    default: () => [],
  },
  collapsed: { type: Boolean, default: false },
})

const statusText = (s) => {
  if (s.status === 'done') return '完成'
  if (s.status === 'error') return '异常'
  if (s.status === 'running') return '进行中'
  return '等待'
}

const currentIndex = computed(() => {
  const idx = props.steps.findIndex((s) => s.status === 'running')
  return idx >= 0 ? idx : props.steps.length
})
</script>

<template>
  <!-- Collapsed: mini dot row -->
  <div v-if="collapsed" class="ap-mini">
    <span
      v-for="(s, i) in steps"
      :key="s.name || i"
      class="ap-mini-dot"
      :class="'ap-mini-dot--' + (s.status || 'waiting')"
    ></span>
  </div>

  <!-- Full horizontal stepper -->
  <div v-else class="ap-stepper">
    <div
      v-for="(s, i) in steps"
      :key="s.name || i"
      class="ap-step"
      :class="[
        'ap-step--' + (s.status || 'waiting'),
        { 'ap-step--active': s.status === 'running' },
        { 'ap-step--last': i === steps.length - 1 },
      ]"
    >
      <!-- Indicator circle -->
      <div class="ap-step-indicator">
        <svg v-if="s.status === 'done'" class="ap-icon ap-icon-done" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="7" fill="#12B76A"/>
          <path d="M5 8.5L7 10.5L11 6" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg v-else-if="s.status === 'error'" class="ap-icon ap-icon-error" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="7" fill="#F04438"/>
          <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <span v-else-if="s.status === 'running'" class="ap-spinner"></span>
        <span v-else class="ap-step-number">{{ i + 1 }}</span>
      </div>

      <!-- Connector line -->
      <div v-if="i < steps.length - 1" class="ap-connector">
        <div class="ap-connector-fill" :class="{ 'ap-connector-fill--done': s.status === 'done' }"></div>
      </div>

      <!-- Label & meta below the circle -->
      <div class="ap-step-body">
        <div class="ap-step-label">{{ s.label || s.name }}</div>
        <div class="ap-step-meta">
          <span v-if="s.duration" class="ap-step-duration">{{ s.duration.toFixed(1) }}s</span>
          <span v-else class="ap-step-status-text">{{ statusText(s) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ===== Mini collapsed mode ===== */
.ap-mini {
  display: flex;
  gap: 5px;
  align-items: center;
}
.ap-mini-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #D0D5DD;
  transition: background 0.3s;
}
.ap-mini-dot--running {
  background: #884BFF;
  animation: ap-pulse 0.8s ease-in-out infinite;
}
.ap-mini-dot--done { background: #12B76A; }
.ap-mini-dot--error { background: #F04438; }
@keyframes ap-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

/* ===== Full horizontal stepper ===== */
.ap-stepper {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 8px 0;
  width: 100%;
}

.ap-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
  min-width: 0;
}

/* Indicator */
.ap-step-indicator {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #F0EBE3;
  color: #B8A088;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.4s, color 0.4s, transform 0.3s, box-shadow 0.3s;
  position: relative;
  z-index: 1;
}
.ap-step--waiting .ap-step-indicator {
  background: #F5F0E8;
  color: #C4B5A5;
}
.ap-step--running .ap-step-indicator {
  background: rgba(136, 75, 255, 0.15);
  color: #884BFF;
  box-shadow: 0 0 0 4px rgba(136, 75, 255, 0.12);
}
.ap-step--done .ap-step-indicator {
  background: #ECFDF3;
}
.ap-step--error .ap-step-indicator {
  background: #FEF3F2;
}

.ap-step-number {
  line-height: 1;
}
.ap-icon {
  width: 32px;
  height: 32px;
  display: block;
}

/* Running spinner */
.ap-spinner {
  width: 16px;
  height: 16px;
  border: 2.5px solid #884BFF;
  border-top-color: transparent;
  border-radius: 50%;
  animation: ap-spin 0.7s linear infinite;
}
@keyframes ap-spin { to { transform: rotate(360deg); } }

/* Active step pulse ring */
.ap-step--active .ap-step-indicator::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid rgba(136, 75, 255, 0.25);
  animation: ap-ring 1.2s ease-out infinite;
}
@keyframes ap-ring {
  0% { transform: scale(0.85); opacity: 1; }
  100% { transform: scale(1.3); opacity: 0; }
}

/* Connector line */
.ap-connector {
  position: absolute;
  top: 15px;
  left: calc(50% + 20px);
  right: calc(-50% + 20px);
  height: 3px;
  background: #F0EBE3;
  border-radius: 2px;
  overflow: hidden;
  z-index: 0;
}
.ap-connector-fill {
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, #884BFF, #12B76A);
  border-radius: 2px;
  transition: width 0.6s ease;
}
.ap-connector-fill--done {
  width: 100%;
}

/* Step body (label + meta) */
.ap-step-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 8px;
  text-align: center;
  width: 100%;
  padding: 0 4px;
}
.ap-step-label {
  font-size: 12px;
  font-weight: 600;
  color: #5C4A3A;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  transition: color 0.3s;
}
.ap-step--waiting .ap-step-label { color: #B8A088; }
.ap-step--running .ap-step-label { color: #884BFF; }
.ap-step--done .ap-step-label { color: #027A48; }
.ap-step--error .ap-step-label { color: #B42318; }

.ap-step-meta {
  margin-top: 2px;
  font-size: 11px;
  color: #B8A088;
  transition: color 0.3s;
}
.ap-step-duration {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  color: #8B7355;
}
.ap-step-status-text {
  font-size: 11px;
}
.ap-step--running .ap-step-status-text { color: #884BFF; }

/* Last step doesn't flex-grow the connector gap */
.ap-step--last {
  flex: 0 0 auto;
}

/* Responsive: stack label above/below on very narrow */
@media (max-width: 480px) {
  .ap-step-label { font-size: 10px; }
  .ap-step-indicator { width: 26px; height: 26px; }
  .ap-icon { width: 26px; height: 26px; }
  .ap-spinner { width: 12px; height: 12px; }
  .ap-connector { top: 12px; }
}
</style>
