# docs/implementation/ — 实施过程记录

> **隔离级别**：版本级 + 用户级（个人踩坑笔记，每人独立）

## 目录结构

```
docs/implementation/
└── {version}/
    └── {user}/
        ├── {module}-implementation.md      # 按模块组织
        └── sprint-{NNN}-notes.md           # 按 Sprint 组织
```

## 典型内容

- 关键模块的落地思路
- 踩坑笔记与解决方案
- 个人技术决策备忘
- 与设计文档的差异说明
- TODO 与后续改进点

## 使用建议

- 开发过程中随时记录，避免遗忘
- 不对外共享，仅个人参考
- Sprint 关闭时可择优内容提炼到 `memory/systemPatterns.md`（项目级 ADR）

## 相关文档

- [`../init/06_版本与用户目录约定.md`](../init/06_版本与用户目录约定.md) — 第 2.3 节版本+用户双层隔离
