import { createStore } from 'vuex'

export default createStore({
  state: {
    // 用户信息
    user: null,
    // 聊天历史
    chats: [],
    // 当前聊天ID
    currentChatId: null,
    // 正在处理中
    isProcessing: false,
    // 思考状态
    isThinking: false,
    // 深色模式
    darkMode: false
  },
  
  getters: {
    // 当前聊天记录
    currentChat: (state) => {
      if (!state.currentChatId) return null
      return state.chats.find(chat => chat.id === state.currentChatId) || null
    },
    
    // 所有聊天列表
    chatList: (state) => {
      return state.chats.map(chat => ({
        id: chat.id,
        title: chat.title,
        updatedAt: chat.updatedAt,
        preview: chat.messages.length > 0 
          ? chat.messages[chat.messages.length - 1].content.substring(0, 30) 
          : '新对话'
      }))
    }
  },
  
  mutations: {
    SET_USER(state, user) {
      state.user = user
    },
    
    SET_DARK_MODE(state, isDark) {
      state.darkMode = isDark
    },
    
    SET_PROCESSING(state, isProcessing) {
      state.isProcessing = isProcessing
    },
    
    SET_THINKING(state, isThinking) {
      state.isThinking = isThinking
    },
    
    CREATE_CHAT(state, chat) {
      state.chats.unshift(chat)
      state.currentChatId = chat.id
    },
    
    SET_CURRENT_CHAT(state, chatId) {
      state.currentChatId = chatId
    },
    
    ADD_MESSAGE(state, { chatId, message }) {
      const chat = state.chats.find(c => c.id === chatId)
      if (chat) {
        chat.messages.push(message)
        chat.updatedAt = new Date().toISOString()
      }
    },
    
    UPDATE_MESSAGE(state, { chatId, messageId, content }) {
      const chat = state.chats.find(c => c.id === chatId)
      if (chat) {
        const message = chat.messages.find(m => m.id === messageId)
        if (message) {
          message.content = content
        }
      }
    },
    
    DELETE_CHAT(state, chatId) {
      const index = state.chats.findIndex(chat => chat.id === chatId)
      if (index !== -1) {
        state.chats.splice(index, 1)
        if (state.currentChatId === chatId) {
          state.currentChatId = state.chats.length > 0 ? state.chats[0].id : null
        }
      }
    },
    
    CLEAR_CHATS(state) {
      state.chats = []
      state.currentChatId = null
    }
  },
  
  actions: {
    // 创建新对话
    createNewChat({ commit }) {
      const newChat = {
        id: Date.now().toString(),
        title: '新对话',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: []
      }
      commit('CREATE_CHAT', newChat)
      return newChat
    },
    
    // 发送消息
    async sendMessage({ commit, state }, message) {
      if (!state.currentChatId) {
        const newChat = await dispatch('createNewChat')
        commit('SET_CURRENT_CHAT', newChat.id)
      }
      
      // 添加用户消息
      const userMessage = {
        id: Date.now().toString(),
        role: 'user',
        content: message,
        timestamp: new Date().toISOString()
      }
      
      commit('ADD_MESSAGE', {
        chatId: state.currentChatId,
        message: userMessage
      })
      
      // 设置处理中状态
      commit('SET_PROCESSING', true)
      commit('SET_THINKING', true)
      
      try {
        // 调用API获取AI回复
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ message })
        })
        
        const data = await response.json()
        
        // 添加AI回复
        const assistantMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: data.text,
          html: data.html,
          timestamp: new Date().toISOString(),
          toolCalls: data.tool_calls,
          taskPlanning: data.task_planning
        }
        
        commit('ADD_MESSAGE', {
          chatId: state.currentChatId,
          message: assistantMessage
        })
        
        return assistantMessage
      } catch (error) {
        console.error('发送消息错误:', error)
        // 添加错误消息
        const errorMessage = {
          id: Date.now().toString(),
          role: 'system',
          content: '抱歉，发送消息时出现了错误，请稍后再试。',
          timestamp: new Date().toISOString(),
          isError: true
        }
        
        commit('ADD_MESSAGE', {
          chatId: state.currentChatId,
          message: errorMessage
        })
        
        return errorMessage
      } finally {
        commit('SET_PROCESSING', false)
        commit('SET_THINKING', false)
      }
    }
  }
}) 