<script setup>
import { ref, watch } from 'vue'
import { resumeChat } from '../services/api'

const props = defineProps({
  visible: { type: Boolean, default: false },
  sessionId: { type: String, default: '' },
  question: { type: String, default: '即将生成试穿效果图，是否确认继续？' },
  previewUrl: { type: String, default: '' },
})

const emit = defineEmits(['confirm', 'modify', 'cancel', 'done'])

const state = ref('idle') // idle | confirming | confirmed | error
const errorMsg = ref('')

watch(() => props.visible, (v) => {
  if (v) { state.value = 'idle'; errorMsg.value = '' }
})

const handleConfirm = async () => {
  state.value = 'confirming'
  try {
    const res = await resumeChat(props.sessionId, '确认生成')
    const body = res?.data?.data || res?.data || {}
    state.value = 'confirmed'
    emit('confirm', body)
    setTimeout(() => emit('done', body), 600)
  } catch (e) {
    state.value = 'error'
    errorMsg.value = e?.message || '操作失败'
  }
}

const handleModify = async () => {
  try {
    await resumeChat(props.sessionId, '修改搭配需求')
  } catch (e) { console.error('HITL modify resume failed:', e) }
  emit('modify')
}

const handleCancel = async () => {
  try {
    await resumeChat(props.sessionId, '取消')
  } catch (e) { console.error('HITL cancel resume failed:', e) }
  emit('cancel')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="hitl-fade">
      <div v-if="visible" class="hitl-overlay" @click.self="handleCancel">
        <div class="hitl-dialog">
          <!-- Header -->
          <div class="hitl-header">
            <div class="hitl-header-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#884BFF" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>
            </div>
            <div class="hitl-header-text">
              <h3 class="hitl-title">搭配确认</h3>
              <p class="hitl-subtitle">AI 即将为你生成试穿效果图</p>
            </div>
          </div>

          <!-- Preview Area -->
          <div class="hitl-preview">
            <div v-if="previewUrl" class="hitl-preview-img-wrap">
              <img :src="previewUrl" alt="搭配预览" class="hitl-preview-img" />
            </div>
            <div v-else class="hitl-preview-placeholder">
              <div class="hitl-preview-silhouette">
                <svg width="48" height="80" viewBox="0 0 48 80" fill="none">
                  <ellipse cx="24" cy="12" rx="10" ry="10" stroke="#D4B896" stroke-width="1.2" fill="none"/>
                  <path d="M14 32c0-6 4-12 10-12s10 6 10 12v12c0 12-7 30-10 36-3-6-10-24-10-36V32z" stroke="#D4B896" stroke-width="1.2" fill="none"/>
                  <path d="M4 52c2-6 10-6 12-4M44 52c-2-6-10-6-12-4" stroke="#D4B896" stroke-width="1" fill="none"/>
                </svg>
              </div>
              <p class="hitl-preview-hint">搭配效果生成预览区</p>
            </div>
            <div class="hitl-question">{{ question }}</div>
          </div>

          <!-- Error -->
          <div v-if="state === 'error'" class="hitl-error">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#F04438" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ errorMsg }}
          </div>

          <!-- Success -->
          <div v-if="state === 'confirmed'" class="hitl-success">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#12B76A" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            已确认，正在生成...
          </div>

          <!-- Actions -->
          <div class="hitl-actions">
            <button
              class="hitl-btn hitl-btn--primary"
              :disabled="state === 'confirming' || state === 'confirmed'"
              @click="handleConfirm"
            >
              <svg v-if="state === 'confirming'" class="hitl-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6"/><path d="M2 11.5a10 10 0 0118.8-4.2M22 12.5a10 10 0 01-18.8 4.2"/></svg>
              {{ state === 'confirmed' ? '已确认' : state === 'confirming' ? '确认中...' : '确认生成' }}
            </button>
            <button
              class="hitl-btn hitl-btn--secondary"
              :disabled="state === 'confirming' || state === 'confirmed'"
              @click="handleModify"
            >
              修改搭配需求
            </button>
            <button
              class="hitl-btn hitl-btn--ghost"
              :disabled="state === 'confirming'"
              @click="handleCancel"
            >
              取消
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ===== Overlay ===== */
.hitl-overlay {
  position: fixed;
  inset: 0;
  background: rgba(92, 74, 58, 0.45);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1001;
}

/* ===== Dialog ===== */
.hitl-dialog {
  width: 420px;
  max-width: 92vw;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 24px 80px rgba(16, 24, 40, 0.18);
  overflow: hidden;
}

/* ===== Header ===== */
.hitl-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px 0;
}
.hitl-header-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: rgba(136, 75, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.hitl-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #5C4A3A;
}
.hitl-subtitle {
  margin: 2px 0 0;
  font-size: 12px;
  color: #B8A088;
}

/* ===== Preview ===== */
.hitl-preview {
  padding: 16px 24px;
  text-align: center;
}
.hitl-preview-img-wrap {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid #F0EBE3;
  margin-bottom: 12px;
}
.hitl-preview-img {
  width: 100%;
  max-height: 260px;
  object-fit: cover;
  display: block;
}
.hitl-preview-placeholder {
  background: linear-gradient(135deg, #FDF8F2 0%, #F8F4EF 100%);
  border: 2px dashed #E8D5C0;
  border-radius: 14px;
  padding: 32px;
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.hitl-preview-silhouette {
  opacity: 0.5;
}
.hitl-preview-hint {
  margin: 0;
  font-size: 12px;
  color: #C4B5A5;
}
.hitl-question {
  font-size: 14px;
  color: #5C4A3A;
  font-weight: 500;
  line-height: 1.5;
}

/* ===== Error / Success ===== */
.hitl-error {
  margin: 0 24px 12px;
  padding: 8px 12px;
  background: #FEF3F2;
  border: 1px solid #FECDCA;
  border-radius: 10px;
  font-size: 12px;
  color: #B42318;
  display: flex;
  align-items: center;
  gap: 6px;
}
.hitl-success {
  margin: 0 24px 12px;
  padding: 8px 12px;
  background: #ECFDF3;
  border: 1px solid #A6F4C5;
  border-radius: 10px;
  font-size: 12px;
  color: #027A48;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ===== Actions ===== */
.hitl-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 24px 20px;
}
.hitl-btn {
  width: 100%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.15s;
  border: none;
}
.hitl-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.hitl-btn--primary {
  background: linear-gradient(135deg, #884BFF 0%, #7530FE 100%);
  color: #fff;
  box-shadow: 0 8px 22px rgba(136, 75, 255, 0.25);
}
.hitl-btn--primary:hover:not(:disabled) {
  box-shadow: 0 10px 28px rgba(136, 75, 255, 0.35);
  transform: translateY(-1px);
}

.hitl-btn--secondary {
  background: #fff;
  color: #5C4A3A;
  border: 1px solid #E8D5C0;
}
.hitl-btn--secondary:hover:not(:disabled) {
  background: #FDF8F2;
  border-color: #D4B896;
}

.hitl-btn--ghost {
  background: transparent;
  color: #B8A088;
  font-size: 13px;
}
.hitl-btn--ghost:hover:not(:disabled) {
  color: #8B7355;
  background: #FDF8F2;
}

.hitl-spin { animation: hitl-rotate 0.8s linear infinite; }
@keyframes hitl-rotate { to { transform: rotate(360deg); } }

/* ===== Transitions ===== */
.hitl-fade-enter-active { transition: opacity 0.25s ease; }
.hitl-fade-leave-active { transition: opacity 0.2s ease; }
.hitl-fade-enter-from,
.hitl-fade-leave-to { opacity: 0; }
</style>
