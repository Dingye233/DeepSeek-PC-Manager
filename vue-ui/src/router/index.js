import { createRouter, createWebHistory } from 'vue-router'

// 页面组件
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { title: 'DeepSeek AI 助手' }
  },
  {
    path: '/chat/:id?',
    name: 'Chat',
    component: () => import('@/views/Chat.vue'),
    meta: { title: '聊天 | DeepSeek AI 助手' }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
    meta: { title: '设置 | DeepSeek AI 助手' }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '页面未找到 | DeepSeek AI 助手' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 动态设置标题
router.beforeEach((to, from, next) => {
  if (to.meta.title) {
    document.title = to.meta.title
  }
  next()
})

export default router 