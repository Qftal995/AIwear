import http from './http'
import { useAuthStore } from '../store/auth'

const FORM_URLENCODED_HEADERS = { 'Content-Type': 'application/x-www-form-urlencoded' }
const JSON_HEADERS = { 'Content-Type': 'application/json' }
const PYTHON_TIMEOUT = 300000

export function sendCode(email) {
  return http.post('/user/send-code', { email })
}

export function auth(payload) {
  return http.post('/user/auth', payload)
}

export function logout(token) {
  if (token) {
    return http.post('/user/logout', null, {
      headers: { Authorization: `Bearer ${token}` },
    })
  }
  return http.post('/user/logout')
}

export function uploadMyImage(file) {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/file/upload/image', fd)
}

export function editImage(params) {
  return http.post('/file/edit', params, {
    headers: JSON_HEADERS,
    timeout: PYTHON_TIMEOUT,
  })
}

export function mergeImages(params) {
  return http.post('/file/merge', params, {
    headers: JSON_HEADERS,
    timeout: PYTHON_TIMEOUT,
  })
}

export function searchImages(params) {
  if (params.file) {
    const fd = new FormData()
    if (params.query?.trim()) fd.append('query', params.query.trim())
    fd.append('file', params.file)
    return http.post('/file/search', fd)
  }
  const body = new URLSearchParams()
  if (params.query?.trim()) body.append('query', params.query.trim())
  if (params.image?.trim()) body.append('image', params.image.trim())
  return http.post('/file/search', body, {
    headers: FORM_URLENCODED_HEADERS,
  })
}

export function myImages() {
  return http.get('/file/my-images')
}

/**
 * Delete an image by its MySQL ID.
 * Backend: DELETE /api/file/{id}
 */
export function deleteMyImage(imageId) {
  return http.delete(`/file/${encodeURIComponent(imageId)}`)
}

export function agentChat(params) {
  return http.post('/agent/chat', params, {
    headers: JSON_HEADERS,
    timeout: PYTHON_TIMEOUT,
  })
}

export function createChatStream(sessionId, message, callbacks) {
  const { onMessage, onProgress, onError, onDone } = callbacks
  const authStore = useAuthStore()
  const token = authStore.token
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

  fetch(`${baseURL}/agent/chat/stream?sessionId=${encodeURIComponent(sessionId)}&message=${encodeURIComponent(message || '')}`, {
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
      'Accept': 'text/event-stream',
    },
  }).then(response => {
    if (!response.ok) throw new Error('SSE connection failed')
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { onDone(); return }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6)
            if (payload === '[DONE]') { onDone(); return }
            try {
              const data = JSON.parse(payload)
              if (data.type === 'progress' || data.status === 'running') {
                onProgress(data)
              } else if (data.type === 'error') {
                onError(new Error(data.error))
              } else if (data.type === 'result') {
                onMessage(data)
              }
            } catch (e) {
              // skip non-JSON lines
            }
          }
        }
        read()
      }).catch(onError)
    }
    read()
  }).catch(onError)
}

export function getWardrobe() {
  return http.get('/agent/wardrobe')
}

/**
 * Delete a wardrobe item by image ID.
 * Backend: DELETE /api/wardrobe/{imageId}
 */
export function deleteWardrobeItem(imageId) {
  return http.delete(`/wardrobe/${encodeURIComponent(imageId)}`)
}

export function classifyWardrobe(userId) {
  return http.post(`/wardrobe/classify?userId=${encodeURIComponent(userId)}`)
}

export function getStats(sessionId) {
  return http.get('/session-stats', {
    params: sessionId ? { sessionId } : {},
  })
}

export function myRecords() {
  return http.get('/record/my')
}

// ===== Dashboard & Trace APIs =====

/**
 * Get detailed session stats including token usage, cost, latency, breakdowns.
 * Backend: GET /api/session-stats?sessionId=xxx
 */
export function getSessionStats(sessionId) {
  return http.get('/session-stats', {
    params: { sessionId },
  })
}

/**
 * Get trace panel data — timeline of agent steps for a session.
 * Backend: GET /api/traces/{sessionId}
 */
export function getTracePanel(sessionId) {
  return http.get(`/traces/${encodeURIComponent(sessionId)}`)
}

/**
 * Poll async image task status.
 * Backend: GET /api/tool/image/status/<task_id>
 */
export function getAsyncTaskStatus(taskId) {
  return http.get(`/tool/image/status/${encodeURIComponent(taskId)}`)
}

/**
 * Submit async image generation task.
 * Backend: POST /api/tool/image/async (multipart/form-data)
 */
export function submitAsyncImageTask(formData) {
  return http.post('/tool/image/async', formData, {
    timeout: PYTHON_TIMEOUT,
  })
}

// ===== MCP / RAG / Trace APIs (Phase 3-6) =====

/**
 * Get MCP server connection status.
 * Backend: GET /api/mcp/status
 */
export function getMcpStatus() {
  return http.get('/mcp/status')
}

/**
 * Get MCP tool list, optionally filtered by server.
 * Backend: GET /api/mcp/tools?server=xxx
 */
export function getMcpTools(server) {
  return http.get('/mcp/tools', { params: server ? { server } : {} })
}

/**
 * Test-call an MCP tool.
 * Backend: POST /api/mcp/test-call
 */
export function testMcpCall(tool, args) {
  return http.post('/mcp/test-call', { tool, args }, { headers: JSON_HEADERS })
}

/**
 * Search RAG knowledge base.
 * Backend: POST /api/rag/search
 */
export function searchRag(params) {
  return http.post('/rag/search', params, { headers: JSON_HEADERS })
}

/**
 * Get RAG knowledge base status.
 * Backend: GET /api/rag/status
 */
export function getRagStatus() {
  return http.get('/rag/status')
}

/**
 * Get trace events for a session.
 * Backend: GET /api/traces/{sessionId}
 */
export function getSessionTraces(sessionId) {
  return http.get(`/traces/${encodeURIComponent(sessionId)}`)
}

/**
 * Get all trace sessions summary.
 * Backend: GET /api/traces
 */
export function getAllTraces() {
  return http.get('/traces')
}

/**
 * Resume a paused HITL session.
 * Backend: POST /api/chat/resume
 */
export function resumeChat(sessionId, choice) {
  return http.post('/chat/resume', { sessionId, choice }, { headers: JSON_HEADERS })
}
