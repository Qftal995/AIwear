<script setup>
import AgentProgress from './AgentProgress.vue'

defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const uniqueImages = (images = []) => [...new Set((images || []).filter(Boolean))]

const buildOutfitGroups = (message = {}) => {
  const images = uniqueImages(message.images || [])
  const previews = images.filter((img) => img.startsWith('data:image'))
  const outfits = Array.isArray(message.outfits) ? message.outfits : []
  const imageMap = message.wardrobeImageMap || {}

  return outfits.map((outfit, index) => {
    const itemImages = uniqueImages((outfit.items || [])
      .map((item) => {
        if (!item || typeof item !== 'object') return ''
        const id = item.image_id || item.imageId
        return imageMap[String(id)] || item.oss_url || item.ossUrl || item.url || ''
      })
      .filter(Boolean))

    return {
      name: outfit.name || `搭配 ${index + 1}`,
      note: outfit.suitable_occasion || outfit.weather_note || '',
      preview: previews[index] || itemImages[0] || '',
      items: itemImages,
    }
  }).filter((group) => group.preview || group.items.length)
}

const buildFallbackImages = (message = {}) => {
  if (buildOutfitGroups(message).length) return []
  return uniqueImages(message.images || []).slice(0, 4)
}

const buildExtraImages = (message = {}) => {
  const grouped = buildOutfitGroups(message)
  const used = new Set()
  grouped.forEach((group) => {
    if (group.preview) used.add(group.preview)
    group.items.forEach((img) => used.add(img))
  })
  return uniqueImages(message.images || [])
    .filter((img) => !used.has(img) && !img.startsWith('data:image'))
    .slice(0, 12)
}

const escapeHtml = (value = '') => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;')

const inlineMarkdown = (value = '') => escapeHtml(value)
  .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

const renderMessage = (value = '') => {
  const lines = String(value).replace(/\r\n/g, '\n').split('\n')
  return lines.map((raw) => {
    const line = raw.trim()
    if (!line) return ''
    if (/^-{3,}$/.test(line)) return '<hr class="chat-md-hr" />'
    const heading = line.match(/^(#{2,4})\s*(.+)$/)
    if (heading) return `<h4 class="chat-md-heading">${inlineMarkdown(heading[2])}</h4>`
    const bullet = line.match(/^[-*]\s+(.+)$/)
    if (bullet) return `<p class="chat-md-line chat-md-bullet">${inlineMarkdown(bullet[1])}</p>`
    const numbered = line.match(/^(\d+)[.)]\s+(.+)$/)
    if (numbered) return `<p class="chat-md-line chat-md-number"><span>${numbered[1]}</span>${inlineMarkdown(numbered[2])}</p>`
    return `<p class="chat-md-line">${inlineMarkdown(line)}</p>`
  }).filter(Boolean).join('')
}
</script>

<template>
  <div class="chat-list">
    <template v-for="(m, i) in messages" :key="i">
      <div v-if="m.role === 'user'" class="chat-msg chat-msg--user">
        <div class="chat-bubble chat-bubble--user">
          <p class="chat-text">{{ m.content }}</p>
          <div v-if="m.images && m.images.length" class="chat-images">
            <img
              v-for="(img, j) in m.images"
              :key="j"
              :src="img"
              class="chat-ref-img"
              alt=""
            />
          </div>
        </div>
      </div>

      <div v-else class="chat-msg chat-msg--agent">
        <div class="chat-bubble chat-bubble--agent">
          <AgentProgress
            v-if="m.steps && m.steps.length"
            :steps="m.steps"
            :collapsed="false"
          />

          <div v-if="buildOutfitGroups(m).length" class="chat-result-panel">
            <div class="chat-result-head">
              <span>搭配预览</span>
              <small>{{ buildOutfitGroups(m).length }} 套方案</small>
            </div>

            <div class="chat-outfit-list">
              <div
                v-for="(group, gIndex) in buildOutfitGroups(m)"
                :key="gIndex"
                class="chat-outfit-row"
              >
                <div class="chat-preview-card">
                  <img v-if="group.preview" :src="group.preview" class="chat-preview-img" alt="" />
                  <div class="chat-preview-title">{{ group.name }}</div>
                </div>

                <div class="chat-item-area">
                  <div v-if="group.note" class="chat-outfit-note">{{ group.note }}</div>
                  <div class="chat-item-strip">
                    <div
                      v-for="(img, j) in group.items"
                      :key="j"
                      class="chat-item-card"
                    >
                      <img :src="img" alt="" />
                    </div>
                    <span v-if="!group.items.length" class="chat-item-empty">这套搭配暂无可映射单品图</span>
                  </div>
                </div>
              </div>
            </div>

            <details v-if="buildExtraImages(m).length" class="chat-extra-images">
              <summary>查看其余 {{ buildExtraImages(m).length }} 张候选图</summary>
              <div class="chat-extra-grid">
                <img
                  v-for="(img, j) in buildExtraImages(m)"
                  :key="j"
                  :src="img"
                  class="chat-extra-img"
                  alt=""
                />
              </div>
            </details>
          </div>

          <div v-else-if="buildFallbackImages(m).length" class="chat-result-panel">
            <div class="chat-result-head">
              <span>相关图片</span>
              <small>{{ buildFallbackImages(m).length }} 张</small>
            </div>
            <div class="chat-fallback-grid">
              <img
                v-for="(img, j) in buildFallbackImages(m)"
                :key="j"
                :src="img"
                class="chat-fallback-img"
                alt=""
              />
            </div>
          </div>

          <div v-if="m.content" class="chat-text chat-text--rich" v-html="renderMessage(m.content)"></div>
        </div>
      </div>
    </template>

    <div v-if="loading" class="chat-msg chat-msg--agent">
      <div class="chat-bubble chat-bubble--agent">
        <div class="chat-typing">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-msg {
  display: flex;
  max-width: 88%;
}
.chat-msg--user {
  align-self: flex-end;
}
.chat-msg--agent {
  align-self: flex-start;
}

.chat-bubble {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.6;
}
.chat-bubble--user {
  background: linear-gradient(135deg, #884BFF 0%, #7530FE 100%);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.chat-bubble--agent {
  width: min(100%, 920px);
  background: #fff;
  border: 1px solid #EAECF0;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04);
}

.chat-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-images {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.chat-ref-img {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  object-fit: cover;
  border: 1px solid rgba(255,255,255,0.3);
}

.chat-result-panel {
  margin-bottom: 14px;
  padding: 10px;
  border: 1px solid #EAECF0;
  border-radius: 10px;
  background: #FCFCFD;
}
.chat-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #344054;
  font-size: 13px;
  font-weight: 700;
}
.chat-result-head small {
  color: #98A2B3;
  font-size: 12px;
  font-weight: 500;
}

.chat-outfit-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.chat-outfit-row {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 10px;
  padding: 8px;
  border: 1px solid #EAECF0;
  border-radius: 10px;
  background: #fff;
}
.chat-preview-card {
  position: relative;
  min-width: 0;
}
.chat-preview-img {
  display: block;
  width: 100%;
  aspect-ratio: 3 / 4;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #EAECF0;
  background: #fff;
}
.chat-preview-title {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.88);
  color: #101828;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
}
.chat-item-area {
  min-width: 0;
}
.chat-outfit-note {
  margin-bottom: 8px;
  color: #667085;
  font-size: 12px;
  line-height: 1.5;
}
.chat-item-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.chat-item-card {
  min-width: 0;
  aspect-ratio: 3 / 4;
  border: 1px solid #EAECF0;
  border-radius: 8px;
  overflow: hidden;
  background: #FCFCFD;
}
.chat-item-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.chat-item-empty {
  color: #98A2B3;
  font-size: 12px;
  line-height: 32px;
}
.chat-extra-images {
  margin-top: 8px;
}
.chat-extra-images summary {
  cursor: pointer;
  color: #667085;
  font-size: 12px;
  line-height: 28px;
  user-select: none;
}
.chat-extra-grid,
.chat-fallback-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
  padding-top: 4px;
}
.chat-extra-img,
.chat-fallback-img {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 6px;
  object-fit: cover;
  border: 1px solid #EAECF0;
  background: #fff;
}

.chat-text--rich {
  color: #101828;
}
:deep(.chat-md-line) {
  margin: 0 0 10px;
}
:deep(.chat-md-heading) {
  margin: 16px 0 10px;
  color: #101828;
  font-size: 15px;
  line-height: 1.5;
}
:deep(.chat-md-hr) {
  border: 0;
  border-top: 1px solid #EAECF0;
  margin: 14px 0;
}
:deep(.chat-md-line strong),
:deep(.chat-md-heading strong) {
  color: #1D2939;
  font-weight: 700;
}
:deep(.chat-md-bullet) {
  position: relative;
  padding-left: 16px;
}
:deep(.chat-md-bullet::before) {
  content: '';
  position: absolute;
  left: 2px;
  top: 0.72em;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #884BFF;
}
:deep(.chat-md-number) {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 6px;
}
:deep(.chat-md-number span) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #F4F3FF;
  color: #6941C6;
  font-size: 12px;
  font-weight: 700;
}

.chat-typing {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #D0D5DD;
  animation: typing 1.2s ease-in-out infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
  30% { opacity: 1; transform: scale(1); }
}

@media (max-width: 720px) {
  .chat-msg {
    max-width: 96%;
  }
  .chat-outfit-row {
    grid-template-columns: 1fr;
  }
  .chat-preview-card {
    max-width: 220px;
  }
  .chat-item-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .chat-extra-grid,
  .chat-fallback-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
