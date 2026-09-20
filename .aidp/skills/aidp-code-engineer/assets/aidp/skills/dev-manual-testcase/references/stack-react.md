# React 项目：文案 / 路由 / 枚举来源

> 生成用例前「从代码读取真实文案」这一步用。跨技术栈通用规则见 `../SKILL.md`。

| 要读什么 | React 项目的位置 |
| :- | :- |
| **路由路径 / 页面入口** | `src/router/*.tsx`（react-router `createBrowserRouter` / `<Route>`）；Next.js 则看 `app/` 或 `pages/` 目录结构（**文件路径即路由**） |
| **按钮 / 表单标签 / Toast 真实文案** | `.tsx`/`.jsx` 的 JSX（`<Button>` 文本、`<Form.Item label="…">`、`message.success('…')`） |
| **表格列展示名** | `columns` 配置数组的 `title`（Antd Table）——**注意是 `title` 不是 `dataIndex`** |
| **国际化文案（若启用 i18n）** | `src/locales/zh-CN.json`、`public/locales/`（next-i18next）——启用时以此为准 |
| **前端枚举 label** | `src/enums/*.ts`、`src/constants/*.ts` |

## 注意

- **用例里写的是用户看到的中文文案**，不是 i18n key 也不是 `dataIndex`。
- Antd Table 的列名取 `title`；`dataIndex` 是数据字段名，写进用例会让执行人对不上界面。
- 引用溯源给精细锚点（如 `UserList.tsx#L120`）。
