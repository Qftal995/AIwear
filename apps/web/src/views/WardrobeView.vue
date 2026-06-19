<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { getWardrobe, uploadMyImage, deleteWardrobeItem, classifyWardrobe } from '../services/api'
import { useAuthStore } from '../store/auth'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()

const items = ref([])
const loading = ref(false)
const classifying = ref(false)
const currentPage = ref(1)
const pageSize = 12
const fileInput = ref(null)

const filters = ref({
  category: '',
  color: '',
  style: '',
  season: '',
  sort: 'newest',
})

const FILTER_OPTIONS = {
  category: ['上衣', '裤子', '裙子', '外套', '鞋子', '配饰'],
  color: ['黑', '白', '蓝', '红', '绿', '灰', '棕', '其他'],
  style: ['休闲', '正式', '运动', '街头', '简约', '复古'],
  season: ['春', '夏', '秋', '冬'],
}

const SORT_OPTIONS = [
  { value: 'newest', label: '最新上传' },
  { value: 'popular', label: '最常搭配' },
]

const hoveredItem = ref(null)

const fetchItems = async () => {
  loading.value = true
  try {
    const { data } = await getWardrobe()
    items.value = (data.data || data || []).map((item) => ({
      id: item.imageId || item.image_id || item.id,
      url: item.ossUrl || item.oss_url || item.url,
      name: item.description || item.filename || '未命名',
      tags: item.tags || {},
      uploadTime: item.uploadTime || item.upload_time || '',
    }))
  } catch (err) {
    ElMessage.error(err?.message || '加载衣橱失败')
  } finally {
    loading.value = false
  }
}

const triggerUpload = () => {
  fileInput.value?.click()
}

const onFileSelected = async (e) => {
  const file = e.target.files[0]
  if (!file) return
  try {
    loading.value = true
    await uploadMyImage(file)
    ElMessage.success('上传成功')
    await fetchItems()
  } catch (err) {
    ElMessage.error(err?.message || '上传失败')
  } finally {
    loading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

const deleteItem = async (id) => {
  if (!confirm('确定要删除这件衣物吗？')) return
  try {
    await deleteWardrobeItem(id)
    ElMessage.success('已删除')
    await fetchItems()
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

const classifyAll = async () => {
  if (!confirm('将使用AI对所有衣橱物品进行智能分类（品类/颜色/风格/季节），需要1-2分钟。继续？')) return
  classifying.value = true
  try {
    const userId = authStore.user?.userId || 'default'
    const { data } = await classifyWardrobe(userId)
    ElMessage.success(data?.message || '分类任务已启动')
    setTimeout(fetchItems, 5000)
  } catch (err) {
    ElMessage.error(err?.message || '分类失败')
  } finally {
    classifying.value = false
  }
}

const filteredItems = computed(() => {
  let result = [...items.value]

  if (filters.value.category) {
    result = result.filter((i) => i.tags?.category === filters.value.category)
  }
  if (filters.value.color) {
    result = result.filter((i) => i.tags?.color === filters.value.color)
  }
  if (filters.value.style) {
    result = result.filter((i) => i.tags?.style === filters.value.style)
  }
  if (filters.value.season) {
    result = result.filter((i) => i.tags?.season === filters.value.season)
  }

  if (filters.value.sort === 'popular') {
    result.sort((a, b) => (b.matchCount || 0) - (a.matchCount || 0))
  }
  // Items arrive from API sorted newest-first; only re-sort for popularity

  return result
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / pageSize)))

const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredItems.value.slice(start, start + pageSize)
})

const clearFilter = (key) => {
  filters.value[key] = ''
  currentPage.value = 1
}

watch(filters, () => { currentPage.value = 1 }, { deep: true })

const setPage = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
  }
}

const formatTime = (t) => {
  if (!t) return ''
  const d = new Date(t)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${m}-${day}`
}

onMounted(fetchItems)
</script>

<template>
  <div class="wardrobe-page">
    <div class="wardrobe-header">
      <h2 class="page-title">衣橱管理</h2>
      <button class="wardrobe-upload-btn" @click="triggerUpload">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        上传图片
      </button>
      <button class="wardrobe-upload-btn wardrobe-classify-btn" @click="classifyAll" :disabled="classifying">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10h-10V2z"/><path d="M12 2a10 10 0 0 1 10 10h-10V2z"/></svg>
        {{ classifying ? '分类中...' : '智能分类' }}
      </button>
      <input
        type="file"
        ref="fileInput"
        accept="image/*"
        class="chat-file-hidden"
        @change="onFileSelected"
      />
    </div>

    <div class="wardrobe-filters">
      <div v-for="(opts, key) in FILTER_OPTIONS" :key="key" class="filter-group">
        <span class="filter-label">{{ { category: '品类', color: '颜色', style: '风格', season: '季节' }[key] }}:</span>
        <div class="filter-chips">
          <button
            class="filter-chip"
            :class="{ active: !filters[key] }"
            @click="clearFilter(key)"
          >全部</button>
          <button
            v-for="opt in opts"
            :key="opt"
            class="filter-chip"
            :class="{ active: filters[key] === opt }"
            @click="filters[key] = filters[key] === opt ? '' : opt"
          >{{ opt }}</button>
        </div>
      </div>
      <div class="filter-group">
        <span class="filter-label">排序:</span>
        <select v-model="filters.sort" class="filter-select">
          <option v-for="s in SORT_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="wardrobe-loading">
      <div class="wardrobe-spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="!pagedItems.length" class="wardrobe-empty">
      <p>衣橱还是空的，上传你的第一件衣物吧</p>
    </div>

    <div v-else class="wardrobe-grid">
      <div
        v-for="item in pagedItems"
        :key="item.id"
        class="wardrobe-card"
        @mouseenter="hoveredItem = item.id"
        @mouseleave="hoveredItem = null"
      >
        <div class="wardrobe-card-img">
          <img :src="item.url" :alt="item.name" />
          <div v-if="hoveredItem === item.id" class="wardrobe-card-overlay">
            <div class="wardrobe-card-detail">
              <p class="wco-name">{{ item.name }}</p>
              <p v-if="item.tags?.category" class="wco-tag">品类: {{ item.tags.category }}</p>
              <p v-if="item.tags?.color" class="wco-tag">颜色: {{ item.tags.color }}</p>
              <p v-if="item.tags?.style" class="wco-tag">风格: {{ item.tags.style }}</p>
              <p v-if="item.tags?.season" class="wco-tag">季节: {{ item.tags.season }}</p>
              <p v-if="item.uploadTime" class="wco-time">上传: {{ formatTime(item.uploadTime) }}</p>
              <div class="wco-actions">
                <button class="wco-btn wco-btn-match">加入搭配</button>
                <button class="wco-btn wco-btn-del" @click="deleteItem(item.id)">删除</button>
              </div>
            </div>
          </div>
        </div>
        <div class="wardrobe-card-info">
          <p class="wci-name">{{ item.name }}</p>
          <p class="wci-tags">
            <span v-if="item.tags?.category">{{ item.tags.category }}</span>
            <span v-if="item.tags?.style"> / {{ item.tags.style }}</span>
            <span v-if="item.tags?.season"> / {{ item.tags.season }}</span>
          </p>
        </div>
      </div>
    </div>

    <div v-if="totalPages > 1" class="wardrobe-pagination">
      <button :disabled="currentPage === 1" @click="setPage(currentPage - 1)">&lt;</button>
      <span
        v-for="p in totalPages"
        :key="p"
        class="page-num"
        :class="{ active: p === currentPage }"
        @click="setPage(p)"
      >{{ p }}</span>
      <button :disabled="currentPage === totalPages" @click="setPage(currentPage + 1)">&gt;</button>
    </div>
  </div>
</template>

<style scoped>
.wardrobe-page {
  max-width: 960px;
  margin: 0 auto;
}

.wardrobe-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.wardrobe-upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: linear-gradient(135deg, #884BFF 0%, #7530FE 100%);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s;
}
.wardrobe-upload-btn:hover {
  opacity: 0.9;
}
.wardrobe-upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.wardrobe-classify-btn {
  background: linear-gradient(135deg, #12B76A 0%, #0E9F5C 100%);
}
.chat-file-hidden {
  display: none;
}

.wardrobe-filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
  margin-bottom: 12px;
  border-bottom: 1px solid #F0EBE3;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-label {
  font-size: 13px;
  color: #8B7355;
  min-width: 36px;
  flex-shrink: 0;
}
.filter-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.filter-chip {
  padding: 4px 10px;
  border: 1px solid #E8D5C0;
  border-radius: 14px;
  background: #fff;
  color: #8B7355;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-chip:hover {
  border-color: #C4A97D;
}
.filter-chip.active {
  background: #F5E6D3;
  border-color: #C4A97D;
  color: #5C4A3A;
}
.filter-select {
  padding: 4px 8px;
  border: 1px solid #E8D5C0;
  border-radius: 6px;
  font-size: 12px;
  color: #5C4A3A;
  outline: none;
  background: #fff;
  cursor: pointer;
}

.wardrobe-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #8B7355;
  font-size: 14px;
}
.wardrobe-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #E8D5C0;
  border-top-color: #884BFF;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin-bottom: 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.wardrobe-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #B8A088;
  font-size: 14px;
}

.wardrobe-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 780px) {
  .wardrobe-grid { grid-template-columns: repeat(2, 1fr); }
}
.wardrobe-card {
  background: #fff;
  border: 1px solid #F0EBE3;
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s;
}
.wardrobe-card:hover {
  box-shadow: 0 4px 16px rgba(92, 74, 58, 0.08);
}
.wardrobe-card-img {
  position: relative;
  aspect-ratio: 3/4;
  background: #FDF8F2;
  overflow: hidden;
}
.wardrobe-card-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.wardrobe-card-overlay {
  position: absolute;
  inset: 0;
  background: rgba(92, 74, 58, 0.85);
  display: flex;
  align-items: flex-end;
  padding: 12px;
}
.wardrobe-card-detail {
  width: 100%;
  color: #fff;
  font-size: 12px;
}
.wco-name {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
}
.wco-tag {
  margin: 0 0 2px;
  opacity: 0.8;
}
.wco-time {
  margin: 4px 0 8px;
  opacity: 0.6;
}
.wco-actions {
  display: flex;
  gap: 6px;
}
.wco-btn {
  flex: 1;
  padding: 5px 0;
  border: none;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  text-align: center;
  transition: opacity 0.2s;
}
.wco-btn-match {
  background: #C4A97D;
  color: #fff;
}
.wco-btn-del {
  background: rgba(255,255,255,0.15);
  color: #fff;
}
.wco-btn:hover {
  opacity: 0.85;
}
.wardrobe-card-info {
  padding: 8px 10px;
}
.wci-name {
  margin: 0;
  font-size: 13px;
  color: #5C4A3A;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wci-tags {
  margin: 2px 0 0;
  font-size: 11px;
  color: #B8A088;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wardrobe-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 20px;
}
.wardrobe-pagination button {
  width: 30px;
  height: 30px;
  border: 1px solid #E8D5C0;
  border-radius: 6px;
  background: #fff;
  color: #8B7355;
  cursor: pointer;
  font-size: 13px;
  transition: border-color 0.2s;
}
.wardrobe-pagination button:hover:not(:disabled) {
  border-color: #C4A97D;
}
.wardrobe-pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.page-num {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 13px;
  color: #8B7355;
  cursor: pointer;
  transition: background 0.2s;
}
.page-num:hover { background: #FDF8F2; }
.page-num.active {
  background: #F5E6D3;
  color: #5C4A3A;
  font-weight: 600;
}
</style>
