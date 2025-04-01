<template>
  <div class="markdown-renderer" v-html="renderedContent"></div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/atom-one-dark.css'

export default {
  name: 'MarkdownRenderer',
  props: {
    content: {
      type: String,
      required: true
    }
  },
  setup(props) {
    // 配置Marked选项
    onMounted(() => {
      marked.setOptions({
        renderer: new marked.Renderer(),
        highlight: function(code, lang) {
          const language = hljs.getLanguage(lang) ? lang : 'plaintext';
          return hljs.highlight(code, { language }).value;
        },
        langPrefix: 'hljs language-',
        gfm: true,
        breaks: true,
        sanitize: false,
        smartypants: true
      });
    });
    
    // 渲染Markdown内容
    const renderedContent = computed(() => {
      try {
        return props.content ? marked(props.content) : '';
      } catch (e) {
        console.error('Markdown渲染错误:', e);
        return props.content || '';
      }
    });
    
    return {
      renderedContent
    };
  }
}
</script>

<style lang="scss">
.markdown-renderer {
  width: 100%;
  line-height: 1.6;
  
  h1, h2, h3, h4, h5, h6 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  h1 { font-size: 2em; }
  h2 { font-size: 1.5em; }
  h3 { font-size: 1.3em; }
  h4 { font-size: 1.1em; }
  h5 { font-size: 1em; }
  h6 { font-size: 0.9em; }
  
  p {
    margin-bottom: 1em;
  }
  
  ul, ol {
    margin-bottom: 1em;
    padding-left: 2em;
  }
  
  li {
    margin-bottom: 0.5em;
  }
  
  blockquote {
    border-left: 4px solid var(--primary-color);
    padding-left: 1em;
    margin-left: 0;
    margin-bottom: 1em;
    color: var(--text-secondary);
    font-style: italic;
  }
  
  code {
    font-family: 'JetBrains Mono', 'Fira Code', Menlo, Monaco, 'Courier New', monospace;
    background-color: var(--bg-tertiary);
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-size: 0.9em;
  }
  
  pre {
    background-color: var(--bg-quaternary);
    border-radius: 8px;
    padding: 1rem;
    margin: 1em 0;
    overflow-x: auto;
    position: relative;
    
    code {
      background-color: transparent;
      padding: 0;
      border-radius: 0;
      font-size: 0.9rem;
    }
    
    &::before {
      content: attr(data-language);
      position: absolute;
      top: 0;
      right: 0;
      padding: 2px 8px;
      font-size: 0.7rem;
      font-weight: 500;
      color: var(--text-quaternary);
      background-color: rgba(0, 0, 0, 0.2);
      border-bottom-left-radius: 4px;
      border-top-right-radius: 8px;
      opacity: 0.8;
    }
  }
  
  img {
    max-width: 100%;
    border-radius: 4px;
    margin: 1em 0;
  }
  
  table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 1em;
    
    th, td {
      border: 1px solid var(--border-color);
      padding: 8px 12px;
    }
    
    th {
      background-color: var(--bg-tertiary);
      font-weight: 600;
    }
    
    tr:nth-child(even) {
      background-color: var(--bg-secondary);
    }
  }
  
  hr {
    border: 0;
    border-top: 1px solid var(--border-color);
    margin: 1.5em 0;
  }
  
  a {
    color: var(--primary-color);
    text-decoration: none;
    
    &:hover {
      text-decoration: underline;
    }
  }
}
</style> 