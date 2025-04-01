/**
 * AI助手 - 前端交互脚本
 * 处理用户输入、消息展示和API通信
 */

// DOM元素
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const clearButton = document.getElementById('clear-button');
const thinkingIndicator = document.getElementById('thinking');

// 状态变量
let isProcessing = false;
let eventSource = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 自动聚焦输入框
    userInput.focus();
    
    // 加载历史记录
    loadChatHistory();
    
    // 设置事件监听器
    setupEventListeners();
});

// 设置事件监听器
function setupEventListeners() {
    // 发送按钮点击
    sendButton.addEventListener('click', sendMessage);
    
    // 输入框回车键
    userInput.addEventListener('keydown', (e) => {
        // 检测Enter键（不按Shift）
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
        
        // 调整输入框高度
        setTimeout(() => {
            userInput.style.height = 'auto';
            userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
        }, 0);
    });
    
    // 清除历史按钮
    clearButton.addEventListener('click', clearHistory);
}

// 发送消息
function sendMessage() {
    const message = userInput.value.trim();
    
    // 验证消息
    if (!message || isProcessing) {
        return;
    }
    
    // 显示用户消息
    appendMessage('user', message);
    
    // 清空输入框并重置高度
    userInput.value = '';
    userInput.style.height = '50px';
    
    // 设置处理状态
    isProcessing = true;
    if (thinkingIndicator) thinkingIndicator.classList.add('visible');
    sendButton.disabled = true;
    
    // 首先尝试流式API
    fetch('/api/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'processing' && data.stream_url) {
            // 使用SSE连接获取流式更新
            connectToStream(data.stream_url);
        } else {
            // 回退到常规API
            fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message }),
            })
            .then(response => response.json())
            .then(data => {
                // 添加AI回复
                appendMessage('assistant', data.text, data.html, data.tool_calls, data.task_planning);
            })
            .catch(error => {
                console.error('Error sending message:', error);
                showError('发送消息失败，请重试');
            })
            .finally(() => {
                resetState();
            });
        }
    })
    .catch(error => {
        console.error('Error starting stream:', error);
        showError('启动流式连接失败，尝试使用常规API');
        
        // 回退到常规API
        fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message }),
        })
        .then(response => response.json())
        .then(data => {
            // 添加AI回复
            appendMessage('assistant', data.text, data.html, data.tool_calls, data.task_planning);
        })
        .catch(error => {
            console.error('Error sending message:', error);
            showError('发送消息失败，请重试');
        })
        .finally(() => {
            resetState();
        });
    });
}

// 连接到流式更新
function connectToStream(streamUrl) {
    // 关闭现有连接
    if (eventSource) {
        eventSource.close();
    }
    
    // 创建消息元素但不立即显示内容
    const messageId = 'ai-message-' + Date.now();
    const messageElement = createEmptyMessageElement('assistant', messageId);
    chatMessages.appendChild(messageElement);
    scrollToBottom();
    
    // 工具和任务区域
    let toolCallsAdded = false;
    let taskPlanningAdded = false;
    
    // 当前消息内容
    let currentContent = '';
    
    // 连接到流式更新
    eventSource = new EventSource(streamUrl);
    
    // 处理消息
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            // 处理错误
            if (data.type === 'error') {
                showError(data.text || '流式连接错误');
                eventSource.close();
                resetState();
                return;
            }
            
            // 处理任务规划
            if (data.task_planning && data.task_planning.has_plan && !taskPlanningAdded) {
                const taskElement = createTaskPlanningElement(data.task_planning.plan_text);
                messageElement.querySelector('.message-content').appendChild(taskElement);
                taskPlanningAdded = true;
                scrollToBottom();
            }
            
            // 处理工具调用
            if (data.tool_calls && data.tool_calls.length > 0 && !toolCallsAdded) {
                const toolsElement = createToolCallsElement(data.tool_calls);
                messageElement.querySelector('.message-content').appendChild(toolsElement);
                toolCallsAdded = true;
                scrollToBottom();
            }
            
            // 更新消息内容
            if (data.type === 'assistant' && data.text) {
                currentContent = data.text;
                // 移除多余的工具调用和任务规划描述
                if (toolCallsAdded || taskPlanningAdded) {
                    // 简化消息内容，移除工具调用和任务规划的描述
                    currentContent = simplifyContent(currentContent, data.tool_calls, data.task_planning);
                }
                updateMessageContent(messageId, currentContent);
                scrollToBottom();
            }
            
            // 完成处理
            if (data.type === 'complete') {
                eventSource.close();
                resetState();
            }
        } catch (error) {
            console.error('Error processing stream data:', error);
            showError('处理流式数据时出错');
            eventSource.close();
            resetState();
        }
    };
    
    // 处理错误
    eventSource.onerror = () => {
        showError('流式连接中断');
        eventSource.close();
        resetState();
    };
}

// 创建空的消息元素
function createEmptyMessageElement(role, id) {
    const messageElement = document.createElement('div');
    messageElement.className = `message message-${role}`;
    messageElement.id = id;
    
    // 消息内容
    const contentElement = document.createElement('div');
    contentElement.className = 'message-content';
    
    // 时间戳
    const timeElement = document.createElement('div');
    timeElement.className = 'message-time';
    timeElement.textContent = new Date().toLocaleTimeString();
    
    // 添加到消息元素
    messageElement.appendChild(contentElement);
    messageElement.appendChild(timeElement);
    
    return messageElement;
}

// 更新消息内容
function updateMessageContent(messageId, content) {
    const messageElement = document.getElementById(messageId);
    if (messageElement) {
        const contentElement = messageElement.querySelector('.message-content');
        // 使用markdown渲染
        const htmlContent = formatMarkdown(content);
        contentElement.innerHTML = htmlContent;
    }
}

// 简单的Markdown格式化
function formatMarkdown(text) {
    // 替换代码块
    let html = text.replace(/```(\w+)?\n([\s\S]*?)\n```/g, '<pre><code class="language-$1">$2</code></pre>');
    
    // 替换行内代码
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // 替换标题
    html = html.replace(/^# (.*)/gm, '<h1>$1</h1>');
    html = html.replace(/^## (.*)/gm, '<h2>$1</h2>');
    html = html.replace(/^### (.*)/gm, '<h3>$1</h3>');
    
    // 替换列表
    html = html.replace(/^\* (.*)/gm, '<li>$1</li>');
    html = html.replace(/^\d+\. (.*)/gm, '<li>$1</li>');
    
    // 替换段落
    html = html.replace(/\n\n/g, '</p><p>');
    
    // 包装成段落
    html = '<p>' + html + '</p>';
    
    return html;
}

// 创建任务规划元素
function createTaskPlanningElement(planText) {
    const planElement = document.createElement('div');
    planElement.className = 'task-planning';
    
    const planHeader = document.createElement('div');
    planHeader.className = 'task-planning-header';
    planHeader.innerHTML = '<span class="icon">📋</span> 任务规划';
    
    const planContent = document.createElement('div');
    planContent.className = 'task-planning-content';
    planContent.textContent = planText;
    
    planElement.appendChild(planHeader);
    planElement.appendChild(planContent);
    
    return planElement;
}

// 创建工具调用元素
function createToolCallsElement(toolCalls) {
    const toolsElement = document.createElement('div');
    toolsElement.className = 'tool-calls';
    
    const toolsHeader = document.createElement('div');
    toolsHeader.className = 'tool-calls-header';
    toolsHeader.innerHTML = '<span class="icon">🔧</span> 工具调用';
    
    const toolsList = document.createElement('ul');
    toolsList.className = 'tools-list';
    
    toolCalls.forEach(tool => {
        const toolItem = document.createElement('li');
        toolItem.className = 'tool-item';
        toolItem.textContent = tool.tool;
        toolsList.appendChild(toolItem);
    });
    
    toolsElement.appendChild(toolsHeader);
    toolsElement.appendChild(toolsList);
    
    return toolsElement;
}

// 简化内容，移除工具调用和任务规划描述
function simplifyContent(content, toolCalls, taskPlanning) {
    let result = content;
    
    // 移除工具调用描述
    if (toolCalls && toolCalls.length > 0) {
        toolCalls.forEach(tool => {
            const pattern = new RegExp(`(调用工具[：:]\\s*\`${tool.tool}\`.*?\\n)|(使用工具[：:]\\s*\`${tool.tool}\`.*?\\n)|(执行命令[：:]\\s*\`${tool.tool}\`.*?\\n)|(运行命令[：:]\\s*\`${tool.tool}\`.*?\\n)`, 'g');
            result = result.replace(pattern, '');
        });
    }
    
    // 移除任务规划描述
    if (taskPlanning && taskPlanning.has_plan) {
        const planPattern = /(任务计划[：:].*?)(?=\n\n|$)|(计划步骤[：:].*?)(?=\n\n|$)|(我将按照以下步骤.*?)(?=\n\n|$)/s;
        result = result.replace(planPattern, '');
    }
    
    return result;
}

// 添加消息到聊天界面
function appendMessage(role, content, html = null, toolCalls = null, taskPlanning = null) {
    const messageElement = createMessageElement(role, content, html, toolCalls, taskPlanning);
    chatMessages.appendChild(messageElement);
    scrollToBottom();
}

// 创建消息元素
function createMessageElement(role, content, html = null, toolCalls = null, taskPlanning = null) {
    const messageElement = document.createElement('div');
    messageElement.className = `message message-${role}`;
    
    // 消息内容
    const contentElement = document.createElement('div');
    contentElement.className = 'message-content';
    
    // 添加任务规划（如果有）
    if (taskPlanning && taskPlanning.has_plan) {
        const planElement = createTaskPlanningElement(taskPlanning.plan_text);
        contentElement.appendChild(planElement);
    }
    
    // 添加工具调用（如果有）
    if (toolCalls && toolCalls.length > 0) {
        const toolsElement = createToolCallsElement(toolCalls);
        contentElement.appendChild(toolsElement);
    }
    
    // 使用HTML内容或纯文本
    if (html) {
        contentElement.innerHTML += html;
    } else {
        // 如果有工具调用或任务规划，简化内容
        if ((toolCalls && toolCalls.length > 0) || (taskPlanning && taskPlanning.has_plan)) {
            content = simplifyContent(content, toolCalls, taskPlanning);
        }
        contentElement.innerHTML += formatMarkdown(content);
    }
    
    // 时间戳
    const timeElement = document.createElement('div');
    timeElement.className = 'message-time';
    timeElement.textContent = new Date().toLocaleTimeString();
    
    // 添加到消息元素
    messageElement.appendChild(contentElement);
    messageElement.appendChild(timeElement);
    
    return messageElement;
}

// 显示错误消息
function showError(message) {
    const errorElement = document.createElement('div');
    errorElement.className = 'error';
    errorElement.textContent = message;
    
    chatMessages.appendChild(errorElement);
    scrollToBottom();
    
    // 自动移除错误消息
    setTimeout(() => {
        errorElement.style.opacity = '0';
        setTimeout(() => {
            errorElement.remove();
        }, 500);
    }, 5000);
}

// 显示成功消息
function showSuccess(message) {
    const successElement = document.createElement('div');
    successElement.className = 'success';
    successElement.textContent = message;
    
    chatMessages.appendChild(successElement);
    scrollToBottom();
    
    // 自动移除成功消息
    setTimeout(() => {
        successElement.style.opacity = '0';
        setTimeout(() => {
            successElement.remove();
        }, 500);
    }, 3000);
}

// 重置状态
function resetState() {
    isProcessing = false;
    if (thinkingIndicator) thinkingIndicator.classList.remove('visible');
    sendButton.disabled = false;
    userInput.focus();
}

// 滚动到底部
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 加载聊天历史
function loadChatHistory() {
    fetch('/api/history')
        .then(response => response.json())
        .then(data => {
            if (data.history && data.history.length > 0) {
                // 初始欢迎消息保留
                const welcomeMessage = chatMessages.querySelector('.message-assistant');
                
                // 清空现有消息，但保留欢迎消息
                if (welcomeMessage) {
                    chatMessages.innerHTML = '';
                    chatMessages.appendChild(welcomeMessage);
                }
                
                // 添加历史消息
                data.history.forEach(msg => {
                    appendMessage(msg.role, msg.content);
                });
                
                scrollToBottom();
            }
        })
        .catch(error => {
            console.error('Error loading chat history:', error);
        });
}

// 清除历史记录
function clearHistory() {
    // 确认对话框
    if (!confirm('确定要清除所有对话历史吗？')) {
        return;
    }
    
    fetch('/api/clear', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 保留欢迎消息
                const welcomeMessage = chatMessages.querySelector('.message-assistant');
                chatMessages.innerHTML = '';
                
                if (welcomeMessage) {
                    chatMessages.appendChild(welcomeMessage);
                }
                
                // 添加系统消息
                showSuccess('对话历史已清除');
            }
        })
        .catch(error => {
            console.error('Error clearing history:', error);
            showError('清除历史失败');
        });
} 