# Vue 项目：文案 / 路由 / 枚举来源

> 生成用例前「从代码读取真实文案」这一步用。跨技术栈通用规则见 `../SKILL.md`。

| 要读什么 | Vue 项目的位置 |
| :- | :- |
| **路由路径 / 页面入口** | `src/router/index.ts`、`src/router/routes.ts`（`vue-router` 配置）；菜单项常另在 `src/layout/` 或后端菜单接口 |
| **按钮 / 表单标签 / Toast 真实文案** | `.vue` 单文件组件的 `<template>`（`el-button` 文本、`el-form-item` 的 `label`、`ElMessage.success('…')`） |
| **表格列展示名** | `el-table-column` 的 `label`，或 `columns` 配置数组的 `label` |
| **国际化文案（若启用 i18n）** | `src/i18n/zh-CN.json`、`src/locales/zh-CN.ts`——**启用 i18n 时以此为准**，`.vue` 里只有 key |
| **前端枚举 label** | `src/enums/*.ts`、`src/constants/enums/*.ts` |

## 注意

- **用例里写的是用户看到的中文文案**，不是 i18n 的 key。若项目启用 i18n，必须解析到 `zh-CN` 的真实值再写进用例。
- 引用溯源时给出精细锚点（如 `UserList.vue#L88`），供 `[PRD存在性]` 与文案一致性用例回查。
