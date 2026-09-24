# docs/prompts/ — 大型 Prompt 存档

> **隔离级别**：版本级（团队共享）

## 目录结构

```
docs/prompts/
└── {version}/
    ├── {module}-prompt.md              # 按模块组织的 Prompt 模板
    ├── {task}-prompt.md                # 按任务组织
    └── agent-team-sprint-{NNN}.md      # 特定 Agent Team 的 Prompt
```

## 用途

- 存放长的、反复使用的 Prompt 模板
- 记录成功的 Prompt 工程实践
- 供新成员参考学习

## 与 `{{AIDP_HOME}}/skills/` 的区别

| 对比项 | `{{AIDP_HOME}}/skills/` | `docs/prompts/{version}/` |
|--------|------------------|---------------------------|
| 范围 | 项目级（跨版本） | 版本级 |
| 调用方式 | Claude 自动调用 | 人工复制粘贴 |
| 格式 | 标准 SKILL.md 格式 | 自由 Markdown |
| 用途 | 结构化能力 | 经验沉淀 |

## 相关文档

- [`../init/02_迭代输入指导.md`](../init/02_迭代输入指导.md) — 第 8 节 Agent Team 模式执行指南
