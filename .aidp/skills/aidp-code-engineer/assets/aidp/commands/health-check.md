# /health-check — 项目健康度检查

你正在执行 `/health-check` 命令，全面检查项目文档、记忆系统和代码的一致性。

## 前置流程

1. **{user}** ← `git config user.name`
2. **{version}** ← 项目记忆文件（`python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取路径）「当前状态.当前版本」；读不到则取 `memory/` 下按版本序最大的 `V*` 目录；仍无（尚未规划任何版本）则标记 `{version}` 缺省、检查项 9 标 N/A（`verify.py` 下游模式缺版本参数直接 exit 2，不跑）。**★ 不得写死任何具体版本号**（写死会让下游项目对着不存在的 `memory/V0.0.1/{user}/` 报假缺失）。
3. 扫描 `memory/` 下**所有版本**（`V*` 目录）和**所有用户**的子目录，汇总健康度。
4. 项目级 memory 文件检查一次即可。

## 触发时机

- 每两个 Sprint 执行一次
- 出现明显混乱时执行
- 版本发布前执行（建议在跑 `/version` 之前先做一次健康检查）

## 执行方式：独立只读子 Agent（隔离上下文，不占主对话）

`/health-check` 本质是"跨全版本 / 全用户扫 `memory/` + `docs/` + `code/` 的 11 项审计（1~10 + 9bis）"，会把大量项目资产读进上下文。**整套检查由独立子 Agent 执行**：用 `Agent` 工具派一个**只读子 Agent**（`subagent_type: Explore` 即可——纯读不写产物），把**下方「检查项」1~10（含 9bis）+ 「输出格式」原文**作为 prompt 传入；子 Agent 自行扫描 `memory/`（项目级 + 所有 `{version}/{user}`）+ `docs/architecture/` + `docs/bugfix/` + `code/` 等资产，逐维度核验，**只回传最终《项目健康度报告》**（按「输出格式」结构）给主对话。主对话**不读被审计文件正文**，只负责把报告呈现给用户 + 据高优先级问题给后续建议。

- 子 Agent 失败（超时 / 异常 / 返回空）→ 命令端内联兜底跑同一 11 项清单（1~10 + 9bis）（标注"⚠️ 子 Agent 失效兜底"），禁止静默放过。
- 本命令纯审计、不写产物，子 Agent 全程只读，可安全隔离；不阻塞主对话，用户可稍后查阅报告。

## 检查项

### 1. 技术栈一致性

- 读取 `memory/systemPatterns.md`（项目级）中的技术选型
- 对比实际代码（`code/` 下脚手架配置）
- 检查是否有新引入但未记录 ADR 的技术

### 2. 功能进度准确性

- 读取各个 `memory/{version}/{user}/progress.md` 中的功能模块状态
- 抽查关键代码文件是否存在，验证状态准确性
- 如多人同版本并行，比对不同用户的 progress 是否有冲突

### 3. ADR 完整性

- 检查 `memory/systemPatterns.md`（项目级）中的 ADR 记录
- 对比代码中实际使用的技术和框架
- 是否有重大架构决策未记录

### 4. 约束合规性

- 全目录读取 `docs/architecture/`（约束三件套 + 可选架构设计文档，单/多文档）
- 抽查关键代码是否符合约束要求
- 重点检查：命名规范、分层结构、安全要求

### 5. 技术债务管理

- 读取 `memory/techContext.md`（项目级）中的技术债务
- 累计技术债务总数是否超过 10 条
- 是否有超过 3 个 Sprint 未处理的技术债务

### 6. Bugfix 闭环

- 扫描 `docs/bugfix/` 下所有版本/用户子目录的问题记录
- 是否有长期未关闭的问题
- 所有已修复的 bugfix 是否有完整的修改范围记录

### 7. 文件完整性

- 检查项目级 `memory/` 下必要文件是否存在：
  - projectBrief.md
  - productContext.md
  - systemPatterns.md
  - techContext.md
  - databaseBaseline.md
- 对每个活跃 `{version}/{user}` 组合，检查 `memory/{version}/{user}/` 下：
  - activeContext.md
  - progress.md
  - sprints/ 目录
- 检查项目记忆文件（`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）的「当前状态」区域是否与实际目录匹配

### 8. ★ 目录层级合规性

- 扫描 `docs/requirements/`、`docs/design/detail/`、`docs/testing/`、`docs/bugfix/`、`docs/plans/`、`docs/implementation/`、`docs/reports/`
- 确认这些目录下第一级的**子目录**都是 `V*` 版本目录（而非直接的 `sprint-*`）；**根级文件豁免**——`README.md`、`docs/requirements/` 的 `PRD-*.md` / `requirements-*.md` 等合法根级文件不算违规；**★ `docs/design/detail/全量/` 豁免**——它是 `/version` 正式发布生成的跨版本全量详细设计目录（非 `V*` 版本目录），合法存在、不算违规
- 确认版本目录下第二级都是合法 git user 标识（仅对按用户隔离的分类，如 `implementation/`）
- 标记任何不符合的「直挂 sprint-*」或「跨用户错写」的目录

### 9. ★ 脚手架漂移比对（约定 16 回检；仅 AIDP 脚手架项目）

- 若存在 `{{AIDP_HOME}}/../skills/aidp-code-engineer/scripts/verify.py` 且 `{version}` 已解析 → 跑 `python3 {{AIDP_HOME}}/../skills/aidp-code-engineer/scripts/verify.py . {version} {user} --read-only`（`{version}` 由「前置流程」第 2 步解析，**不写死**），把其 FAIL/ERROR/WARN（尤其契约漂移）汇总为本项状态；`{version}` 缺省 → 标 N/A
- 命中漂移 → ⚠️ 提示「重跑 `python3 {{AIDP_HOME}}/../skills/aidp-code-engineer/scripts/scaffold.py . --mode upgrade` 同步」；无 verify.py（非脚手架项目）→ 标 N/A

### 9bis. ★ 已发布 AI 报告的完整性巡检（只读）

- 跑 `python3 {{AIDP_HOME}}/scripts/emit-report.py verify-reports --json`：批量契约校验 + `_integrity`
  checksum 防篡改，扫**所有历史 build 报告 data**。退出码 `4` = 有报告契约不过 / 疑似被手改 /
  无法解析；`0` = 全部可解析且未被篡改。无 `docs/reports/` → 标 N/A。
- ⛔ **本步是该子命令唯一的常规调用方**：它守的是「报告定稿即不可变」这条承诺，
  而一份被手改或白屏的历史报告，除非有人跑它，否则永远不会有人发现。
- 命中 → 在输出里逐条列出 build 号 + 失败原因，**不自动修复**（报告定稿后只能走 `--force-amend` 留痕修订）。

### 10. ★ 项目级事实索引新鲜度 + 老版本产物体量（只读，不改任何文件）

- **索引新鲜度**（⛔ 必须过滤字段，见下）：

  ```bash
  # ⛔ 不可直接把 `show --json` 的原始输出读进上下文：它打的是**整个 state**（含全部文件的 sha），
  #    中等仓库即达百 KB、大仓可达 MB 级 —— 只读性没问题，但会把子 Agent 的上下文挤爆。
  #    只取本项真正要看的两个字段：
  python3 {{AIDP_HOME}}/scripts/code_inventory.py show --json 2>/dev/null \
    | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("N/A（索引缓存缺失或不可解析）"); raise SystemExit(0)
print(json.dumps({"generated_at": d.get("generated_at"), "counts": d.get("counts")}, ensure_ascii=False))'
  ```

  > 缓存不存在时 `show` 返回非 0、上面的分支打印 `N/A` —— **本项即标 N/A 通过**，
  > ⛔ 不得因此去跑 `update`（那会写盘，违反本命令只读声明）。判定：`generated_at` 距今明显早于最近一次代码提交时间（`git log -1 --format=%cI -- code/`）→ 提示"久未刷新，建议手动跑 `code_inventory.py update`"；需求事实由 `requirement_query.py` 读时查询，无落盘台账、不在本项检查。
  > ⛔ **本项绝不能用 `code_inventory.py update`**：`update` 会经 `save_state` 写盘
  > `memory/_facts/code-inventory.json`，与本命令「纯审计、不写产物、子 Agent 全程只读」的声明
  > 直接矛盾；更要命的是**检查会自我清除**——本项的判据正是"索引久未刷新"，而取判据的命令
  > 自己就把索引刷新了，于是第二次跑必然 `delta≈0` 报绿。"检查通过"是自己改出来的。
- **老版本产物体量**：`python3 {{AIDP_HOME}}/scripts/archive_old_artifacts.py plan --json`（**只读 dry-run**）。可归档版本的原始体积 > 100MB 或跨版本重复文件 > 100 个 → ⚠️ 建议执行归档（留仓、只是打包+去重，豁免最近 5 版）。
- ⛔ **本项只报告、绝不代为执行**：`apply` 会删文件，是否执行、豁免几个版本由用户拍板；健康检查本身是只读子 Agent。

## 输出格式

```
# 项目健康度报告
生成时间：{当前日期}
扫描范围：memory/（项目级 + 所有 {version}/{user}）+ docs/ 全部子目录

## 检查结果

| 检查项 | 状态 | 详情 |
|--------|------|------|
| 技术栈一致性 | ✅/⚠️/❌ | {具体情况} |
| 功能进度准确性 | ✅/⚠️/❌ | {具体情况} |
| ADR 完整性 | ✅/⚠️/❌ | {具体情况} |
| 约束合规性 | ✅/⚠️/❌ | {具体情况} |
| 技术债务 | ✅/⚠️/❌ | {N}条债务，{N}条超期 |
| Bugfix 闭环 | ✅/⚠️/❌ | {N}个未关闭 |
| 文件完整性 | ✅/⚠️/❌ | {缺失文件列表} |
| ★ 目录层级合规性 | ✅/⚠️/❌ | {不合规目录列表} |
| ★ 脚手架漂移比对 | ✅/⚠️/❌/N/A | {verify.py 漂移摘要；非脚手架项目或缺版本 N/A} |
| ★ 已发布 AI 报告完整性（9bis） | ✅/❌/N/A | {verify-reports 失败 build 号 + 原因；无 docs/reports/ N/A} |
| ★ 事实索引新鲜度 + 老版本产物体量 | ✅/⚠️/❌ | {code_inventory 索引是否过期；archive_old_artifacts 建议归档量} |

## 活跃上下文概览

| 版本 | 开发者 | 当前 Sprint | 最近更新 |
|------|--------|------------|---------|
| V0.1.0 | alice | Sprint-002 🚧 | YYYY-MM-DD |
| V0.1.0 | bob | Sprint-003 🚧 | YYYY-MM-DD |

## 整体评级
{✅ 健康 / ⚠️ 需要关注 / ❌ 需要立即处理}

## 需要处理的问题

### 高优先级
1. {问题} — 建议操作：{操作}

### 中优先级
1. {问题} — 建议操作：{操作}

## 建议行动
- [ ] {行动1}
- [ ] {行动2}
```
