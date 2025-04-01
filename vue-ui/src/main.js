import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import './styles/main.scss'

// 创建应用实例
const app = createApp(App)

// 注册全局组件
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
app.component('MarkdownRenderer', MarkdownRenderer)

// 使用插件
app.use(store)
app.use(router)
app.use(ElementPlus, {
  locale: zhCn,
  size: 'default'
})

// 挂载应用
app.mount('#app') 