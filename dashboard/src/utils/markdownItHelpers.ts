import type { MarkdownIt } from 'markdown-it-ts'

/**
 * Enables HTML and GitHub-like defaults on the markdown-it instance used by markstream-vue.
 *
 * Note: GitHub's renderer is not identical to markdown-it, but this makes the local rendering
 * consistent across panels and ensures preprocessed HTML (e.g. <img>) is actually rendered.
 */
export function enableGitHubLikeMarkdownIt(md: MarkdownIt): MarkdownIt {
  md.options.html = true
  md.options.linkify = true
  md.options.typographer = true
  return md
}