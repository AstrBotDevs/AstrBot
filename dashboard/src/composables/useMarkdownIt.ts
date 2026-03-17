import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

// Shared markdown-it instance with highlight.js code highlighting.
// Used by PluginWelcomePanel and PluginOverviewPanel.
// We use markdown-it directly (instead of markstream-vue's MarkdownRender)
// to preserve raw HTML inline layout — markstream-vue wraps each node
// in width:100% Vue containers, which breaks inline flow of <a> tags
// inside <div align="center">.

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: false,
})

md.enable(['table', 'strikethrough'])
md.renderer.rules.table_open = () => '<div class="table-container"><table>'
md.renderer.rules.table_close = () => '</table></div>'

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = token.info.trim() || ''
  const code = token.content

  const highlighted =
    lang && hljs.getLanguage(lang)
      ? hljs.highlight(code, { language: lang }).value
      : md.utils.escapeHtml(code)

  return `<div class="code-block-wrapper">
    ${lang ? `<span class="code-lang-label">${lang}</span>` : ''}
    <pre class="hljs"><code class="language-${lang}">${highlighted}</code></pre>
  </div>`
}

/**
 * Render markdown to HTML, post-processing all links to open in new tabs.
 */
export function renderMarkdown(source: string): string {
  if (!source) return ''

  const rawHtml = md.render(source)

  // Post-process: make all links open in new tab
  const tempDiv = document.createElement('div')
  tempDiv.innerHTML = rawHtml
  tempDiv.querySelectorAll('a').forEach((a) => {
    const href = a.getAttribute('href') || ''
    if (href && !href.startsWith('#')) {
      a.setAttribute('target', '_blank')
      a.setAttribute('rel', 'noopener noreferrer')
    }
  })

  return tempDiv.innerHTML
}
