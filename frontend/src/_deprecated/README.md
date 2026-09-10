# `_deprecated/` — 已下架的前端页面（**保留代码，不参与构建**）

这里的 `.vue` **没有任何地方 import**，因此会被 Vite 排除在产物之外（不会增加包体积）。
放这里的目的是留档：万一要复活，代码还在，不用从 git 历史里翻。

> 想复活某个页面：把文件移回 `src/views/`，在 `src/router/index.js` 里补 import + 一条路由即可。
> 移回前请先确认它的依赖（`@/api/*`、`@/utils/*`）还在 —— 下架时可能顺带清理了死代码。

| 文件 | 下架时间 | 原因 | 能力是否丢失 |
|---|---|---|---|
| `ConfigChatView.vue` | 2026-09-10 | 316 行的真实功能，但侧栏**没有任何入口**，长期不可达（等于用不到）；用户拍板归档 | ❌ 未丢失。核心能力（`/角色` `/地点` 等斜杠指令 + 自然语言入库 + dry-run 那套解析）由 `components/workspace/ChatInput.vue` 承载，走同样的 `commandApi` + `parseSlashCommands`。丢掉的是"独立页面 + 仅预览开关"这层壳 |
| `ChapterView.vue` | 2026-08-06 | 早期章节页，被工作区内的生成对话框取代 | ❌ 未丢失（章节生成走 `GenerateChapterDialog`） |
| `DiscussionView.vue` | 2026-08-06 | 早期商讨页（桩），被 `ChatView` + 商讨面板取代 | ❌ 未丢失 |

**后端接口不受影响**：`POST /projects/{id}/command` 正常可用（`config_command.run` 是真实实现），
所以斜杠指令与自然语言入库在主聊天框里照常工作。
