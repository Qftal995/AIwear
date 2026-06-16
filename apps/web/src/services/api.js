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

export function agentChat(params) {
  return http.post('/agent/chat', params, {
    headers: JSON_HEADERS,
    timeout: PYTHON_TIMEOUT,
  })
}

export function createChatStream(sessionId, callbacks) {
  const { onMessage, onProgress, onError, onDone } = callbacks
  const authStore = useAuthStore()
  const token = authStore.token
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

  fetch(`${baseURL}/agent/chat/stream?sessionId=${encodeURIComponent(sessionId)}`, {
    headers: {
      'Authorization': token ? `Bearer ${token}` : '',
      'Accept': 'text/event-stream',
    },
  }).then(response => {
    if (!response.ok) throw new Error('SSE connection failed')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
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

export function getStats(sessionId) {
  return http.get('/agent/stats', {
    params: sessionId ? { sessionId } : {},
  })
}

export function myRecords() {
  return http.get('/record/my')
}
