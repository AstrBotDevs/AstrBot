import MarkdownIt from 'markdown-it'

// Shared markdown-it instance for MOD Manager markdown panels.
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
  const langClass = lang.replace(/[^\w-]/g, '')
  const code = token.content
  const highlighted = md.utils.escapeHtml(code)

  return `<div class="code-block-wrapper">
    ${lang ? `<span class="code-lang-label">${md.utils.escapeHtml(lang)}</span>` : ''}
    <pre class="hljs"><code class="language-${langClass}">${highlighted}</code></pre>
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
