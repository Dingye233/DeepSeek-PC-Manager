<template>
  <div 
    class="message-item" 
    :class="{ 
      'message-user': message.role === 'user',
      'message-assistant': message.role === 'assistant',
      'message-system': message.role === 'system',
      'message-error': message.isError
    }"
  >
    <div class="message-avatar">
      <el-avatar 
        :size="40" 
        :icon="avatarIcon" 
        :src="avatarSrc"
        :class="{ 'user-avatar': message.role === 'user' }"
      />
    </div>
    
    <div class="message-body">
      <div class="message-header">
        <span class="message-role">{{ roleLabel }}</span>
        <span class="message-time">{{ formattedTime }}</span>
      </div>
      
      <div class="message-content">
        <!-- 使用Markdown渲染内容 -->
        <markdown-renderer 
          v-if="message.role === 'assistant' && !message.isError" 
          :content="message.content" 
        />
        <!-- 普通文本内容 -->
        <div v-else>{{ message.content }}</div>
      </div>
      
      <!-- 工具调用区块 -->
      <div v-if="message.toolCalls && message.toolCalls.length > 0" class="tool-calls">
        <div class="tool-calls-header">
          <span class="material-symbols-rounded icon">build</span>
          工具调用
        </div>
        <ul class="tools-list">
          <li 
            v-for="tool in message.toolCalls" 
            :key="tool.id" 
            class="tool-item"
          >
            <div class="tool-info">
              <span class="tool-name">{{ tool.name }}</span>
              <span 
                class="tool-status"
                :class="{
                  'success': tool.status === 'completed',
                  'error': tool.status === 'error'
                }"
              >
                {{ getToolStatusText(tool.status) }}
              </span>
            </div>
            
            <div v-if="tool.result" class="tool-result">
              <span class="material-symbols-rounded icon">check_circle</span>
              {{ truncateResult(tool.result) }}
            </div>
          </li>
        </ul>
      </div>
      
      <!-- 任务规划区块 -->
      <div v-if="message.taskPlanning" class="task-planning">
        <div class="task-planning-header">
          <span class="material-symbols-rounded icon">psychology</span>
          思考过程
        </div>
        <div class="task-planning-content">{{ message.taskPlanning }}</div>
      </div>
    </div>
  </div>
</template>

<script>
import { computed } from 'vue'
import { format } from 'date-fns'
import zhCN from 'date-fns/locale/zh-CN'

export default {
  name: 'MessageItem',
  props: {
    message: {
      type: Object,
      required: true
    }
  },
  setup(props) {
    // 角色标签
    const roleLabel = computed(() => {
      const roles = {
        'user': '用户',
        'assistant': 'AI助手',
        'system': '系统消息'
      }
      return roles[props.message.role] || props.message.role
    })
    
    // 头像图标
    const avatarIcon = computed(() => {
      const icons = {
        'user': 'el-icon-user',
        'assistant': 'el-icon-s-custom',
        'system': 'el-icon-info'
      }
      return icons[props.message.role] || 'el-icon-s-comment'
    })
    
    // 头像源
    const avatarSrc = computed(() => {
      const sources = {
        'assistant': '/img/ai-avatar.png'
      }
      return sources[props.message.role] || ''
    })
    
    // 格式化时间
    const formattedTime = computed(() => {
      try {
        const date = new Date(props.message.timestamp)
        return format(date, 'HH:mm:ss', { locale: zhCN })
      } catch (e) {
        return ''
      }
    })
    
    // 获取工具状态文本
    const getToolStatusText = (status) => {
      const statusMap = {
        'pending': '等待中',
        'running': '执行中',
        'completed': '已完成',
        'error': '错误'
      }
      return statusMap[status] || status
    }
    
    // 截断结果文本
    const truncateResult = (result) => {
      if (typeof result !== 'string') return JSON.stringify(result).substring(0, 100)
      return result.length > 100 ? result.substring(0, 100) + '...' : result
    }
    
    return {
      roleLabel,
      avatarIcon,
      avatarSrc,
      formattedTime,
      getToolStatusText,
      truncateResult
    }
  }
}
</script>

<style lang="scss" scoped>
.message-item {
  display: flex;
  margin-bottom: 1.5rem;
  animation: fadeIn 0.3s ease;
  
  &.message-user {
    .message-body {
      background-color: var(--primary-light);
      border-color: var(--primary-hover);
    }
    
    .message-role {
      color: var(--primary-color);
    }
  }
  
  &.message-assistant {
    .message-body {
      background-color: var(--bg-primary);
    }
  }
  
  &.message-system, &.message-error {
    .message-body {
      background-color: var(--bg-tertiary);
      border-color: var(--info-color);
    }
    
    &.message-error .message-body {
      border-color: var(--error-color);
    }
  }
}

.message-avatar {
  margin-right: 12px;
  
  .user-avatar {
    background-color: var(--primary-color);
  }
}

.message-body {
  flex: 1;
  background-color: var(--bg-primary);
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-color);
  max-width: calc(100% - 60px);
  overflow-wrap: break-word;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.message-role {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.message-time {
  font-size: 0.75rem;
  color: var(--text-quaternary);
}

.message-content {
  color: var(--text-primary);
}

.tool-calls, .task-planning {
  margin-top: 16px;
  padding: 12px;
  border-radius: 8px;
  background-color: var(--bg-secondary);
  border-left: 3px solid var(--primary-color);
  font-size: 0.9rem;
}

.tool-calls-header, .task-planning-header {
  display: flex;
  align-items: center;
  font-weight: 600;
  color: var(--primary-color);
  margin-bottom: 8px;
}

.icon {
  margin-right: 6px;
  font-size: 1.1rem;
}

.tools-list {
  list-style-type: none;
  padding-left: 24px;
}

.tool-item {
  position: relative;
  padding: 6px 0;
  
  &:before {
    content: '•';
    position: absolute;
    left: -12px;
    color: var(--primary-color);
  }
}

.tool-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tool-name {
  font-weight: 500;
}

.tool-status {
  font-size: 0.8rem;
  padding: 2px 6px;
  border-radius: 4px;
  background-color: var(--bg-tertiary);
  color: var(--text-tertiary);
  
  &.success {
    color: var(--success-color);
    background-color: rgba(16, 185, 129, 0.1);
  }
  
  &.error {
    color: var(--error-color);
    background-color: rgba(239, 68, 68, 0.1);
  }
}

.tool-result {
  margin-top: 6px;
  padding: 8px 10px;
  background-color: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  
  .icon {
    color: var(--success-color);
    font-size: 0.9rem;
  }
}

.task-planning-content {
  white-space: pre-line;
  color: var(--text-secondary);
  padding-left: 12px;
  font-size: 0.85rem;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style> 