<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** Total cost in USD */
  totalCost: { type: Number, default: 0 },
  /** Map of model name -> cost: { 'gpt-4o': 0.015, 'dall-e-3': 0.008 } */
  modelCosts: { type: Object, default: () => ({}) },
  /** Map of tool name -> cost: { 'wardrobe': 0.005, 'stylist': 0.01 } */
  toolCosts: { type: Object, default: () => ({}) },
  /** Loading state */
  loading: { type: Boolean, default: false },
})

// ===== Bar chart: cost by model =====
const modelBars = computed(() => {
  const entries = Object.entries(props.modelCosts).filter(([_, v]) => v > 0)
  if (!entries.length) return []
  const maxVal = Math.max(...entries.map(([_, v]) => v))
  const colors = ['#884BFF', '#7530FE', '#5B1FE6', '#9D6CFF', '#B388FF']
  return entries.map(([model, cost], i) => ({
    model,
    cost,
    label: model.length > 12 ? model.slice(0, 11) + '…' : model,
    pct: maxVal > 0 ? (cost / maxVal) * 100 : 0,
    display: `$${cost.toFixed(4)}`,
    color: colors[i % colors.length],
  }))
})

// ===== Pie chart: cost by tool =====
const CHART_COLORS = ['#884BFF', '#F5A623', '#12B76A', '#3538CD', '#F04438', '#8B7355', '#6B3CFF', '#D4B896']

const pieSegments = computed(() => {
  const entries = Object.entries(props.toolCosts).filter(([_, v]) => v > 0)
  if (!entries.length) return []
  const total = entries.reduce((sum, [_, v]) => sum + v, 0) || 1
  let current = 0
  return entries.map(([name, cost], i) => {
    const deg = (cost / total) * 360
    const seg = {
      name,
      cost,
      pct: ((cost / total) * 100).toFixed(1),
      startAngle: current,
      endAngle: current + deg,
      color: CHART_COLORS[i % CHART_COLORS.length],
    }
    current += deg
    return seg
  })
})

const pieGradient = computed(() => {
  return pieSegments.value
    .map((s) => `${s.color} ${s.startAngle}deg ${s.endAngle}deg`)
    .join(', ')
})

const pieEmpty = computed(() => pieSegments.value.length === 0)
</script>

<template>
  <div class="cost-chart">
    <!-- Loading overlay -->
    <div v-if="loading" class="cc-loading">
      <div class="cc-shimmer-row">
        <div class="cc-shimmer-big"></div>
      </div>
      <div class="cc-shimmer-row">
        <div class="cc-shimmer-bar"></div>
        <div class="cc-shimmer-bar"></div>
        <div class="cc-shimmer-bar"></div>
      </div>
    </div>

    <template v-else>
      <!-- Total cost (hero number) -->
      <div class="cc-total">
        <div class="cc-total-currency">USD</div>
        <div class="cc-total-amount">
          <span class="cc-dollar">$</span>{{ (totalCost || 0).toFixed(4) }}
        </div>
        <div class="cc-total-label">总消耗</div>
      </div>

      <div class="cc-sections">
        <!-- Bar chart: cost by model -->
        <div class="cc-section">
          <h4 class="cc-section-title">模型费用</h4>
          <div v-if="!modelBars.length" class="cc-empty">暂无模型费用数据</div>
          <div v-else class="cc-bar-chart">
            <div v-for="bar in modelBars" :key="bar.model" class="cc-bar-row">
              <span class="cc-bar-label" :title="bar.model">{{ bar.label }}</span>
              <div class="cc-bar-track">
                <div
                  class="cc-bar-fill"
                  :style="{ width: bar.pct + '%', background: bar.color }"
                ></div>
              </div>
              <span class="cc-bar-value">{{ bar.display }}</span>
            </div>
          </div>
        </div>

        <!-- Pie chart: cost by tool -->
        <div class="cc-section">
          <h4 class="cc-section-title">工具费用</h4>
          <div v-if="pieEmpty" class="cc-empty">暂无工具费用数据</div>
          <div v-else class="cc-pie-wrapper">
            <div
              class="cc-pie"
              :style="{ background: 'conic-gradient(' + pieGradient + ')' }"
            ></div>
            <div class="cc-legend">
              <div v-for="seg in pieSegments" :key="seg.name" class="cc-legend-item">
                <span class="cc-legend-dot" :style="{ background: seg.color }"></span>
                <span class="cc-legend-name">{{ seg.name }}</span>
                <span class="cc-legend-pct">{{ seg.pct }}%</span>
                <span class="cc-legend-cost">${{ seg.cost.toFixed(4) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cost-chart {
  position: relative;
  width: 100%;
}

/* ===== Loading shimmer ===== */
.cc-loading {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0;
}
.cc-shimmer-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cc-shimmer-big {
  height: 48px;
  width: 120px;
  border-radius: 8px;
  background: linear-gradient(90deg, #F0EBE3 25%, #F8F4EF 50%, #F0EBE3 75%);
  background-size: 200% 100%;
  animation: cc-shimmer 1.4s ease infinite;
}
.cc-shimmer-bar {
  height: 16px;
  width: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #F5F0E8 25%, #FDF8F2 50%, #F5F0E8 75%);
  background-size: 200% 100%;
  animation: cc-shimmer 1.4s ease infinite;
}
@keyframes cc-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ===== Total cost ===== */
.cc-total {
  text-align: center;
  padding: 16px 0 12px;
}
.cc-total-currency {
  font-size: 11px;
  font-weight: 600;
  color: #B8A088;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.cc-total-amount {
  font-size: 32px;
  font-weight: 800;
  color: #5C4A3A;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  line-height: 1.2;
  margin: 2px 0;
}
.cc-dollar {
  font-size: 20px;
  font-weight: 600;
  color: #B8A088;
  vertical-align: super;
}
.cc-total-label {
  font-size: 12px;
  color: #B8A088;
}

/* ===== Sections grid ===== */
.cc-sections {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 4px;
}
@media (max-width: 600px) {
  .cc-sections {
    grid-template-columns: 1fr;
  }
}
.cc-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cc-section-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #5C4A3A;
}
.cc-empty {
  font-size: 12px;
  color: #C4B5A5;
  padding: 12px 0;
  text-align: center;
}

/* ===== Bar chart ===== */
.cc-bar-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cc-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cc-bar-label {
  width: 64px;
  font-size: 11px;
  color: #8B7355;
  text-align: right;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cc-bar-track {
  flex: 1;
  height: 14px;
  background: #F0EBE3;
  border-radius: 7px;
  overflow: hidden;
}
.cc-bar-fill {
  height: 100%;
  border-radius: 7px;
  transition: width 0.6s ease;
  min-width: 4px;
}
.cc-bar-value {
  width: 58px;
  font-size: 11px;
  color: #5C4A3A;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  flex-shrink: 0;
  text-align: right;
}

/* ===== Pie chart ===== */
.cc-pie-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.cc-pie {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 2px solid #F0EBE3;
  transition: background 0.4s;
}
.cc-legend {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.cc-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #5C4A3A;
}
.cc-legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cc-legend-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cc-legend-pct {
  color: #B8A088;
  font-size: 10px;
  width: 32px;
  text-align: right;
}
.cc-legend-cost {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 10px;
  color: #8B7355;
  width: 50px;
  text-align: right;
}
</style>
