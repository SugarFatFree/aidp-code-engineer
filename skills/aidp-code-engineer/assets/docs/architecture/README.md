# docs/architecture/ — 架构约束文档（项目级）

> **隔离级别**：项目级（跨版本累积，不按版本或用户隔离）

## 文件结构

```
docs/architecture/
├── README.md                      本文件
├── 架构约束.md                    分层、命名、安全、性能、数据约束 + 禁止事项
├── 技术选型.md                    技术栈总览 + 选型决策记录
├── UI规范约束.md                  品牌色、字体、组件样式、布局、交互规范
└── 架构设计.md 或 架构设计/       ★【可选】整体架构设计（单文档或多文档子文件夹）
```

> ★ **上面前三份是「约束三件套」，第四项「架构设计类」是可选的**（单文档 `架构设计.md`
> 或子文件夹 `架构设计/`，兼容存量任意命名）。**约定 7 要求读本目录时【全目录扫描】**——
> 架构设计文档存在即作为详细设计的**上游输入**通读，不存在则跳过。
> 仅有架构设计、缺架构约束时，`/sprint-design` Step 4.2 会据它派生一份 `架构约束.md`。
> 定义见 `docs/init/06_版本与用户目录约定.md` §2.1.1。

## 文件定位

三份文档均为 **AIDP 模板**（空占位 + 章节骨架），内容会**随项目演进动态填充**：

- **初始化**：`/sprint-init` 创建空模板
- **动态填充**：每次 `/sprint-design` 调用 `dev-logic-architect` skill / UI Agent，根据实际设计追加新内容
- **人工补充**：团队可随时编辑补充强制规范

## 动态填充机制

| 触发命令 | 填充目标 | 数据来源 |
|---------|---------|---------|
| `/sprint-init` | 创建空模板 | - |
| `/sprint-design` | 追加新技术/新约束 | `dev-logic-architect` skill 输出 |
| `/sprint-design` | 追加 UI 规范 | UI Agent 从原型提取 |
| `/sprint-dev` | 引入新架构决策时追加 | git diff 对比 |
| `/sprint-bugfix` | 修复涉及架构变更时追加 | 同上 |

## 使用准则

1. **团队约定 > 动态填充**：人工补充的强制规范（如"必须使用团队公共组件库"）会被 AIDP 尊重，不会被自动覆盖
2. **追加而非覆盖**：`/sprint-design` 只追加新内容，不删除已有内容
3. **变更历史表**：每个文件末尾有变更历史表，记录谁在什么时候改了什么
4. **关联 Sprint**：每次追加都标注"关联 Sprint-NNN"，便于审计

## 相关文档

- [`../init/00_AIDP范式主文档.md`](../init/00_AIDP范式主文档.md) — 6.7 节文档动态同步机制
- [`../init/04_agents详细规范.md`](../init/04_agents详细规范.md) — Architect Agent / UI Agent 职责
- [`../../{{AIDP_HOME}}/commands/sprint-design.md`](../../{{AIDP_HOME}}/commands/sprint-design.md) — Step 4 动态更新 architecture 说明
