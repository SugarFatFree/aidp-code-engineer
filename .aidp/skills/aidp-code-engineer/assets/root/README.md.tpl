# {{project}}

> 项目简介（待填充）

## 📋 项目概述

本项目采用 [AIDP](docs/init/README.md) 范式进行开发，通过结构化文档驱动 + AI 记忆系统实现高效迭代。

**当前版本与开发状态**见项目记忆文件（`AGENTS.md`，Claude Code 下为 `CLAUDE.md`）「当前状态」；项目标识见 `memory/aidp-config.yaml` 的 `project` 段。

## 🚀 快速开始

### 环境要求

- （待填充：Node.js / Java / Python 版本等）
- （待填充：数据库、中间件等依赖）

### 安装依赖

```bash
# 待填充：npm install / mvn install / pip install 等
```

### 启动项目

```bash
# 待填充：npm run dev / mvn spring-boot:run 等
```

### 访问地址

- 前端：http://localhost:3000（待填充）
- 后端：http://localhost:8080（待填充）
- API 文档：http://localhost:8080/swagger-ui.html（待填充）

## 📚 文档导航

| 文档类型 | 路径 | 说明 |
|---------|------|------|
| 需求文档 | [docs/requirements/](docs/requirements/) | PRD、FSD 等需求规格 |
| 设计文档 | [docs/design/](docs/design/) | 架构设计、详细设计 |
| 测试文档 | [docs/testing/](docs/testing/) | 测试用例、测试报告 |
| 部署文档 | [docs/deployment/](docs/deployment/) | 部署方案、运维手册 |
| AIDP 使用指南 | [docs/init/README.md](docs/init/README.md) | AIDP 范式使用说明 |

## 🏗️ 技术栈

- **前端**：（待填充：React / Vue / Angular 等）
- **后端**：（待填充：Spring Boot / Express / Django 等）
- **数据库**：（待填充：MySQL / PostgreSQL / MongoDB 等）
- **其他**：（待填充：Redis / Kafka / Docker 等）

## 📦 项目结构

```
{{project}}/
├── code/              # 源代码
│   ├── frontend/      # 前端代码（如有）
│   └── backend/       # 后端代码（如有）
├── docs/              # 文档体系
│   ├── requirements/  # 需求文档
│   ├── design/        # 设计文档
│   ├── testing/       # 测试文档
│   ├── deployment/    # 部署文档（sql/ + 部署流程/ + 配置文件/）
│   └── reports/       # AI 全自动报告（执行/测试/数据清理/版本测试）
├── memory/            # AI 记忆系统
├── env/               # 环境配置（.env）
├── {{AIDP_HOME}}/      # AIDP 运行真源：commands/agents/rules/flows/reference/skills/hooks/templates/plugins
│                     #   + scripts/ 工具脚本（aidp_state / commit_gate / notify / cicd_watch 等）
├── .github/           # CICD 工作流（如有）
├── AGENTS.md          # 项目记忆文件（Claude Code 下为 CLAUDE.md）
└── README.md          # 本文件
```


## 🔧 开发指南

### 分支管理

- `master` / `main`：主分支，保护分支
- `develop`：开发分支
- `feature/*`：功能分支
- `bugfix/*`：修复分支

### 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
feat: 新增功能
fix: 修复 bug
docs: 文档更新
style: 代码格式调整
refactor: 重构
test: 测试相关
chore: 构建/工具链相关
```

### 使用 AIDP 命令

本项目使用 AIDP 范式进行迭代开发，常用命令：

```bash
/sprint-init              # 项目初始化
/sprint-dev "功能描述"    # 开发新功能
/sprint-bugfix            # 修复 bug
/sprint-test              # 执行测试
```

上方 `/命令` 适用于 Claude Code / DeepSeek Harness；Codex 使用同名 `$命令`（如 `$sprint-dev`）。

★ 7×24 全自动（开发链路 + 测试链路两条同时运行；操作系统调度，Claude Code / Codex / DeepSeek Harness 通用）：

```bash
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install   # 开发链路（10m）+ 测试链路（5m）+ 独立 watchdog 巡检（5m）
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py status    # 三条定时任务 + 两条链路心跳；告警见 memory/.aidp/alerts.jsonl
```

Claude Code 会话内短期使用：`/loop 10m /sprint-autopilot --unattended` 与 `/loop 5m /sprint-aiauto-test --unattended`（会话级，关闭即停）。

详见 [docs/init/README.md](docs/init/README.md)。

## 📝 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| {{version}} | {{date}} | 初始版本 |

完整的版本发布记录（含发布时间、新增功能、修复问题，倒叙排列）见 [版本更新日志.md](版本更新日志.md)。每次 `/version` 发布会自动追加。

## 👥 团队成员

- （待填充：团队成员信息）

## 📄 许可证

（待填充：MIT / Apache 2.0 / 私有等）

---

*本项目使用 [AIDP](docs/init/README.md) 范式进行开发。*
