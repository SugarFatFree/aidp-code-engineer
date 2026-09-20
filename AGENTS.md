# aidp-code-engineer — 模板仓库维护记忆

> 本文件只服务于**本仓库自身的维护**，⛔ 不下发。
> 下发给下游项目的记忆正文是 **`.aidp/AIDP-AGENTS.md`**（会话流程 / 命令入口 / 核心约定 1–41 等）——本仓库自己不跑 `/sprint-*` 命令、也不调用那些 SKILL，维护时按需 Read 即可。
> Claude Code 经 `CLAUDE.md`（一行 `@AGENTS.md`）加载本文件；Codex / DeepSeek Harness 直接读本文件。

## 项目一句话描述

**aidp-code-engineer** 是通用的 AIDP（AI-Driven Iterative Development Paradigm）模板项目与同名脚手架 skill：把「版本规划 → Sprint 执行 → 7×24 无人值守 → AI 自动化测试 → 发布归档」这套范式下发给下游项目，支持 Claude Code / Codex / DeepSeek Harness。

## 语言

面向维护者的说明、计划、总结一律中文；代码、命令、配置键、专有名词保持原文。

## 仓库地图（改什么 → 去哪改）

| 想改的内容 | 落点 |
|-----------|------|
| 下游项目记忆正文（会话流程、命令入口、核心约定） | `.aidp/AIDP-AGENTS.md` |
| 命令 / 命令分片流程 | `.aidp/commands/`、`.aidp/flows/` |
| 角色、编码规则、约定细则与参考 | `.aidp/agents/`、`.aidp/rules/`、`.aidp/reference/` |
| SKILL / 插件 | `.aidp/skills/`、`.aidp/plugins/` |
| 确定性脚本与回归测试 | `.aidp/scripts/`、`.aidp/scripts/tests/` |
| hook / 报告与部署模板 | `.aidp/hooks/`、`.aidp/templates/` |
| 范式文档 | `docs/init/` |
| 配置骨架 | `memory/aidp-config.yaml`、`memory/README.md` |
| 脚手架引擎（init / migrate / upgrade / verify） | `.aidp/skills/aidp-code-engineer/`（`assets/` 是生成物，⛔ 不手改） |
| 范式版本号 / 变更记录 | `版本变更历史.md` |
| 主要命令的设计目标基线 | `设计目标.md` |

- **本仓库不携带 Agent 适配层**（`.claude/`、`.codex/`、`.dsh/`、`.agents/` 已整目录忽略）：维护者本地用哪个 Agent，就建对应标记目录后跑 `python3 .aidp/scripts/agent_sync.py`。
- **命令适配由 `agent_sync.py` 生成**：Claude Code → `.claude/commands/`，Codex → `.codex/aidp/skills/`，DeepSeek Harness → `.dsh/commands/`；增删 `.aidp/commands/` 后重跑该脚本。

## 提交规范

Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`），一次提交只做一件事；脚手架同步可用 `chore(skill): sync aidp-code-engineer`。

## ★ 模板 ↔ 脚手架同步（改完契约文件后、commit 前必跑；⛔ 不手工 `cp`）

```bash
# ① 下发记忆源 → 脚手架模板（改过 .aidp/AIDP-AGENTS.md 时）
python3 .aidp/skills/aidp-code-engineer/scripts/sync_memory_md.py
# ② 本体 → 脚手架 bundle 单向镜像（--check 干运行，有漂移 exit 1）
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py
# ③ 模板自检（镜像类 ERROR 应为 0）
python3 .aidp/skills/aidp-code-engineer/scripts/verify.py . --template --read-only
# ④ 回归单测（本清单是它唯一的调用方：verify.py 不跑单测，单测是模板项目自有；run.sh 已含脚手架单测，第二行供单独调试）
bash .aidp/scripts/tests/run.sh
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
# ⑤ 文档引用与开源卫生（CI 同样必跑；私有痕迹按模式识别，需按具体名称扫描时加 --denylist <本地文件>）
python3 .aidp/scripts/check_code_symbol_refs.py
python3 .aidp/scripts/check_cli_invocation.py
python3 .aidp/scripts/check_private_markers.py
```

- **需同步的范围**：`.aidp/AIDP-AGENTS.md`、`.aidp/{agents,commands,rules,flows,reference,hooks,templates,skills,plugins}`（受版本门控，单一信源 = `scaffold_lib.py::GATED_DIRS`）、`.aidp/scripts/`（不受版本门控，字节不同即覆盖下发；模板回归单测 `tests/` 与设计目标 baseline 不下发，见 `scaffold_lib.py::TEMPLATE_OWNED`）、`docs/init/`、`docs/**/README.md`（不含版本目录）、`docs/architecture/` 三份约束骨架、`memory/README.md`、`memory/aidp-config.yaml`、脚手架 `sources/`（下游根文件与项目级 memory 模板真源）。
- **不进脚手架**：本文件、`设计目标.md`、`code/` 业务代码、版本化迭代产出（`docs/*/{version}/`、`memory/{version}/`）、已填真实内容的项目级 memory。
- **目标↔实现背离检查（可选，不阻断）**：派子 Agent 按 `.aidp/agents/aidp-compliance.md` 语义维度 4 逐条核 `设计目标.md` 的 G-* 锚点，产出「已落地 / 形式落地 / 未落地」清单。

## ★ 范式版本号自增铁律

- **唯一合规触发 = 用户在本次请求里明确要求 bump**（"版本号更新至 X" / "自增版本号"）。"本轮含真实功能修改"不是自我授权；上一轮授权只对那一轮有效。
- 版本号落点：`版本变更历史.md`「当前范式版本」（权威）→ `assets/SCAFFOLD_VERSION` / `CONTRACT_MANIFEST.json`（脚本派生）；改版本只用 `bump_version.py`。
- **纯审计不 bump**（一致性、计数、错别字等内部修复）。
- **例外提示**：改了**会下发的契约正文且改变下游 AI 行为**时，同版本下游收不到（`scaffold.py` 仅在 `项目版本 < 脚手架版本` 时覆盖已有契约）。命中时改完停在当前版本，在汇报里点明"建议 bump 一个 patch"，等用户拍板。
