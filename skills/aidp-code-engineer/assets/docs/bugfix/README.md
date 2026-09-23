# docs/bugfix/ — Bug 记录

> **隔离级别**：版本级目录（文件命名带 user 区分发现人）

## 文件命名规范

```
# ⚠️ 下方 bugfix-*.md 均为【示例文件名】
docs/bugfix/
└── {version}/
    ├── bugfix-{YYYYMMDD}-{user}.md    # 一天一人一份汇总
    ├── bugfix-20260509-alice.md
    └── bugfix-20260509-bob.md
```

**核心约定**：一个开发者当天发现/修复的所有 bug，汇总到一份文件。

## 文件结构

1. **标题**：`# Bugfix {YYYYMMDD} - {user}`
2. **Bug 清单表格**（文件开头，必需）：
   ```
   | 编号 | 时间 | Sprint | 模块 | 现象 | 严重 | 优先级 | 难易 | 状态 | Commit | 备注 |
   ```
3. **每个 Bug 详情章节**：`# B-{YYYYMMDD}-NN: {标题}（Sprint-{NNN}）`
   - Bug 现象（用户原话）
   - 影响范围
   - Root Cause
   - 改动文件
   - 验证步骤
   - 部署提醒
   - Commit

详见 [`../init/00_AIDP范式主文档.md`](../init/00_AIDP范式主文档.md) 第 7 节。

## 字段说明

| 字段 | 取值 |
|------|------|
| 严重 | P0 阻塞 / P1 严重 / P2 一般 / P3 轻微 |
| 优先级 | 高 / 中 / 低 |
| 难易 | 简单 / 中等 / 困难 |
| 状态 | Open 待修 / In-Progress 修复中 / Fixed 已修 / Verified 已验证 / Closed 已关闭 / Reopened 回归 |
| Sprint | 该 bug 归属的 Sprint 序号（可选，支持跨 Sprint 修复） |

## 相关命令

- `/sprint-bugfix` — 修复已记录的 bug（独立可用，无需 Sprint）
- `/sprint-bugfix sprint-001` — 按 Sprint 过滤
- `/sprint-bugfix "<描述>"` — 自动累进新 Sprint（适合较大 bug）

## 跨用户约束

- ❌ 不得修改其他用户的文件（`bugfix-*-{其他user}.md`）
- ✅ 可以读取他人文件了解协作进度
- ✅ 集成测试发现跨模块问题时，各自归属人创建自己的文件
