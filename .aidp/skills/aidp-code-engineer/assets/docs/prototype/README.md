# docs/prototype/ — 原型与高保真图资源

> **隔离级别**：版本级（团队共享）

## 目录结构

```
docs/prototype/
└── {version}/
    ├── code/                       # 原型代码（vibe coding 产物）
    │   └── {module}/               # 按功能模块组织
    └── mockup/                     # 高保真原型（视觉基准）
        └── {module}/               # 按模块组织
            ├── page-overview.png   # 人工提供的高保真图
            └── page-detail.vue     # UI Agent 自动生成的原型代码
```

## 两个子目录职责

### `code/`（原型代码）

- 产品/设计通过 vibe coding 工具（Cursor / v0 / Bolt 等）生成的**可运行静态原型**
- 用途：**功能 + 交互逻辑的参考**（按钮点击、表单校验、弹窗流程）
- 技术栈任意（React / Vue / 纯 HTML），由 UI Agent 转换为项目实际技术栈

### `mockup/`（高保真原型）

- **视觉基准**（最高优先级）
- 两种来源：
  1. **人工提供**：设计师输出的高保真图（PNG / JPG）
  2. **AI 自动生成**：当 **用户显式选择情形 D 时**（⛔ 不是「`mockup/` 下无图片」——那横跨情形 B/C/D，而 `agents/ui.md` 硬禁在 A/B/C 下擅自生成：臆造的视觉基线会被钉成 L1 对齐基准），UI Agent 在 `/sprint-design` 阶段基于 `code/` + `docs/architecture/UI规范约束.md` 自动生成

## 优先级规则（4 情形 — 含 UI 设计规范维度）

| 情形 | 高保真 | UI 设计规范 | 用户选择 | 视觉基准 | 功能/交互基准 |
|------|------|-----------|---------|---------|--------------|
| A | ✓ | 任意 | — | `mockup/` 图片 | `code/` 原型代码 |
| B | ✗ | ✗（空模板/缺失） | — | `code/` 原型代码自身样式 | `code/` 原型代码 |
| C | ✗ | ✓ | "直接对齐原型" | 同 B（沿用 `code/`） | `code/` 原型代码 |
| D | ✗ | ✓ | "参考原型 + UI 规范优化" | UI Agent 流程 C 生成 `mockup/` → 转 A | `code/` 原型代码 |

**优先级排序**：**人工高保真图片 > AI 生成高保真原型 > 原型代码（情形 B/C 作为视觉基准）**

情形 C/D 必须由用户显式选择（详见 `../init/04_agents详细规范.md` UI Agent / `.aidp/agents/ui.md` 流程 A Step 0）。

## 相关命令

- `/sprint-design` — 调用 UI Agent 生成 UI 规范 + 必要时自动生成高保真原型
- `/sprint-dev` — 前端开发时严格按 `mockup/` 实现视觉

## 相关文档

- [`../init/04_agents详细规范.md`](../init/04_agents详细规范.md) — UI Agent 职责
- [`../architecture/UI规范约束.md`](../architecture/UI规范约束.md) — UI 规范（动态更新）
