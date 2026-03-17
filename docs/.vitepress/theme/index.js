// https://vitepress.dev/guide/custom-theme
import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import './styles/style.css'
import './styles/custom-block.css'
import './styles/font.css'
import Layout from './components/Layout.vue'
import ArticleShare from './components/ArticleShare.vue'
import NotFound from './components/NotFound.vue'

/** @type {import('vitepress').Theme} */
export default {
  extends: DefaultTheme,
  Layout() {
    return h(Layout, null, {
      // https://vitepress.dev/guide/extending-default-theme#layout-slots
      'aside-outline-after': () => h(ArticleShare),
      'not-found': () => h(NotFound)
    })
  }
}
