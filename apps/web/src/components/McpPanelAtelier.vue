<script setup>
import { ref, onMounted, computed } from 'vue'
import { getMcpStatus, getMcpTools, testMcpCall } from '../services/api'

const servers = ref([])
const tools = ref([])
const loading = ref(true)
const error = ref(null)
const expandedServer = ref(null)
const testDialog = ref({ open: false, tool: null, args: '', result: null, running: false })

const fetchAll = async () => {
  loading.value = true
  error.value = null
  try {
    const [sRes, tRes] = await Promise.all([getMcpStatus(), getMcpTools()])
    servers.value = (sRes.data?.data || sRes.data?.servers || [])
    tools.value = (tRes.data?.data || tRes.data?.tools || [])
  } catch (e) {
    error.value = e?.message || '加载 MCP 状态失败'
  } finally {
    loading.value = false
  }
}

const serverTools = (serverName) => tools.value.filter((t) => t.server === serverName || t.name?.startsWith(serverName))

const toggleServer = (name) => {
  expandedServer.value = expandedServer.value === name ? null : name
}

const openTest = (tool) => {
  testDialog.value = { open: true, tool, args: '{}', result: null, running: false }
}

const runTest = async () => {
  testDialog.value.running = true
  testDialog.value.result = null
  try {
    let parsed = testDialog.value.args
    try { parsed = JSON.parse(parsed) } catch {}
    const res = await testMcpCall(testDialog.value.tool.name, parsed)
    testDialog.value.result = res.data?.data || res.data
  } catch (e) {
    testDialog.value.result = { error: e?.message || '调用失败' }
  } finally {
    testDialog.value.running = false
  }
}

const connectedCount = computed(() => servers.value.filter((s) => s.status === 'connected').length)

onMounted(fetchAll)
</script>

<template>
  <div class="atelier-mcp">
    <!-- Loading -->
    <div v-if="loading" class="atelier-loading">
      <div v-for="n in 3" :key="n" class="atelier-skel-card">
        <div class="atelier-skel-line w-50"></div>
        <div class="atelier-skel-line w-80"></div>
        <div class="atelier-skel-line w-30"></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="atelier-error">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#B42318" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>{{ error }}</span>
      <button class="atelier-retry" @click="fetchAll">重试</button>
    </div>

    <!-- Content -->
    <template v-else>
      <div class="atelier-head">
        <div class="atelier-head-left">
          <span class="atelier-dot atelier-dot--live"></span>
          <span class="atelier-head-title">MCP 工具间</span>
          <span class="atelier-head-count">{{ connectedCount }}/{{ servers.length }} 在线</span>
        </div>
        <button class="atelier-refresh-btn" @click="fetchAll" title="刷新">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6"/><path d="M2 11.5a10 10 0 0118.8-4.2M22 12.5a10 10 0 01-18.8 4.2"/></svg>
        </button>
      </div>

      <div class="atelier-cards">
        <div
          v-for="s in servers"
          :key="s.name"
          class="atelier-card"
          :class="{ 'atelier-card--open': expandedServer === s.name }"
        >
          <button class="atelier-card-head" @click="toggleServer(s.name)">
            <span class="atelier-card-status" :class="'atelier-status--' + (s.status || 'unknown')"></span>
            <div class="atelier-card-meta">
              <span class="atelier-card-name">
                {{ s.name }}
                <span v-if="s.optional === false" class="atelier-badge-core">Core</span>
                <span v-else-if="s.optional" class="atelier-badge-opt">Optional</span>
              </span>
              <span class="atelier-card-desc">{{ s.description || s.transport || '' }}</span>
            </div>
            <span class="atelier-card-badge">{{ serverTools(s.name).length }} tools</span>
            <svg class="atelier-card-arrow" :class="{ 'atelier-arrow--flip': expandedServer === s.name }" width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          </button>

          <div v-if="expandedServer === s.name" class="atelier-card-body">
            <div
              v-for="tool in serverTools(s.name)"
              :key="tool.name"
              class="atelier-tool"
            >
              <div class="atelier-tool-info">
                <span class="atelier-tool-name">{{ tool.name }}</span>
                <span v-if="tool.description" class="atelier-tool-desc">{{ tool.description }}</span>
              </div>
              <button class="atelier-tool-test" @click="openTest(tool)">测试</button>
            </div>
            <div v-if="!serverTools(s.name).length" class="atelier-empty-tools">暂无工具</div>
          </div>
        </div>
      </div>

      <!-- Test Dialog -->
      <Teleport to="body">
        <div v-if="testDialog.open" class="atelier-overlay" @click.self="testDialog.open = false">
          <div class="atelier-modal">
            <div class="atelier-modal-head">
              <h3 class="atelier-modal-title">测试工具调用</h3>
              <button class="atelier-modal-close" @click="testDialog.open = false">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div class="atelier-modal-body">
              <div class="atelier-field">
                <label class="atelier-label">工具</label>
                <code class="atelier-code">{{ testDialog.tool?.name }}</code>
              </div>
              <div class="atelier-field">
                <label class="atelier-label">参数 (JSON)</label>
                <textarea
                  v-model="testDialog.args"
                  class="atelier-textarea"
                  rows="5"
                  :disabled="testDialog.running"
                ></textarea>
              </div>
              <div v-if="testDialog.result" class="atelier-field">
                <label class="atelier-label">结果</label>
                <pre class="atelier-pre">{{ JSON.stringify(testDialog.result, null, 2) }}</pre>
              </div>
            </div>
            <div class="atelier-modal-foot">
              <button class="atelier-btn-cancel" @click="testDialog.open = false">关闭</button>
              <button class="atelier-btn-run" :disabled="testDialog.running" @click="runTest">
                <svg v-if="testDialog.running" class="atelier-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6"/><path d="M2 11.5a10 10 0 0118.8-4.2M22 12.5a10 10 0 01-18.8 4.2"/></svg>
                {{ testDialog.running ? '调用中...' : '执行' }}
              </button>
            </div>
          </div>
        </div>
      </Teleport>
    </template>
  </div>
</template>

<style scoped>
/* ===== Container ===== */
.atelier-mcp {
  width: 100%;
}

/* ===== Loading ===== */
.atelier-loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.atelier-skel-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.atelier-skel-line {
  height: 14px;
  background: linear-gradient(90deg, #F0EBE3 25%, #F8F4EF 50%, #F0EBE3 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: atelier-shimmer 1.4s ease infinite;
}
.w-50 { width: 50%; }
.w-80 { width: 80%; }
.w-30 { width: 30%; }
@keyframes atelier-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ===== Error ===== */
.atelier-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #FEF3F2;
  border: 1px solid #FECDCA;
  border-radius: 12px;
  font-size: 13px;
  color: #B42318;
}
.atelier-retry {
  margin-left: auto;
  padding: 4px 14px;
  border: 1px solid #FECDCA;
  border-radius: 8px;
  background: #fff;
  color: #B42318;
  font-size: 12px;
  cursor: pointer;
}

/* ===== Head ===== */
.atelier-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.atelier-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.atelier-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #D0D5DD;
}
.atelier-dot--live {
  background: #12B76A;
  box-shadow: 0 0 6px rgba(18, 183, 106, 0.4);
  animation: atelier-pulse 2s ease-in-out infinite;
}
@keyframes atelier-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}
.atelier-head-title {
  font-size: 14px;
  font-weight: 600;
  color: #5C4A3A;
}
.atelier-head-count {
  font-size: 11px;
  color: #B8A088;
  background: #FDF8F2;
  padding: 2px 10px;
  border-radius: 10px;
}
.atelier-refresh-btn {
  width: 30px;
  height: 30px;
  border: 1px solid #F0EBE3;
  border-radius: 8px;
  background: #fff;
  color: #B8A088;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.atelier-refresh-btn:hover { background: #FDF8F2; color: #5C4A3A; }

/* ===== Cards ===== */
.atelier-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.atelier-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 14px;
  overflow: hidden;
  transition: box-shadow 0.2s, transform 0.2s;
}
.atelier-card:hover {
  box-shadow: 0 2px 12px rgba(16, 24, 40, 0.06);
}
.atelier-card--open {
  box-shadow: 0 2px 12px rgba(16, 24, 40, 0.06);
  border-color: rgba(136, 75, 255, 0.18);
}

.atelier-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 14px 16px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}
.atelier-card-head:hover { background: #FDF8F2; }

.atelier-card-status {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.atelier-status--connected { background: #12B76A; box-shadow: 0 0 8px rgba(18, 183, 106, 0.3); }
.atelier-status--disconnected { background: #F04438; }
.atelier-status--unknown { background: #D0D5DD; }

.atelier-card-meta { flex: 1; min-width: 0; }
.atelier-card-name {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #5C4A3A;
}
.atelier-badge-core {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(18, 183, 106, 0.12);
  color: #12B76A;
  font-weight: 600;
  margin-left: 6px;
  vertical-align: middle;
}
.atelier-badge-opt {
  display: inline-block;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(184, 160, 136, 0.12);
  color: #B8A088;
  font-weight: 500;
  margin-left: 6px;
  vertical-align: middle;
}
.atelier-card-desc {
  display: block;
  font-size: 11px;
  color: #B8A088;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.atelier-card-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(136, 75, 255, 0.08);
  color: #884BFF;
  font-weight: 500;
  flex-shrink: 0;
}
.atelier-card-arrow {
  color: #C4B5A5;
  flex-shrink: 0;
  transition: transform 0.2s;
}
.atelier-arrow--flip { transform: rotate(90deg); }

/* ===== Tool List ===== */
.atelier-card-body {
  border-top: 1px solid #F0EBE3;
  padding: 4px;
}
.atelier-tool {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  transition: background 0.12s;
}
.atelier-tool:hover { background: #FDF8F2; }
.atelier-tool-info {
  flex: 1;
  min-width: 0;
}
.atelier-tool-name {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: #5C4A3A;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.atelier-tool-desc {
  display: block;
  font-size: 11px;
  color: #B8A088;
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.atelier-tool-test {
  padding: 4px 14px;
  border: 1px solid rgba(136, 75, 255, 0.25);
  border-radius: 8px;
  background: #fff;
  color: #884BFF;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.atelier-tool-test:hover {
  background: rgba(136, 75, 255, 0.08);
  border-color: rgba(136, 75, 255, 0.4);
}
.atelier-empty-tools {
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: #C4B5A5;
}

/* ===== Modal ===== */
.atelier-overlay {
  position: fixed;
  inset: 0;
  background: rgba(92, 74, 58, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.atelier-modal {
  width: 480px;
  max-width: 90vw;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(16, 24, 40, 0.15);
  overflow: hidden;
}
.atelier-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #F0EBE3;
}
.atelier-modal-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #5C4A3A;
}
.atelier-modal-close {
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
.atelier-modal-close:hover { background: #F5E6D3; color: #5C4A3A; }
.atelier-modal-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.atelier-field { display: flex; flex-direction: column; gap: 6px; }
.atelier-label {
  font-size: 12px;
  font-weight: 600;
  color: #8B7355;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.atelier-code {
  padding: 8px 12px;
  background: #FDF8F2;
  border: 1px solid #F0EBE3;
  border-radius: 8px;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  color: #884BFF;
}
.atelier-textarea {
  padding: 10px 12px;
  border: 1px solid #E8D5C0;
  border-radius: 10px;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  color: #5C4A3A;
  background: #FDF8F2;
  outline: none;
  resize: vertical;
  transition: border-color 0.15s;
}
.atelier-textarea:focus { border-color: rgba(136, 75, 255, 0.4); }
.atelier-pre {
  margin: 0;
  padding: 10px 12px;
  background: #FDF8F2;
  border: 1px solid #F0EBE3;
  border-radius: 10px;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  color: #5C4A3A;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.atelier-modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #F0EBE3;
  background: #FDF8F2;
}
.atelier-btn-cancel {
  padding: 8px 18px;
  border: 1px solid #E8D5C0;
  border-radius: 10px;
  background: #fff;
  color: #8B7355;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.atelier-btn-cancel:hover { background: #F5E6D3; }
.atelier-btn-run {
  padding: 8px 20px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #884BFF 0%, #7530FE 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.15s;
}
.atelier-btn-run:hover:not(:disabled) { opacity: 0.9; }
.atelier-btn-run:disabled { opacity: 0.5; cursor: not-allowed; }
.atelier-spin { animation: atelier-rotate 0.8s linear infinite; }
@keyframes atelier-rotate { to { transform: rotate(360deg); } }
</style>
