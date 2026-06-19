<script setup>
import { RouterLink, useRoute } from 'vue-router'
import iconEdit from '../assets/image/menu-edit.svg'
import iconMerge from '../assets/image/menu-merge.svg'
import iconMyImage from '../assets/image/menu-my-image.svg'
import iconHistory from '../assets/image/menu-history.svg'

const route = useRoute()
</script>

<template>
  <aside class="sider">
    <div class="sider-logo">
      <span class="sider-logo-text">AIWear</span>
    </div>

    <nav class="menu">
      <RouterLink to="/chat" class="menu-item" :class="{ active: route.path === '/chat' }">
        <span class="mi-ico">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </span>
        <span>智能搭配</span>
      </RouterLink>
      <RouterLink to="/wardrobe" class="menu-item" :class="{ active: route.path === '/wardrobe' }">
        <span class="mi-ico">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
        </span>
        <span>衣橱管理</span>
      </RouterLink>
      <RouterLink to="/images" class="menu-item" :class="{ active: route.path === '/images' }">
        <span class="mi-ico"><img :src="iconMyImage" alt="" /></span>
        <span>我的图片</span>
      </RouterLink>
      <RouterLink to="/records" class="menu-item" :class="{ active: route.path === '/records' }">
        <span class="mi-ico"><img :src="iconHistory" alt="" /></span>
        <span>历史记录</span>
      </RouterLink>

      <div class="menu-divider"></div>

      <RouterLink to="/edit" class="menu-item" :class="{ active: route.path === '/edit' }">
        <span class="mi-ico"><img :src="iconEdit" alt="" /></span>
        <span>图片编辑</span>
      </RouterLink>
      <RouterLink to="/merge" class="menu-item" :class="{ active: route.path === '/merge' }">
        <span class="mi-ico"><img :src="iconMerge" alt="" /></span>
        <span>图片合并</span>
      </RouterLink>

      <div class="menu-spacer"></div>


      <RouterLink to="/dashboard" class="menu-item menu-item-bottom" :class="{ active: route.path === '/dashboard' }">
        <span class="mi-ico">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
        </span>
        <span>控制面板</span>
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
.sider {
  position: sticky;
  top: 0;
  width: 152px;
  height: 100vh;
  padding: 16px 12px;
  background: linear-gradient(180deg, #f0f2f8 0%, #faf8fc 50%, #ffffff 100%);
  border-right: 1px solid rgba(16, 24, 40, 0.08);
  backdrop-filter: blur(10px);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sider-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px 0 16px;
}
.sider-logo-text {
  font-size: 18px;
  font-weight: 800;
  color: #6b3cff;
  letter-spacing: 1px;
}

.menu {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
  flex: 1;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 10px;
  border-radius: 10px;
  color: rgba(16, 24, 40, 0.72);
  border: none;
  transition: background 0.2s ease, color 0.2s ease;
  text-decoration: none;
  font-size: 14px;
}
.menu-item:hover {
  background: rgba(123, 85, 255, 0.06);
  color: rgba(16, 24, 40, 0.88);
}
.menu-item.active {
  background: rgba(123, 85, 255, 0.12);
  color: rgba(16, 24, 40, 0.88);
}
.mi-ico {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: inherit;
}
.menu-item .mi-ico img {
  width: 18px;
  height: 18px;
  object-fit: contain;
  display: block;
}
.menu-item:not(.active) .mi-ico img {
  opacity: 0.6;
}
.menu-item.active .mi-ico img {
  opacity: 1;
}

.menu-divider {
  height: 1px;
  background: rgba(16, 24, 40, 0.08);
  margin: 6px 8px;
}

.menu-spacer {
  flex: 1;
}

.menu-item-bottom {
  margin-top: auto;
}

@media (max-width: 980px) {
  .sider {
    position: relative;
    height: auto;
  }
}
</style>
