<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import { agentChat } from '../services/api'
import AgentChat from '../components/AgentChat.vue'

const QUICK_PROMPTS = ['约会穿搭', '通勤上班', '休闲周末', '商务会议', '运动户外']

const messages = ref([])
const loading = ref(false)
const inputText = ref('')
const refImages = ref([])
const chatScroll = ref(null)
const fileInput = ref(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (chatScroll.value) {
      chatScroll.value.scrollTop = chatScroll.value.scrollHeight
    }
  })
}

const addRefImage = (file) => {
  if (refImages.value.length >= 4) return
  const url = URL.createObjectURL(file)
  refImages.value.push({ file, url, name: file.name })
}

const removeRefImage = (idx) => {
  URL.revokeObjectURL(refImages.value[idx].url)
  refImages.value.splice(idx, 1)
}

const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  const userMsg = {
    role: 'user',
    content: text,
    images: refImages.value.map((r) => r.url),
  }
  messages.value.push(userMsg)
  inputText.value = ''
  refImages.value.forEach((r) => URL.revokeObjectURL(r.url))
  refImages.value = []
  loading.value = true
  scrollToBottom()

  try {
    const payload = {
      message: text,
      session_id: sessionId.value,
    }
    if (userMsg.images.length) {
      payload.image_urls = userMsg.images
    }

    const { data } = await agentChat(payload)
    const body = data.data || data

    const agentMsg = {
      role: 'agent',
      content: body.reply || body.message || '',
      images: (body.sub_results || [])
        .filter((r) => r.type === 'image')
        .map((r) => r.url),
      progress: (body.steps || []).map((s) => ({
        name: s.name || s.step,
        label: s.name || s.step,
        status: s.status || 'done',
        duration: s.duration,
      })),
    }
    messages.value.push(agentMsg)
  } catch (err) {
    messages.value.push({
      role: 'agent',
      content: err?.message || '请求失败，请稍后重试',
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

const sendQuickPrompt = (prompt) => {
  inputText.value = prompt
  sendMessage()
}

const handleFileChange = (e) => {
  const files = e.target.files || []
  for (const f of files) addRefImage(f)
  if (fileInput.value) fileInput.value.value = ''
}

const sessionId = ref('session_' + Date.now())

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

onMounted(() => {
  sessionId.value = 'session_' + Date.now()
})
</script>

<template>
  <div class="chat-page">
    <div class="chat-body" ref="chatScroll">
      <div v-if="!messages.length && !loading" class="chat-empty">
        <div class="chat-empty-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="4" y="8" width="40" height="28" rx="4" stroke="#C4B5A5" stroke-width="1.5" fill="none"/>
            <circle cx="16" cy="22" r="3" fill="#C4B5A5" opacity="0.4"/>
            <circle cx="24" cy="22" r="3" fill="#C4B5A5" opacity="0.4"/>
            <circle cx="32" cy="22" r="3" fill="#C4B5A5" opacity="0.4"/>
            <path d="M12 32h24" stroke="#C4B5A5" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <h3 class="chat-empty-title">AI 智能搭配助手</h3>
        <p class="chat-empty-desc">
          告诉我你要去什么场合、喜欢什么风格，<br/>我帮你从衣橱里挑出最适合的穿搭
        </p>
        <div class="chat-quick-prompts">
          <button
            v-for="p in QUICK_PROMPTS"
            :key="p"
            class="chat-quick-chip"
            @click="sendQuickPrompt(p)"
          >{{ p }}</button>
        </div>
      </div>

      <AgentChat :messages="messages" :loading="loading" />
    </div>

    <div class="chat-footer">
      <div v-if="refImages.length" class="chat-ref-row">
        <div v-for="(img, idx) in refImages" :key="idx" class="chat-ref-thumb">
          <img :src="img.url" :alt="img.name" />
          <button class="chat-ref-remove" @click="removeRefImage(idx)">&times;</button>
        </div>
        <button
          v-if="refImages.length < 4"
          class="chat-ref-add"
          @click="fileInput?.click()"
        >+</button>
      </div>

      <div class="chat-input-row">
        <button class="chat-add-btn" @click="fileInput?.click()" title="添加参考图">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
        </button>
        <input
          type="file"
          ref="fileInput"
          accept="image/*"
          class="chat-file-hidden"
          @change="handleFileChange"
          multiple
        />
        <textarea
          v-model="inputText"
          class="chat-textarea"
          rows="1"
          placeholder="输入你的搭配需求..."
          :disabled="loading"
          @keydown="handleKeydown"
        ></textarea>
        <button
          class="chat-send-btn"
          :disabled="!inputText.trim() || loading"
          @click="sendMessage"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 130px);
  max-width: 800px;
  margin: 0 auto;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 16px;
  scroll-behavior: smooth;
}

/* 空态 */
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 360px;
  text-align: center;
  padding: 48px 24px;
}
.chat-empty-icon {
  margin-bottom: 16px;
  opacity: 0.6;
}
.chat-empty-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #5C4A3A;
  letter-spacing: 0.3px;
}
.chat-empty-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: #8B7355;
  line-height: 1.7;
}
.chat-quick-prompts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}
.chat-quick-chip {
  padding: 8px 16px;
  background: #FDF8F2;
  border: 1px solid #E8D5C0;
  border-radius: 20px;
  color: #8B6914;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.chat-quick-chip:hover {
  background: #F5E6D3;
  border-color: #D4B896;
}

/* 底部输入区 */
.chat-footer {
  padding: 12px 0 4px;
  border-top: 1px solid #F0EBE3;
}
.chat-ref-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  align-items: center;
}
.chat-ref-thumb {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid #E8D5C0;
}
.chat-ref-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.chat-ref-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  color: #fff;
  border: none;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chat-ref-add {
  width: 48px;
  height: 48px;
  border: 1px dashed #D4B896;
  border-radius: 6px;
  background: transparent;
  color: #B8A088;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s;
}
.chat-ref-add:hover {
  border-color: #8B6914;
}
.chat-input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.chat-add-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: 1px solid #E8D5C0;
  border-radius: 8px;
  background: #FDF8F2;
  color: #8B7355;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}
.chat-add-btn:hover {
  background: #F5E6D3;
}
.chat-file-hidden {
  display: none;
}
.chat-textarea {
  flex: 1;
  min-height: 36px;
  max-height: 100px;
  padding: 8px 12px;
  border: 1px solid #E8D5C0;
  border-radius: 10px;
  outline: none;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
  background: #FDF8F2;
  color: #5C4A3A;
  transition: border-color 0.2s;
}
.chat-textarea:focus {
  border-color: #C4A97D;
}
.chat-textarea::placeholder {
  color: #C4B5A5;
}
.chat-textarea:disabled {
  opacity: 0.6;
}
.chat-send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #884BFF 0%, #7530FE 100%);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.2s;
}
.chat-send-btn:hover:not(:disabled) {
  opacity: 0.9;
}
.chat-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
