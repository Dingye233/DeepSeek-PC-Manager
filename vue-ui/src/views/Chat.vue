<template>
  <div class="chat-view">
    <!-- 聊天页面头部 -->
    <header class="chat-header">
      <div class="header-left">
        <el-button 
          class="back-button" 
          icon="el-icon-arrow-left" 
          size="small" 
          circle 
          @click="goToHome" 
        />
        <h1 class="chat-title">{{ chatTitle }}</h1>
      </div>
      
      <div class="header-actions">
        <el-button 
          icon="el-icon-delete"
          size="small"
          @click="confirmClearChat"
          :disabled="!currentChat || !currentChat.messages.length"
        >
          清空记录
        </el-button>
        
        <el-button 
          icon="el-icon-refresh"
          type="primary"
          size="small"
          @click="createNewChat"
        >
          新对话
        </el-button>
      </div>
    </header>
    
    <!-- 聊天内容区域 -->
    <main class="chat-main" ref="chatContainerRef">
      <div v-if="!currentChat || !currentChat.messages.length" class="empty-chat">
        <div class="empty-icon">
          <span class="material-symbols-rounded">chat</span>
        </div>
        <h2>开始一个新的对话</h2>
        <p>您可以向AI助手询问任何问题，或者请求执行各种任务。</p>
      </div>
      
      <template v-else>
        <message-item 
          v-for="message in currentChat.messages" 
          :key="message.id"
          :message="message"
        />
      </template>
      
      <!-- 思考状态指示器 -->
      <div 
        v-if="isThinking" 
        class="thinking-indicator"
      >
        <span class="material-symbols-rounded icon">psychology</span>
        AI正在思考并处理您的请求...
      </div>
    </main>
    
    <!-- 输入区域 -->
    <footer class="chat-footer">
      <div class="input-container">
        <el-input
          v-model="messageInput"
          type="textarea"
          autosize
          placeholder="输入您的问题或指令..."
          :disabled="isProcessing"
          @keydown.enter.exact.prevent="sendMessage"
        />
        
        <el-button 
          class="send-button"
          type="primary"
          icon="el-icon-s-promotion"
          :loading="isProcessing"
          :disabled="!messageInput.trim() || isProcessing"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>
      
      <div class="input-hints">
        <p>按 Enter 发送，Shift + Enter 换行</p>
      </div>
    </footer>
  </div>
</template>

<script>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useStore } from 'vuex'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import MessageItem from '@/components/MessageItem.vue'

export default {
  name: 'ChatView',
  components: {
    MessageItem
  },
  setup() {
    const store = useStore()
    const router = useRouter()
    const route = useRoute()
    
    // 响应式数据
    const messageInput = ref('')
    const chatContainerRef = ref(null)
    
    // 从Vuex获取状态
    const currentChat = computed(() => store.getters.currentChat)
    const isProcessing = computed(() => store.state.isProcessing)
    const isThinking = computed(() => store.state.isThinking)
    
    // 聊天标题
    const chatTitle = computed(() => {
      if (!currentChat.value) return '新对话'
      return currentChat.value.title || '新对话'
    })
    
    // 初始化
    onMounted(async () => {
      // 检查路由参数
      const chatId = route.params.id
      
      if (chatId) {
        store.commit('SET_CURRENT_CHAT', chatId)
      } else if (!store.state.currentChatId) {
        // 如果没有当前对话，创建一个新的
        await store.dispatch('createNewChat')
      }
      
      // 滚动到底部
      scrollToBottom()
    })
    
    // 监听消息变化，自动滚动到底部
    watch(() => currentChat.value?.messages.length, () => {
      nextTick(scrollToBottom)
    })
    
    // 滚动到底部
    const scrollToBottom = () => {
      if (chatContainerRef.value) {
        chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight
      }
    }
    
    // 返回主页
    const goToHome = () => {
      router.push('/')
    }
    
    // 创建新对话
    const createNewChat = async () => {
      await store.dispatch('createNewChat')
      messageInput.value = ''
      nextTick(scrollToBottom)
    }
    
    // 发送消息
    const sendMessage = async () => {
      if (!messageInput.value.trim() || isProcessing.value) return
      
      const message = messageInput.value
      messageInput.value = ''
      
      try {
        await store.dispatch('sendMessage', message)
        nextTick(scrollToBottom)
      } catch (error) {
        ElMessage.error('发送消息失败，请重试')
        console.error('发送消息错误:', error)
      }
    }
    
    // 确认清空对话
    const confirmClearChat = () => {
      ElMessageBox.confirm(
        '确定要清空当前对话吗？此操作不可恢复。',
        '确认清空',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      ).then(() => {
        if (currentChat.value) {
          store.commit('DELETE_CHAT', currentChat.value.id)
          ElMessage.success('对话已清空')
        }
      }).catch(() => {})
    }
    
    return {
      messageInput,
      chatContainerRef,
      currentChat,
      isProcessing,
      isThinking,
      chatTitle,
      goToHome,
      createNewChat,
      sendMessage,
      confirmClearChat
    }
  }
}
</script>

<style lang="scss" scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: var(--bg-secondary);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background-color: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
  z-index: 10;
  
  .header-left {
    display: flex;
    align-items: center;
  }
  
  .back-button {
    margin-right: 12px;
  }
  
  .chat-title {
    font-size: 1.1rem;
    font-weight: 600;
    margin: 0;
    color: var(--text-primary);
  }
  
  .header-actions {
    display: flex;
    gap: 8px;
  }
}

.chat-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  
  .empty-chat {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-tertiary);
    text-align: center;
    padding: 0 20px;
    
    .empty-icon {
      font-size: 4rem;
      margin-bottom: 16px;
      color: var(--primary-color);
      opacity: 0.5;
      
      .material-symbols-rounded {
        font-size: inherit;
      }
    }
    
    h2 {
      font-size: 1.5rem;
      font-weight: 600;
      margin-bottom: 8px;
      color: var(--text-secondary);
    }
    
    p {
      font-size: 1rem;
      max-width: 400px;
    }
  }
}

.thinking-indicator {
  display: flex;
  align-items: center;
  align-self: flex-start;
  padding: 10px 16px;
  background-color: var(--primary-color);
  color: white;
  border-radius: 12px;
  margin: 8px 0;
  font-size: 0.95rem;
  box-shadow: var(--shadow-sm);
  animation: bounce 2s infinite;
  
  .icon {
    margin-right: 8px;
  }
}

.chat-footer {
  padding: 16px 24px;
  background-color: var(--bg-primary);
  border-top: 1px solid var(--border-color);
  
  .input-container {
    display: flex;
    gap: 12px;
    
    .el-textarea {
      flex: 1;
      
      :deep(.el-textarea__inner) {
        min-height: 50px;
        max-height: 150px;
        resize: none;
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 1rem;
        line-height: 1.5;
        border-color: var(--border-color);
        background-color: var(--bg-primary);
        color: var(--text-primary);
        
        &:focus {
          border-color: var(--primary-color);
          box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.2);
        }
      }
    }
    
    .send-button {
      align-self: flex-end;
    }
  }
  
  .input-hints {
    margin-top: 8px;
    font-size: 0.75rem;
    color: var(--text-quaternary);
    text-align: right;
  }
}

@keyframes bounce {
  0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-5px); }
  60% { transform: translateY(-2px); }
}

// 响应式样式
@media (max-width: 768px) {
  .chat-header {
    padding: 8px 16px;
    
    .chat-title {
      font-size: 1rem;
    }
  }
  
  .chat-main {
    padding: 16px;
  }
  
  .chat-footer {
    padding: 12px 16px;
  }
}
</style> 