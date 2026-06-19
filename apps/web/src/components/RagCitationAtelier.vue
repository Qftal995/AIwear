<script setup>
import { computed } from 'vue'

const props = defineProps({
  results: { type: Array, default: () => [] },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'select'])

const scorePercent = (score) => Math.round((score || 0) * 100)

const scoreLevel = (score) => {
  const p = scorePercent(score)
  if (p >= 80) return 'high'
  if (p >= 50) return 'mid'
  return 'low'
}

const levelLabel = (level) => ({ high: '高度相关', mid: '部分相关', low: '一般参考' })[level] || ''

const sorted = computed(() => [...props.results].sort((a, b) => (b.score || 0) - (a.score || 0)))
</script>

<template>
  <Teleport to="body">
    <Transition name="rag-slide">
      <div v-if="visible" class="rag-panel">
        <div class="rag-panel-head">
          <div class="rag-panel-head-left">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#884BFF" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
            <span class="rag-panel-title">搭配笔记</span>
            <span class="rag-panel-count">{{ results.length }} 条引用</span>
          </div>
          <button class="rag-panel-close" @click="emit('close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div v-if="!results.length" class="rag-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#D0D5DD" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
          <p class="rag-empty-text">暂无知识引用</p>
        </div>

        <div v-else class="rag-list">
          <div
            v-for="(item, idx) in sorted"
            :key="idx"
            class="rag-item"
            @click="emit('select', item)"
          >
            <div class="rag-item-head">
              <span class="rag-item-num">{{ idx + 1 }}</span>
              <span class="rag-item-title">{{ item.citation?.title || '未命名文档' }}</span>
              <span
                class="rag-item-level"
                :class="'rag-level--' + scoreLevel(item.score)"
              >
                <span class="rag-level-dot"></span>
                {{ levelLabel(scoreLevel(item.score)) }}
              </span>
            </div>

            <div class="rag-item-score-bar">
              <div
                class="rag-item-score-fill"
                :class="'rag-score-fill--' + scoreLevel(item.score)"
                :style="{ width: scorePercent(item.score) + '%' }"
              ></div>
            </div>
            <div class="rag-item-score-num">{{ scorePercent(item.score) }}%</div>

            <p class="rag-item-content">{{ item.content }}</p>

            <div class="rag-item-meta">
              <span v-if="item.citation?.file" class="rag-meta-tag">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                {{ item.citation.file }}
              </span>
              <span v-if="item.citation?.section" class="rag-meta-tag">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                # {{ item.citation.section }}
              </span>
              <span v-if="item.citation?.chunkId" class="rag-meta-tag rag-meta-tag--id">
                {{ item.citation.chunkId }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ===== Panel ===== */
.rag-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  max-width: 90vw;
  background: #FDF8F2;
  border-left: 1px solid #E8D5C0;
  box-shadow: -8px 0 40px rgba(16, 24, 40, 0.08);
  display: flex;
  flex-direction: column;
  z-index: 999;
}

.rag-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #F0EBE3;
  flex-shrink: 0;
}
.rag-panel-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rag-panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #5C4A3A;
}
.rag-panel-count {
  font-size: 11px;
  color: #B8A088;
  background: #fff;
  padding: 2px 10px;
  border-radius: 10px;
  border: 1px solid #F0EBE3;
}
.rag-panel-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #B8A088;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rag-panel-close:hover { background: #F5E6D3; color: #5C4A3A; }

/* ===== Empty ===== */
.rag-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #C4B5A5;
  gap: 8px;
}
.rag-empty-text { margin: 0; font-size: 13px; }

/* ===== List ===== */
.rag-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rag-item {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s, transform 0.15s;
}
.rag-item:hover {
  box-shadow: 0 3px 14px rgba(16, 24, 40, 0.06);
  border-color: rgba(136, 75, 255, 0.15);
  transform: translateY(-1px);
}

.rag-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.rag-item-num {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: rgba(136, 75, 255, 0.1);
  color: #884BFF;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.rag-item-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #5C4A3A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rag-item-level {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 8px;
  flex-shrink: 0;
}
.rag-level-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.rag-level--high { background: #ECFDF3; color: #027A48; }
.rag-level--high .rag-level-dot { background: #12B76A; }
.rag-level--mid { background: #FEF7E6; color: #B54708; }
.rag-level--mid .rag-level-dot { background: #F5A623; }
.rag-level--low { background: #F5F0E8; color: #8B7355; }
.rag-level--low .rag-level-dot { background: #B8A088; }

.rag-item-score-bar {
  height: 4px;
  background: #F0EBE3;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 4px;
}
.rag-item-score-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
}
.rag-score-fill--high { background: linear-gradient(90deg, #12B76A, #27D17A); }
.rag-score-fill--mid { background: linear-gradient(90deg, #F5A623, #FDB022); }
.rag-score-fill--low { background: linear-gradient(90deg, #B8A088, #D4B896); }
.rag-item-score-num {
  font-size: 11px;
  color: #B8A088;
  text-align: right;
  margin-bottom: 8px;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}

.rag-item-content {
  margin: 0 0 10px;
  font-size: 12px;
  color: #5C4A3A;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.rag-item-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.rag-meta-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: #FDF8F2;
  border: 1px solid #F0EBE3;
  border-radius: 6px;
  font-size: 10px;
  color: #8B7355;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.rag-meta-tag--id {
  color: #884BFF;
  border-color: rgba(136, 75, 255, 0.15);
  background: rgba(136, 75, 255, 0.04);
}

/* ===== Transition ===== */
.rag-slide-enter-active { transition: transform 0.3s ease, opacity 0.3s ease; }
.rag-slide-leave-active { transition: transform 0.25s ease, opacity 0.25s ease; }
.rag-slide-enter-from { transform: translateX(100%); opacity: 0; }
.rag-slide-leave-to { transform: translateX(100%); opacity: 0; }
</style>
