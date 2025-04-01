import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

/**
 * 发送聊天消息
 * @param {string} message - 用户消息内容
 * @returns {Promise} - 返回Promise对象
 */
export const sendMessage = (message) => {
  return api.post('/chat', { message })
}

/**
 * 创建流式连接
 * @returns {Promise} - 返回Promise对象
 */
export const createStream = () => {
  return api.get('/stream')
}

/**
 * 开始流式处理用户消息
 * @param {string} message - 用户消息内容
 * @returns {Promise} - 返回Promise对象
 */
export const startStream = (message) => {
  return api.post('/stream', { message })
}

/**
 * 获取聊天历史
 * @returns {Promise} - 返回Promise对象
 */
export const getChatHistory = () => {
  return api.get('/history')
}

/**
 * 清除聊天历史
 * @returns {Promise} - 返回Promise对象
 */
export const clearChatHistory = () => {
  return api.delete('/history')
}

export default {
  sendMessage,
  createStream,
  startStream,
  getChatHistory,
  clearChatHistory
} 