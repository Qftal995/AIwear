<script setup>
import AgentProgress from './AgentProgress.vue'

defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
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
          <div v-if="m.images && m.images.length" class="chat-result-imgs">
            <img
              v-for="(img, j) in m.images"
              :key="j"
              :src="img"
              class="chat-result-img"
              alt=""
            />
          </div>
          <p v-if="m.content" class="chat-text">{{ m.content }}</p>
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
  max-width: 85%;
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

.chat-result-imgs {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.chat-result-img {
  width: 120px;
  height: 160px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #EAECF0;
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
</style>
