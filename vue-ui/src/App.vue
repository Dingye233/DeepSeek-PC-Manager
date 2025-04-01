<template>
  <div class="app-container" :class="{ 'dark-mode': isDarkMode }">
    <el-config-provider :locale="zhCn">
      <router-view />
    </el-config-provider>
  </div>
</template>

<script>
import { ref, computed, onMounted, provide } from 'vue'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/lib/locale/lang/zh-cn'

export default {
  name: 'App',
  components: {
    ElConfigProvider
  },
  setup() {
    const isDarkMode = ref(false)
    
    // 检测系统主题偏好
    const detectColorScheme = () => {
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        isDarkMode.value = true
      }
    }
    
    // 切换主题
    const toggleDarkMode = () => {
      isDarkMode.value = !isDarkMode.value
      localStorage.setItem('darkMode', isDarkMode.value ? 'true' : 'false')
      document.documentElement.setAttribute('data-theme', isDarkMode.value ? 'dark' : 'light')
    }
    
    // 恢复用户主题设置
    onMounted(() => {
      const savedTheme = localStorage.getItem('darkMode')
      if (savedTheme === null) {
        detectColorScheme()
      } else {
        isDarkMode.value = savedTheme === 'true'
      }
      document.documentElement.setAttribute('data-theme', isDarkMode.value ? 'dark' : 'light')
    })
    
    // 提供全局方法和状态
    provide('toggleDarkMode', toggleDarkMode)
    provide('isDarkMode', computed(() => isDarkMode.value))
    
    return {
      isDarkMode,
      toggleDarkMode,
      zhCn
    }
  }
}
</script>

<style lang="scss">
.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: background-color 0.3s ease;
}
</style> 