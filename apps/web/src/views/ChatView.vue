<script setup>
import { ref, nextTick, watch, onMounted, computed } from 'vue'
import { agentChat, searchRag, resumeChat, uploadMyImage } from '../services/api'
import AgentChat from '../components/AgentChat.vue'
import McpPanelAtelier from '../components/McpPanelAtelier.vue'
import RagCitationAtelier from '../components/RagCitationAtelier.vue'
import HitlDialogAtelier from '../components/HitlDialogAtelier.vue'

const QUICK_PROMPTS = ['约会穿搭', '通勤上班', '休闲周末', '商务会议', '运动户外']

const messages = ref([])
const loading = ref(false)
const inputText = ref('')
const refImages = ref([])
const chatScroll = ref(null)
const fileInput = ref(null)

// ── Sidebar: 对话记录 ──
const showHistory = ref(false)
const currentSteps = ref([])
const currentToolCalls = ref([])
const currentCitations = ref([])
const currentSessionMeta = ref({ intent: '', city: '', citySource: '' })

// ── MCP / RAG / HITL state ──
const showMcp = ref(false)
const ragResults = ref([])
const ragVisible = ref(false)
const ragToast = ref('')
const ragLoading = ref(false)
const hitlVisible = ref(false)
const hitlSessionId = ref('')
const hitlQuestion = ref('')
const toolEvents = ref([])
const currentSessionId = ref('')

// ── GPS ──
let _gpsCache = null
const getGPSCoords = () => {
  return new Promise((resolve) => {
    if (_gpsCache) return resolve(_gpsCache)
    if (!navigator.geolocation) { _gpsCache = null; return resolve(null) }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        _gpsCache = { lat: pos.coords.latitude, lng: pos.coords.longitude }
        resolve(_gpsCache)
      },
      () => { _gpsCache = null; resolve(null) },
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 5 * 60 * 1000 }
    )
  })
}

// Turn count for display
const turnCount = computed(() => {
  return messages.value.filter(m => m.role === 'user').length
})

const scrollToBottom = () => {
  nextTick(() => {
    if (chatScroll.value) {
      chatScroll.value.scrollTop = chatScroll.value.scrollHeight
    }
  })
}

const collectImageUrls = (value, acc = []) => {
  if (!value) return acc
  if (typeof value === 'string') {
    if (value.startsWith('http') || value.startsWith('data:image')) acc.push(value)
    return acc
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectImageUrls(item, acc))
    return [...new Set(acc)]
  }
  if (typeof value === 'object') {
    ;['url', 'imageUrl', 'image_url', 'previewUrl', 'preview_url', 'ossUrl', 'oss_url'].forEach((key) => {
      collectImageUrls(value[key], acc)
    })
    ;['images', 'result', 'results', 'subResults', 'output'].forEach((key) => {
      collectImageUrls(value[key], acc)
    })
  }
  return [...new Set(acc)]
}

const collectOutfits = (body = {}) => {
  const subResults = Array.isArray(body.subResults) ? body.subResults : []
  const stylist = subResults.find((item) => item?.agent === 'stylist' && item?.result?.outfits)
  return stylist?.result?.outfits || []
}

const collectWardrobeImageMap = (body = {}) => {
  const map = {}
  const walk = (value) => {
    if (!value) return
    if (Array.isArray(value)) {
      value.forEach(walk)
      return
    }
    if (typeof value !== 'object') return
    const id = value.image_id || value.imageId || value.id
    const meta = value.metadata || {}
    const url = value.url || value.imageUrl || value.image_url || value.ossUrl || value.oss_url || meta.oss_url || meta.ossUrl
    if (id && typeof url === 'string' && url.startsWith('http')) map[String(id)] = url
    Object.values(value).forEach(walk)
  }
  walk(body.toolCalls)
  walk(body.subResults)
  return map
}

const applyAgentResultState = (body = {}) => {
  currentSteps.value = body.steps || []
  currentToolCalls.value = body.toolCalls || []
  currentCitations.value = body.citations || []
  currentSessionMeta.value = {
    intent: body.intent || '',
    city: body.city || '',
    citySource: body.citySource || '',
  }

  if (body.citations && body.citations.length) ragResults.value = body.citations
  if (body.toolCalls && body.toolCalls.length) toolEvents.value = body.toolCalls
}

const createAgentMessage = (body = {}) => ({
  role: 'agent',
  content: body.reply || body.message || '',
  images: collectImageUrls(body.images || body.subResults || body),
  outfits: collectOutfits(body),
  wardrobeImageMap: collectWardrobeImageMap(body),
  steps: currentSteps.value,
  toolCalls: currentToolCalls.value,
  citations: currentCitations.value,
  meta: currentSessionMeta.value,
  time: Date.now(),
})

const addRefImage = (file) => {
  if (refImages.value.length >= 4) return
  const url = URL.createObjectURL(file)
  refImages.value.push({ file, url, name: file.name })
}

const removeRefImage = (idx) => {
  URL.revokeObjectURL(refImages.value[idx].url)
  refImages.value.splice(idx, 1)
}

const uploadChatImages = async () => {
  const uploaded = []
  for (const item of refImages.value) {
    const { data } = await uploadMyImage(item.file)
    const body = data.data || data
    uploaded.push(body.url)
  }
  return uploaded
}

const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  loading.value = true
  toolEvents.value = []
  currentSteps.value = []
  currentToolCalls.value = []
  currentCitations.value = []
  currentSessionMeta.value = {}

  const localPreviewUrls = refImages.value.map((r) => r.url)
  const refsToRelease = [...refImages.value]

  const userMsg = {
    role: 'user',
    content: text,
    images: localPreviewUrls,
    time: Date.now(),
  }
  messages.value.push(userMsg)
  inputText.value = ''
  scrollToBottom()

  try {
    const uploadedImageUrls = await uploadChatImages()
    if (uploadedImageUrls.length) {
      userMsg.images = uploadedImageUrls
    }
    refsToRelease.forEach((r) => URL.revokeObjectURL(r.url))
    refImages.value = []

    const payload = { message: text, session_id: currentSessionId.value }
    if (uploadedImageUrls.length) {
      payload.imageUrls = uploadedImageUrls
      payload.imageUrl = uploadedImageUrls[0]
    }

    const gps = await getGPSCoords()
    if (gps) {
      payload.latitude = gps.lat
      payload.longitude = gps.lng
    }

    const { data } = await agentChat(payload)
    const body = data.data || data
    const sid = body.sessionId || body.session_id

    if (sid) currentSessionId.value = sid

    applyAgentResultState(body)
    messages.value.push(createAgentMessage(body))

    // HITL: show confirmation dialog when backend requests it
    if (body.needsHitl) {
      hitlSessionId.value = sid || currentSessionId.value
      hitlQuestion.value = body.hitl?.question || body.reply || '请确认是否继续？'
      hitlVisible.value = true
    }

    loading.value = false
    scrollToBottom()
    saveHistory()
  } catch (err) {
    messages.value.push({
      role: 'agent',
      content: err?.message || '请求失败，请稍后重试',
      time: Date.now(),
    })
    loading.value = false
    scrollToBottom()
    saveHistory()
  }
}

const handleHitlConfirm = (body = {}) => {
  hitlVisible.value = false
  if (body && (body.reply || body.images || body.subResults)) {
    applyAgentResultState(body)
    messages.value.push(createAgentMessage(body))
    scrollToBottom()
    saveHistory()
  }
}

const handleHitlModify = () => {
  hitlVisible.value = false
  inputText.value = '请修改搭配方案：'
}

const handleHitlCancel = () => {
  hitlVisible.value = false
}

const searchRagInline = async () => {
  const lastUserMsg = [...messages.value].reverse().find((m) => m.role === 'user')
  if (!lastUserMsg) {
    ragToast.value = '请先发送消息再检索知识库'
    setTimeout(() => { ragToast.value = '' }, 3000)
    return
  }
  ragLoading.value = true
  try {
    const { data } = await searchRag({ query: lastUserMsg.content, topK: 3 })
    const results = Array.isArray(data?.data) ? data.data : (data?.results || [])
    if (results.length) {
      ragResults.value = results
      ragVisible.value = true
    } else {
      ragToast.value = '未找到相关知识条目，请尝试更具体的查询'
      setTimeout(() => { ragToast.value = '' }, 3000)
    }
  } catch (e) {
    ragToast.value = '知识库检索失败：' + (e?.message || '服务不可用')
    setTimeout(() => { ragToast.value = '' }, 4000)
  } finally {
    ragLoading.value = false
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

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// Jump to a specific turn in the conversation
const jumpToTurn = (idx) => {
  // Find the user message at that index and scroll to it
  const userMsgs = messages.value.filter(m => m.role === 'user')
  if (idx >= 0 && idx < userMsgs.length) {
    const target = userMsgs[idx]
    const el = document.getElementById('msg-' + target.time)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const stepLabel = (name) => {
  const map = {
    intent: '意图分析', planning: '工具规划', tool_execution: '调用工具',
    dispatch: '调用助手', aggregate: '整合结果', final: '生成回复'
  }
  return map[name] || name
}

const stepColor = (name) => {
  const map = {
    intent: '#884BFF', planning: '#7C3AED', tool_execution: '#F59E0B',
    dispatch: '#10B981', aggregate: '#3B82F6', final: '#EC4899'
  }
  return map[name] || '#8B7355'
}

const toolColor = (tool) => {
  if (tool === 'weather') return '#F59E0B'
  if (tool === 'rag_search') return '#884BFF'
  if (tool === 'wardrobe_search') return '#10B981'
  if (tool === 'body_shape') return '#EC4899'
  return '#8B7355'
}

const toolLabel = (tool) => {
  const map = {
    weather: '天气', rag_search: '知识库', wardrobe_search: '衣橱',
    body_shape: '身材分析'
  }
  return map[tool] || tool
}

const saveHistory = () => {
  try {
    const data = {
      sessionId: currentSessionId.value,
      messages: messages.value.slice(-40), // last 40 messages
      steps: currentSteps.value,
      toolCalls: currentToolCalls.value,
      meta: currentSessionMeta.value,
      updated: Date.now(),
    }
    localStorage.setItem('aiwear_chat_history', JSON.stringify(data))
  } catch {}
}

const loadHistory = () => {
  try {
    const raw = localStorage.getItem('aiwear_chat_history')
    if (!raw) return
    const data = JSON.parse(raw)
    if (data.messages?.length) {
      messages.value = data.messages
      currentSteps.value = data.steps || []
      currentToolCalls.value = data.toolCalls || []
      currentSessionMeta.value = data.meta || {}
      if (data.sessionId) currentSessionId.value = data.sessionId
    }
  } catch {}
}

onMounted(() => {
  loadHistory()
  if (!currentSessionId.value) currentSessionId.value = 'session_' + Date.now()
})

// Clear current session
const clearSession = () => {
  messages.value = []
  currentSteps.value = []
  currentToolCalls.value = []
  currentCitations.value = []
  currentSessionMeta.value = {}
  currentSessionId.value = 'session_' + Date.now()
  localStorage.removeItem('aiwear_chat_history')
}
</script>

<template>
  <div class="chat-layout">
    <!-- ===== 对话记录 Sidebar ===== -->
    <aside class="chat-sidebar" :class="{ 'chat-sidebar--open': showHistory }">
      <div class="chat-sidebar-head">
        <span class="chat-sidebar-title">对话记录</span>
        <button class="chat-sidebar-close" @click="showHistory = false">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <div class="chat-sidebar-body">
        <!-- Session meta -->
        <div v-if="currentSessionMeta.intent || currentSessionMeta.city" class="hs-section">
          <div class="hs-section-title">会话信息</div>
          <div class="hs-meta-grid">
            <div v-if="currentSessionMeta.intent" class="hs-meta-item">
              <span class="hs-meta-label">意图</span>
              <span class="hs-meta-value">{{ currentSessionMeta.intent }}</span>
            </div>
            <div v-if="currentSessionMeta.city" class="hs-meta-item">
              <span class="hs-meta-label">城市</span>
              <span class="hs-meta-value">{{ currentSessionMeta.city }}
                <span v-if="currentSessionMeta.citySource" class="hs-meta-tag">{{ currentSessionMeta.citySource === 'gps' ? 'GPS' : currentSessionMeta.citySource }}</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Turn history -->
        <div v-if="messages.length" class="hs-section">
          <div class="hs-section-title">对话轮次 ({{ turnCount }})</div>
          <div class="hs-turn-list">
            <button
              v-for="(msg, i) in messages.filter(m => m.role === 'user')"
              :key="i"
              class="hs-turn-item"
              @click="jumpToTurn(i)"
            >
              <span class="hs-turn-idx">#{{ i + 1 }}</span>
              <span class="hs-turn-text">{{ msg.content.slice(0, 30) }}{{ msg.content.length > 30 ? '...' : '' }}</span>
              <span class="hs-turn-time">{{ new Date(msg.time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</span>
            </button>
          </div>
        </div>

        <!-- Agent 流水 (steps) -->
        <div v-if="currentSteps.length" class="hs-section">
          <div class="hs-section-title">Agent 流水</div>
          <div class="hs-flow">
            <div
              v-for="(step, i) in currentSteps"
              :key="i"
              class="hs-flow-item"
            >
              <div class="hs-flow-bar" :style="{ background: stepColor(step.name) }"></div>
              <div class="hs-flow-info">
                <span class="hs-flow-label">{{ step.label || stepLabel(step.name) }}</span>
                <span class="hs-flow-time">{{ step.duration ? step.duration.toFixed(1) + 's' : '' }}</span>
              </div>
              <div class="hs-flow-detail" v-if="step.detail">
                <span v-if="step.detail.intent">意图: {{ step.detail.intent }}</span>
                <span v-if="step.detail.city">城市: {{ step.detail.city }}</span>
                <span v-if="step.detail.tools">{{ step.detail.tools.map(toolLabel).join(', ') }}</span>
                <span v-if="step.detail.agents">{{ step.detail.agents.join(', ') }}</span>
                <span v-if="step.detail.citations !== undefined">{{ step.detail.citations }} 条引用</span>
                <span v-if="step.detail.reply_len">{{ step.detail.reply_len }} 字回复</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 工具调用热力图 -->
        <div v-if="currentToolCalls.length" class="hs-section">
          <div class="hs-section-title">工具调用</div>
          <div class="hs-tool-list">
            <div
              v-for="(tc, i) in currentToolCalls"
              :key="i"
              class="hs-tool-item"
              :class="{ 'hs-tool-item--fail': !tc.success }"
            >
              <span
                class="hs-tool-dot"
                :style="{ background: tc.success ? toolColor(tc.tool) : '#F04438' }"
              ></span>
              <span class="hs-tool-name">{{ toolLabel(tc.tool) || tc.tool }}</span>
              <span class="hs-tool-status">{{ tc.success ? '成功' : '失败' }}</span>
              <span v-if="tc.result?.latencyMs" class="hs-tool-latency">{{ tc.result.latencyMs }}ms</span>
              <!-- Tool result preview -->
              <div class="hs-tool-result" v-if="tc.result?.result">
                <template v-if="tc.tool === 'weather' && tc.result.result">
                  <span v-if="tc.result.result.city">{{ tc.result.result.city }}</span>
                  <span v-if="tc.result.result.temperature">{{ tc.result.result.temperature }}°C</span>
                  <span v-if="tc.result.result.condition">{{ tc.result.result.condition }}</span>
                </template>
                <template v-else-if="tc.tool === 'wardrobe_search' && tc.result.result">
                  <span>{{ tc.result.result.total || 0 }} 件单品</span>
                </template>
                <template v-else-if="tc.tool === 'rag_search'">
                  <span>{{ tc.result.resultCount || 0 }} 条知识</span>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="!messages.length && !currentSteps.length && !currentToolCalls.length" class="hs-empty">
          <p>暂无对话记录</p>
          <p class="hs-empty-hint">开始对话后将在此显示<br/>Agent 流水和工具调用</p>
        </div>
      </div>

      <!-- Clear button -->
      <div v-if="messages.length" class="chat-sidebar-foot">
        <button class="hs-clear-btn" @click="clearSession">清空当前会话</button>
      </div>
    </aside>

    <!-- ===== Main Chat Area ===== -->
    <div class="chat-page">
      <!-- Header bar -->
      <div class="chat-top-bar">
        <div class="chat-top-left">
          <button class="chat-top-btn chat-menu-btn" @click="showHistory = !showHistory" :class="{ 'chat-top-btn--active': showHistory }" title="对话记录">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="12" y2="17"/></svg>
            <span>对话记录</span>
            <span v-if="turnCount" class="chat-top-dot">{{ turnCount }}</span>
          </button>
          <span class="chat-top-title">AI 智能搭配助手</span>
        </div>
        <div class="chat-top-actions">
          <button class="chat-top-btn" :class="{ 'chat-top-btn--active': showMcp }" @click="showMcp = !showMcp" title="MCP 工具间">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="18" r="1"/><circle cx="9.5" cy="6" r="1"/></svg>
            <span>MCP</span>
            <span v-if="toolEvents.length" class="chat-top-dot">{{ toolEvents.length }}</span>
          </button>
          <button class="chat-top-btn" @click="searchRagInline" title="检索知识库" :disabled="ragLoading">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
            <span>{{ ragLoading ? '检索中...' : '知识库' }}</span>
          </button>
          <span v-if="ragToast" class="chat-rag-toast">{{ ragToast }}</span>
        </div>
      </div>

      <!-- MCP Panel -->
      <div v-if="showMcp" class="chat-mcp-wrap">
        <McpPanelAtelier :tool-events="toolEvents" />
      </div>

      <!-- Chat body -->
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

        <AgentChat :messages="messages" :loading="loading">
        </AgentChat>

        <!-- RAG citation toggle -->
        <div v-if="ragResults.length && !ragVisible" class="chat-rag-toggle">
          <button @click="ragVisible = true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#884BFF" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
            查看 {{ ragResults.length }} 条知识引用
          </button>
        </div>
      </div>

      <!-- Footer -->
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

      <!-- Overlays -->
      <RagCitationAtelier :results="ragResults" :visible="ragVisible" @close="ragVisible = false" />
      <HitlDialogAtelier
        :visible="hitlVisible"
        :session-id="hitlSessionId"
        :question="hitlQuestion"
        @confirm="handleHitlConfirm"
        @modify="handleHitlModify"
        @cancel="handleHitlCancel"
      />
    </div>
  </div>
</template>

<style scoped>
/* ===== Layout ===== */
.chat-layout {
  display: flex;
  height: calc(100vh - 130px);
  max-width: 1100px;
  margin: 0 auto;
  gap: 0;
  position: relative;
}

/* ===== Sidebar ===== */
.chat-sidebar {
  width: 0;
  overflow: hidden;
  flex-shrink: 0;
  background: #FDF8F2;
  border-right: 1px solid #F0EBE3;
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease;
}
.chat-sidebar--open {
  width: 300px;
}
.chat-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid #F0EBE3;
  flex-shrink: 0;
}
.chat-sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: #5C4A3A;
}
.chat-sidebar-close {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: #B8A088;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: background 0.15s;
}
.chat-sidebar-close:hover {
  background: #F0EBE3;
}
.chat-sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 0;
}
.chat-sidebar-foot {
  padding: 8px 14px;
  border-top: 1px solid #F0EBE3;
  flex-shrink: 0;
}

/* ===== Sidebar sections ===== */
.hs-section {
  padding: 8px 14px;
}
.hs-section + .hs-section {
  border-top: 1px solid #F5F0E8;
}
.hs-section-title {
  font-size: 11px;
  font-weight: 600;
  color: #B8A088;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

/* Session meta */
.hs-meta-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hs-meta-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.hs-meta-label {
  color: #B8A088;
  min-width: 32px;
}
.hs-meta-value {
  color: #5C4A3A;
  font-weight: 500;
}
.hs-meta-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(136, 75, 255, 0.1);
  color: #884BFF;
  margin-left: 4px;
}

/* Turn list */
.hs-turn-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.hs-turn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: #5C4A3A;
  transition: background 0.15s;
}
.hs-turn-item:hover {
  background: #F5E6D3;
}
.hs-turn-idx {
  font-weight: 600;
  color: #884BFF;
  flex-shrink: 0;
  min-width: 20px;
}
.hs-turn-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hs-turn-time {
  font-size: 10px;
  color: #B8A088;
  flex-shrink: 0;
}

/* Agent flow */
.hs-flow {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hs-flow-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 6px;
  background: rgba(0,0,0,0.02);
}
.hs-flow-bar {
  width: 3px;
  height: 14px;
  border-radius: 2px;
  flex-shrink: 0;
}
.hs-flow-info {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.hs-flow-label {
  font-size: 12px;
  font-weight: 500;
  color: #5C4A3A;
}
.hs-flow-time {
  font-size: 11px;
  color: #B8A088;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.hs-flow-detail {
  width: 100%;
  padding-left: 9px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 10px;
  color: #8B7355;
}

/* Tool calls */
.hs-tool-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hs-tool-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(0,0,0,0.02);
  font-size: 12px;
}
.hs-tool-item--fail {
  background: rgba(240, 68, 56, 0.04);
}
.hs-tool-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.hs-tool-name {
  font-weight: 500;
  color: #5C4A3A;
}
.hs-tool-status {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: #ECFDF3;
  color: #027A48;
}
.hs-tool-item--fail .hs-tool-status {
  background: #FEF3F2;
  color: #B42318;
}
.hs-tool-latency {
  font-size: 10px;
  color: #B8A088;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.hs-tool-result {
  width: 100%;
  padding-left: 14px;
  display: flex;
  gap: 6px;
  font-size: 11px;
  color: #8B7355;
}

/* Empty */
.hs-empty {
  padding: 32px 14px;
  text-align: center;
  color: #B8A088;
}
.hs-empty p {
  margin: 0;
  font-size: 13px;
}
.hs-empty-hint {
  margin-top: 4px !important;
  font-size: 11px !important;
  color: #C4B5A5;
}

/* Clear button */
.hs-clear-btn {
  width: 100%;
  padding: 6px 0;
  border: 1px solid #FECDCA;
  border-radius: 8px;
  background: #FEF3F2;
  color: #B42318;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.hs-clear-btn:hover {
  background: #FEE4E2;
}

/* ===== Chat Page ===== */
.chat-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

/* ── Top bar ── */
.chat-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px 8px;
  flex-shrink: 0;
}
.chat-top-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.chat-menu-btn {
  gap: 5px;
}
.chat-top-title {
  font-size: 15px;
  font-weight: 600;
  color: #5C4A3A;
}
.chat-top-actions {
  display: flex;
  gap: 6px;
  position: relative;
}
.chat-top-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border: 1px solid #E8D5C0;
  border-radius: 8px;
  background: #FDF8F2;
  color: #8B7355;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}
.chat-top-btn:hover {
  background: #F5E6D3;
  border-color: #D4B896;
}
.chat-top-btn--active {
  background: rgba(136, 75, 255, 0.08);
  border-color: rgba(136, 75, 255, 0.25);
  color: #884BFF;
}
.chat-top-dot {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #884BFF;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ── MCP panel ── */
.chat-mcp-wrap {
  flex-shrink: 0;
  margin-bottom: 8px;
  max-height: 340px;
  overflow-y: auto;
  background: #FDF8F2;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 12px;
}

/* ── RAG toggle ── */
.chat-rag-toggle {
  padding: 8px 0;
  text-align: center;
}
.chat-rag-toggle button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: 1px solid rgba(136, 75, 255, 0.2);
  border-radius: 10px;
  background: rgba(136, 75, 255, 0.04);
  color: #884BFF;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.chat-rag-toggle button:hover {
  background: rgba(136, 75, 255, 0.1);
  border-color: rgba(136, 75, 255, 0.35);
}

/* ── RAG toast ── */
.chat-rag-toast {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 6px;
  padding: 6px 14px;
  background: #FFF8E1;
  border: 1px solid #F0D060;
  border-radius: 8px;
  color: #8B6914;
  font-size: 12px;
  white-space: nowrap;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  animation: ragToastIn 0.2s ease;
}
@keyframes ragToastIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 16px;
  scroll-behavior: smooth;
}

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
