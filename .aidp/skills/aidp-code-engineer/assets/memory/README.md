# memory/ — AI 记忆系统（Memory Bank）

> AIDP 范式的 AI 记忆系统，解决 AI 编码 Agent（Claude Code / Codex / DeepSeek Harness）无跨会话记忆的问题。
> 完整规范见 [`docs/init/03_memory文件详细规范.md`](../docs/init/03_memory文件详细规范.md)。模板仓库 `.aidp/` 仅是维护源；下游运行契约位于 `{{AIDP_HOME}}/`（仅 Claude 为 `.claude/aidp`，有 Codex / DSH 为 `.agents/aidp`），脚本引用一律指向下游运行目录。

## 分层结构

### 项目级（单一真源，不隔离）

位于本目录根，跨版本跨用户共享：

| 文件 | 内容 | 写权限 | 更新时机 |
|------|------|--------|---------|
| `projectBrief.md` | L1 项目简介（北极星文件） | PM（需 Review） | 仅项目方向重大调整时 |
| `productContext.md` | L1 产品上下文 | PM | 需求变更时 |
| `systemPatterns.md` | L2 架构决策（ADR 累积，跨版本） | Architect（需 Review） | 每次重大技术决策 |
| `techContext.md` | L2 技术上下文 | Architect / Dev | 环境变更时 |
| `databaseBaseline.md` | L2 数据库基线（跨版本累积） | Architect | Sprint 关闭时 |

**项目级文件是跨版本的单一权威来源，不得分叉，不得按用户隔离。**

### 迭代级（按 {version}/{user} 隔离）

位于 `memory/{version}/{user}/` 子目录，每个开发者独立：

| 文件 | 内容 | 写权限 |
|------|------|--------|
| `activeContext.md` | L3 当前 Sprint 实时状态 | 该用户独占 |
| `progress.md` | L3 该用户在该版本的进度 | 该用户 |
| `sprints/sprint-{NNN}.md` | L4 Sprint 归档快照（只追加） | 该用户（仅创建） |

### 项目配置（人维护）

| 文件 | 内容 |
|------|------|
| `aidp-config.yaml` | 项目级开关与集成配置：提交前门禁 `commit_gate`、里程碑通知 `notify`、CICD `cicd`（提供方 `provider`，默认 GitHub Actions + 环境→流水线映射 `pipelines`）、7×24 调度 `scheduler`（`aidp_scheduler.py` 读取）、Stop 护栏 `stop_guard`、脚手架版本 `scaffold`、autopilot 决策兜底 `autopilot_decisions`。团队共享、随 git 提交；⛔ 密钥只经环境变量引用，不明文入库 |

### 运行时状态文件（点号开头，项目级）

除上述 Markdown 记忆文件外，本目录还承载若干**命令运行时状态**（JSON），它们不是"记忆"、不供人工编辑，且**均由对应命令/脚本首次用到时才创建**（下表是**规范落点清单**，本仓按需生成、缺失不算缺陷）：

| 文件 | 内容 | 入库 | 写入方 |
|------|------|------|--------|
| `.sprint-autopilot-baseline.json` | ★ `/sprint-autopilot`（开发链路）与 `/sprint-aiauto-test`（测试链路）**共享的版本状态机 baseline**（项目级扁平 `versions.{V}` + `current_build` + 项目级运行时记录 `project_state`），是两条链路判断"当前开发/被测版本"的唯一依据 | ✅ 入库共享 | 两命令 |
| `.aidp/`（目录） | 本地运行态，路径单一信源 = `{{AIDP_HOME}}/scripts/aidp_paths.py`：里程碑通知台账、Stop 护栏计数 `stop-guard-count` 与放行留痕 `stop-guard-skips.jsonl`（滚动保留最近 50 条）、**本地告警台账 `alerts.jsonl`**（冻结 / 链路失联 / 通知未送达恒追加一行，无通知渠道时"停得响"靠它）、并发写锁 `locks/`（0 字节 `flock` 载体）、7×24 调度日志 `logs/`、memory 写前快照 `memory-snapshot/` | ❌ 已 gitignore（纯本地）| `aidp_paths.py` 各写方（`baseline_edit.py` / `notify.py` / `autopilot_fail_handle.py` / `agent_loop.sh` / `aidp_scheduler.py` / Stop hook 等）|
| `.autopilot-stop-guard-off` | Stop 护栏人工禁用逃生舱（存在即全程放行，⛔ 用完即删）| ❌ 已 gitignore | 人工创建 |
| `.sprint-autopilot-credentials.json` | 测试账号（明文敏感）| ❌ 已 gitignore + `chmod 600` | `/sprint-aiauto-test` Phase 0.4「测试账号加载」（`flows/sprint-aiauto-test/phase-0-7.md`）—— ⛔ 不是 `/sprint-autopilot`：其 `phase-0-8.md` 明写「不在本命令收集」 |
| `_facts/code-inventory.json` | 代码事实增量缓存（API 端点 / 数据库表 / 前端路由 / 页面 / 配置，sha 比对刷新）| ❌ 已 gitignore（可由代码重建，无需入库）| `{{AIDP_HOME}}/scripts/code_inventory.py` |
| （无落盘台账） | 跨版本需求检索走**读时查询**：`requirement_query.py search` 现读现搜各版研发需求正文、`supersessions` 聚合各版 `98_语义变更与需求作废.json` | — 无产物、不入库 | `{{AIDP_HOME}}/scripts/requirement_query.py` |

> ⛔ **并发写铁律**：`.sprint-autopilot-baseline.json` 由**两条 `/loop` 并发读写**（开发链路 10m tick + 测试链路 5m tick），**任何写入必须经 `python3 {{AIDP_HOME}}/scripts/baseline_edit.py`（`memory/.aidp/locks/` 下加锁 + 锁内重读 + 原子替换）**——严禁直接 `Write` / `jq > file` / 手工编辑该 JSON，否则会丢写、互相覆盖版本状态。读取可直接读。

## 目录结构

```
memory/
├── README.md                （本文件）
├── aidp-config.yaml         （项目配置·人维护·入库共享）
├── projectBrief.md          （项目级）
├── productContext.md        （项目级）
├── systemPatterns.md        （项目级）
├── techContext.md           （项目级）
├── databaseBaseline.md      （项目级）
├── .sprint-autopilot-baseline.json       （运行时状态·入库共享）
├── .sprint-autopilot-baseline.json.lock  （并发写锁·空文件，已 gitignore）
├── _facts/                  （机器可读事实清单，由命令自动维护）
│   └── code-inventory.json
└── {version}/               （版本目录，如 V1.0.0/）
    └── {user}/              （开发者目录，取 git config user.name）
        ├── activeContext.md
        ├── progress.md
        └── sprints/         （Sprint 归档）
```

> ℹ️ **迭代级 memory 文件按需生成、不预建**：`{version}/{user}/` 下脚手架只铺目录骨架——`activeContext.md` 与 `progress.md` 由 `/sprint-start`、`/memory-sync` **首次运行时自动创建**（不预置空文件，避免空占位被误读成"已有状态"）。`sprints/sprint-{NNN}.md` 则由 `/sprint-close` 归档时写入。

## 会话启动读取顺序

```
必读：
  1. AGENTS.md（Claude Code 下为 CLAUDE.md） → 项目概况和当前状态
  2. memory/{version}/{user}/activeContext.md     → 当前 Sprint 状态
  3. memory/{version}/{user}/progress.md          → 该视角下的进度

按需读取：
  4. memory/systemPatterns.md     → 做技术决策前必读（项目级）
  5. memory/databaseBaseline.md   → ★ 做数据库设计前必读（防重复建表）
  6. memory/techContext.md        → 搭建/修改开发环境前必读
  7. memory/productContext.md     → 做需求分析前必读
  8. memory/projectBrief.md       → 了解项目背景时读取
```

## 禁忌

- ❌ 不得将 ADR 或数据库基线放进 `{version}/{user}/` 子目录
- ❌ 不得修改其他用户的迭代级 memory 文件
- ❌ 不得在未 `/sprint-close` 时直接修改 `sprints/` 下的归档文件
- ❌ 不得跨版本复制 activeContext（每个版本独立维护）

## 相关文档

- [`docs/init/03_memory文件详细规范.md`](../docs/init/03_memory文件详细规范.md) — 文件模板与规范
- [`docs/init/06_版本与用户目录约定.md`](../docs/init/06_版本与用户目录约定.md) — 路径规则权威来源
- [`docs/init/04_agents详细规范.md`](../docs/init/04_agents详细规范.md) — Agent 写权限分工
