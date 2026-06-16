<script setup>
defineProps({
  steps: { type: Array, default: () => [] },
  collapsed: { type: Boolean, default: false },
})

const statusIcon = (status) => {
  if (status === 'done') return '&#10003;'
  if (status === 'error') return '&#10007;'
  if (status === 'running') return ''
  return '&#9711;'
}
</script>

<template>
  <div class="agent-progress" :class="{ collapsed }">
    <div class="ap-list">
      <div
        v-for="(s, i) in steps"
        :key="i"
        class="ap-step"
        :class="'ap-step--' + (s.status || 'waiting')"
      >
        <span class="ap-step-dot">
          <span v-if="s.status === 'running'" class="ap-spinner"></span>
          <span v-else v-html="statusIcon(s.status)"></span>
        </span>
        <span v-if="!collapsed" class="ap-step-label">{{ s.label || s.name }}</span>
        <span v-if="!collapsed && s.duration" class="ap-step-time">{{ s.duration }}s</span>
        <span
          v-if="!collapsed"
          class="ap-step-bar"
          :style="{ width: (s.progress || (s.status === 'done' ? 100 : s.status === 'running' ? 50 : 0)) + '%' }"
        ></span>
      </div>
    </div>
    <div v-if="collapsed && steps.length" class="ap-mini-text">
      <template v-for="(s, i) in steps" :key="i">
        <span class="ap-mini-dot" :class="'ap-mini-dot--' + (s.status || 'waiting')"></span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.agent-progress {
  padding: 12px 16px;
  background: #F9FAFB;
  border-radius: 10px;
  border: 1px solid #EAECF0;
}
.agent-progress.collapsed {
  padding: 6px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ap-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.collapsed .ap-list {
  display: none;
}

.ap-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #667085;
  position: relative;
  padding: 4px 0;
}
.ap-step--running { color: #3538CD; font-weight: 500; }
.ap-step--done { color: #027A48; }
.ap-step--error { color: #B42318; }
.ap-step--waiting { color: #98A2B3; }

.ap-step-dot {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  border-radius: 50%;
  background: #EAECF0;
}
.ap-step--running .ap-step-dot { background: #3538CD1A; color: #3538CD; }
.ap-step--done .ap-step-dot { background: #ECFDF3; color: #027A48; }
.ap-step--error .ap-step-dot { background: #FEF3F2; color: #B42318; }

.ap-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid #3538CD;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: block;
}
@keyframes spin { to { transform: rotate(360deg); } }

.ap-step-label { flex: 1; }
.ap-step-time { font-size: 11px; color: #98A2B3; }
.ap-step-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  background: #3538CD;
  border-radius: 1px;
  transition: width 0.5s ease;
}
.ap-step--done .ap-step-bar { background: #12B76A; }
.ap-step--error .ap-step-bar { background: #F04438; }

.ap-mini-text { display: flex; gap: 4px; align-items: center; }
.ap-mini-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #98A2B3;
}
.ap-mini-dot--running { background: #3538CD; animation: pulse 0.8s ease-in-out infinite; }
.ap-mini-dot--done { background: #12B76A; }
.ap-mini-dot--error { background: #F04438; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
