# {{AIDP_HOME}}/hooks/ — Hook 脚本（autopilot Stop 护栏 + PreToolUse 入口/测试范围护栏）

## 文件说明

| 文件 | 说明 |
|------|------|
| `autopilot-stop-guard.py` | **Stop Hook**，autopilot 执行态下「收尾门没过不许结束」的结构级兜底（`exit 2` 阻止结束、迫使补产）|
| `pretool-guard.py` | **PreToolUse Hook**，入口协议不可跳过 + 测试范围机器强制（`exit 2` 阻断工具调用并提示补哪一步）|

---

## autopilot 收尾门 Stop Hook（`autopilot-stop-guard.py`）

把 `/sprint-autopilot`「命令收尾硬门」从「执行体自律」提为结构级——Agent 试图结束轮次时触发，检测到「autopilot 正处执行态且收尾门 `exit 1`（仪式产物缺失）」→ `exit 2` 阻止结束、迫使继续补产（build / AI执行报告 / 里程碑通知 / 委派测试）。

**作用域：只拦「本会话 / 本进程正在执行 `/sprint-autopilot` tick」的轮次**。判据（任一）：
- 环境变量 `AIDP_TICK_COMMAND=sprint-autopilot`（`agent_loop.sh` / `aidp_scheduler.py` 调度时注入）；
- Stop 输入的 transcript 中最后一条用户输入是 `sprint-autopilot` 命令调用（Claude Code / DeepSeek Harness 为 `/sprint-autopilot`，Codex 为 `$sprint-autopilot`，含 `/loop … /sprint-autopilot`）。

测试链路（`AIDP_TICK_COMMAND=sprint-aiauto-test`）与同一项目里人的普通对话一律放行。

**⛔ 安全第一（本 hook 全局每轮触发，多重 fail-open 保证绝不误 wedge 正常对话）**：
1. **逃生舱**：`touch memory/.autopilot-stop-guard-off` → 立即放行（临时禁用，优先级最高）。
2. **配置开关**：`memory/aidp-config.yaml` 的 `stop_guard.enabled: false` → 放行。
3. **无待收口流水线放行**：非 autopilot tick 轮次 / baseline 缺失 / run_state 无活跃 phase / 有唤醒源且只是让位下一 tick（`next_sprint` 未跑完或 `next_phase` 为 `3.2.1-*` 跨 tick 等待游标）→ 不干预。
4. **判不出 version/build、脚本缺失、任何异常** → 放行（永不因自身故障 wedge）。
5. **熔断上限**：同一 build 连续阻止达 3 次仍未过 → fail-open 放行 + 告警交人工（防无限 wedge）。

只有【全部确定信号齐备 + 收尾门确定 `exit 1` + 未达熔断上限】才 `exit 2`。计数文件 `memory/.aidp/stop-guard-count`（收尾门通过即清）。 每次「本可介入却放行」的 fail-open（如判不出来）留痕于 `memory/.aidp/stop-guard-skips.jsonl`。

**项目根目录解析**（兼容多宿主）：`CLAUDE_PROJECT_DIR` → `CODEX_PROJECT_DIR` / `DSH_PROJECT_DIR`（若宿主注入）→ `git rev-parse --show-toplevel` → 当前工作目录。

---

## PreToolUse 护栏（`pretool-guard.py`）

一个脚本、两道独立的门，按工具输入解析；缺少任一步均拒绝本次工具调用，提示补齐后重试。

| 检查 | 触发范围 | 校验 |
|---|---|---|
| 入口门 | Edit / Write / MultiEdit / NotebookEdit / apply_patch，以及 Bash 的可识别写入 | `entry_gate.py` 统一校验本任务已 resolve、已读取 branch-policy、持有 implement、目标在非空 write_set 内；formal 和无人值守 tick 不豁免 |
| 测试范围门 | Bash / Codex shell 命令 | `test_command_guard.py evaluate` 拒绝无参、目录、越界、未授权全量测试及 git stash，保留相关测试/失败基线提示 |

**上下文绑定**：只接受 `AIDP_EXECUTION_CONTEXT` 或入口明确写入的任务标记，不再扫描最近 24 小时内的任意上下文。上下文须通过 `entry_context.load_context` 身份校验，属于当前根、active 且新鲜；显式指向错误时直接拒绝，不回退另一任务。任务关闭即失效。分支读取标记必须属于当前根且与实时 policy/status 一致，偏好变化须重读。

```bash
# resolve 与 branch-policy 成功后，light_task start 会执行对应绑定；手工入口可显式绑定
python3 {{AIDP_HOME}}/scripts/entry_gate.py bind --root . --execution-context "$EXECUTION_CONTEXT" --json
# 宿主提供 session_id 时使用同一个实际标识；拒绝提示会带出该值
python3 {{AIDP_HOME}}/scripts/entry_gate.py bind --root . --execution-context "$EXECUTION_CONTEXT" --session-id "$AIDP_SESSION_ID" --json
```

有 `session_id` 的 hook 只读取同会话标记，不回退项目标记；没有会话标识时，`memory/.aidp/entry-task.json` 只代表显式选定的串行项目任务，不能宣称会话隔离。并行调用须传递各自上下文或 session 绑定。只读检查不续期、不创建绑定。

**Bash 支持范围**：`shell_write_targets.py` 静态识别 `sed -i/-iSUFFIX`（含备份写入）、`> / >> / >|`、tee、cp/mv/install、rm 等常见写目标，理解常量环境变量、export、cd、相对/绝对路径、目录目的地、bash/sh `-c` 包装及可识别 Python `-c` 的 open/Path 写入。Codex 支持字符串 `command/cmd` 和 argv 数组（先 quote，不直接拼接），并使用工具的 cwd/workdir。纯读 sed/cat/rg、只读 JSON 解析与入口 bootstrap 保持可用。

**官方 tick 引导的窄兼容**：仅识别 `eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"`，允许追加选择命名空间的 `--command autopilot|aiauto-test`。脚本路径必须解析到当前 helper 同一安装目录的 `autopilot_tick_flags.py`，且 eval 只有这一个完整命令替换参数；不接受外部同名脚本、其他子命令、拼接额外命令或任意变量 eval。识别依据是该本地脚本用 `shlex.quote` 输出赋值的既定契约，解析器不执行脚本、不采信任意脚本输出。导出结果仍是动态值，不能据此把变量写目标当作确定路径。

固定路径的元数据输出后接 `|| exit $?` 不再误拒。官方条件围栏仅通过重定向和 `mkdir` 写当前工作目录下 `memory/.aidp/` 的字面路径时，允许分支决定是否写入；仍逐目标经过入口门及符号链接检查，混入 `ln/cp/mv` 等改变路径含义的操作不适用此例外。不豁免变量写目标、cwd 变化或条件分支中改写命令别名；其他复合写入保持保守拒绝。官方部署围栏的版本参数显式传 argv，分支结果各用固定文件名，不把末次变量赋值当成全部分支的写集。已识别的只读消费者（包括 JSON 解析的 Python `-c`）可用 `<<<` 输入数据；把 stdin 作为程序的裸 bash/python、未知 eval 和未解析 here-document 仍拒绝。真实 autopilot 围栏中的常量命令别名按词拆分解析，不执行别名来判安全。

官方预算围栏直接捕获 `execution_policy.py reserve-budget` 的 JSON stdout，用只读 `<<<` 提取预留 ID 后结算；预算校验与失败退出保持不变，不再通过 `mktemp` 输出路径做 shell 重定向。解析器不将 `mktemp` 输出当作可信写目标，避免 `TMPDIR`、自定义模板或组合命令把写入引向业务目录。

未解析变量、动态写目标、无法确认的 Python 调用或复合写入会明确拒绝，提示先走入口并拆成显式路径命令；即使入口已完成也不会把未知写目标当成 write_set 内。它不解释任意外部程序/脚本正文，不是覆盖所有恶意绕过的 shell 沙箱；未触发宿主 hook 的专用工具仍不受它拦截。

**独立开关与迁移**：

| 门 | 配置（默认 true） | 临时逃生文件 | 对另一道门 |
|---|---|---|---|
| 入口门 | `entry_guard.enabled` | `memory/.entry-guard-off` | 不影响测试范围门 |
| 测试范围门 | `test_guard.enabled` | `memory/.test-guard-off` | 不影响入口门 |

旧 `memory/.pretool-guard-off` 保守兼容为**仅关闭入口门**，不再关闭测试范围门；迁移时改用 `.entry-guard-off` 后删除旧文件。旧 `entry_guard.enabled: false` 同样仅影响入口。需要恢复入口门时，也须删除旧文件；故障排除后分别恢复配置/删除相应逃生文件。这些本地文件均由 gitignore 模板排除。

目标工具的坏输入、缺模块、内部校验异常或缺少明确判定均 `exit 2`，不静默放行测试命令；日志沿用 `memory/.aidp/pretool-guard-skips.jsonl` 文件名，但记录 `decision: deny`，滚动保留 50 条。非目标工具正常放行。阻断采用 `exit 2` + stderr，`--agent codex` 另输出 deny JSON。

**宿主能力**：Claude Code / Codex 由 `agent_sync.py` 装配；DeepSeek Harness 的 PreToolUse 官方契约仍未证实，不装配、不声称支持。无 hook 时按命令协议运行 `entry_gate.py check` 与 `test_command_guard.py wrap`，详见 `{{AIDP_HOME}}/reference/agent-tools.md` 第五节。

---

## 环境要求

- Python ≥ 3.9（标准库，无需安装额外依赖）。模板仓库 `.aidp` 中的 hooks 仅作维护源；下游脚本位于当前 Agent 的 `{{AIDP_HOME}}/hooks/`。无 Git 时使用宿主项目根或当前工作目录回退，不能把 Git 步骤标成通过。

---

## 多 Agent 接线

> ✅ **下游项目无需手动配置**：接线由 `aidp-code-engineer` 脚手架在 **init / migrate / upgrade** 时自动完成，日常也可用 `python3 {{AIDP_HOME}}/scripts/agent_sync.py` 按当前启用的 Agent 幂等补齐——脚本本体只有 `{{AIDP_HOME}}/hooks/` 这一份，各宿主的配置文件只写「Stop / PreToolUse 事件 → 调对应脚本」，保留你已有的其它 hook / 配置。手工配置仅用于排查。

| Agent | 配置文件 | 接线方式 |
|------|---------|---------|
| **Claude Code** | `.claude/settings.json`（项目级共享，随 git 提交）| `hooks.Stop` 挂 `python3 {{AIDP_HOME}}/hooks/autopilot-stop-guard.py`；`hooks.PreToolUse`（matcher `Bash\|Edit\|Write\|MultiEdit\|NotebookEdit`）挂 `pretool-guard.py` |
| **Codex** | `.codex/hooks.json` | Stop 事件挂同一命令（带 `--agent codex`）；PreToolUse（matcher `Bash\|shell\|shell_command\|exec_command\|local_shell\|apply_patch\|Edit\|Write`）挂 `pretool-guard.py --agent codex`；须在 `.codex/config.toml` 中开启 `[features] codex_hooks = true`，且项目需被 Codex 信任（trust）才会加载项目级 hooks |
| **DeepSeek Harness** | `.dsh/hooks.json` | Claude Code 格式，Stop 事件挂同一命令（带 `--agent dsh`），由 DeepSeek Harness 的 hooks 插件加载（加载方式以所用版本官方文档为准）；**PreToolUse 未证实，不写入**（`agent_sync.py` 输出 `notes` 说明） |

Claude Code 配置示例（`.claude/settings.json`，已有内容时合并 `hooks` 字段）：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 {{AIDP_HOME}}/hooks/autopilot-stop-guard.py" }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          { "type": "command", "command": "python3 {{AIDP_HOME}}/hooks/pretool-guard.py" }
        ]
      }
    ]
  }
}
```

Codex 配置示例（`.codex/hooks.json`）：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 {{AIDP_HOME}}/hooks/autopilot-stop-guard.py --agent codex" }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash|shell|shell_command|exec_command|local_shell|apply_patch|Edit|Write",
        "hooks": [
          { "type": "command", "command": "python3 {{AIDP_HOME}}/hooks/pretool-guard.py --agent codex" }
        ]
      }
    ]
  }
}
```

```toml
# .codex/config.toml
[features]
codex_hooks = true
```

> Codex 对非托管 hook 要求先在 `/hooks` 评审信任（hook 定义或脚本变更后需重新信任），未信任前新装配的 hook 不会运行。

> 命令使用相对路径，须以**项目根目录**为工作目录启动 Agent 会话；宿主未注入项目目录变量时，脚本会回落到 git 根解析。

---

## ⛔ 维护边界（约定 16）

- `agent_sync.py` 只识别并替换**自己托管**的 hook 命令，用户已有的 Stop / PreToolUse 配置原样保留；同名外部脚本不当作托管命令。
- hook 由脚手架下发并自动接线，下游无需手工配置；改动请在模板项目本体修改后镜像进脚手架。
- 本文件是**脚手架契约文件**，随 `aidp-code-engineer` 下发/升级同步——下游直接手改会在下次升级被覆盖。
