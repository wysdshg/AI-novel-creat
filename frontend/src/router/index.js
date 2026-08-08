import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layout/MainLayout.vue'
import ChatView from '@/views/ChatView.vue'
import OverviewView from '@/views/OverviewView.vue'
import DatabaseView from '@/views/DatabaseView.vue'
import FactionView from '@/views/FactionView.vue'
import LocationView from '@/views/LocationView.vue'
import WorldMapView from '@/views/WorldMapView.vue'
import CharacterRelationView from '@/views/CharacterRelationView.vue'
import ConfigChatView from '@/views/ConfigChatView.vue'
import ForeshadowView from '@/views/ForeshadowView.vue'
import DirectionView from '@/views/DirectionView.vue'
import ChapterListView from '@/views/ChapterListView.vue'
import TemplateView from '@/views/TemplateView.vue'
import ModelConfigView from '@/views/ModelConfigView.vue'
import ReferenceView from '@/views/ReferenceView.vue'

// 顶层采用「作品工作区」布局：左侧小说/对话树 + 顶部标签页。
// 新增模块时，只需在此 children 中追加一条带 meta.tab=true 的路由，
// MainLayout 会自动渲染对应的顶部标签，无需改动布局代码 —— 保证可拓展性。
const routes = [
  { path: '/', redirect: '/workspace/chat' },
  {
    path: '/workspace',
    component: MainLayout,
    redirect: '/workspace/chat',
    children: [
      { path: 'chat', name: 'chat', component: ChatView, meta: { title: '对话', tab: true } },
      { path: 'overview', name: 'overview', component: OverviewView, meta: { title: '概览', tab: true } },
      { path: 'database', name: 'database', component: DatabaseView, meta: { title: '角色库', tab: true } },
      { path: 'faction', name: 'faction', component: FactionView, meta: { title: '势力库', tab: true } },
      { path: 'location', name: 'location', component: LocationView, meta: { title: '地点库', tab: true } },
      { path: 'world-map', name: 'world-map', component: WorldMapView, meta: { title: '世界地图', tab: true } },
      { path: 'character-relation', name: 'character-relation', component: CharacterRelationView, meta: { title: '关系网', tab: true } },
      { path: 'config-chat', name: 'config-chat', component: ConfigChatView, meta: { title: '配置对话', tab: true } },
      { path: 'foreshadow', name: 'foreshadow', component: ForeshadowView, meta: { title: '线索 / 伏笔', tab: true } },
      { path: 'direction', name: 'direction', component: DirectionView, meta: { title: '走向推荐', tab: true } },
      { path: 'chapters', name: 'chapters', component: ChapterListView, meta: { title: '章节列表', tab: true } },
      { path: 'template', name: 'template', component: TemplateView, meta: { title: '套路模板', tab: true } },
      { path: 'reference', name: 'reference', component: ReferenceView, meta: { title: '参考文档', tab: true } },
      // 模型配置从左侧栏进入，不在顶部标签中展示
      { path: 'model-config', name: 'model-config', component: ModelConfigView, meta: { title: '模型配置', hideTab: true } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
