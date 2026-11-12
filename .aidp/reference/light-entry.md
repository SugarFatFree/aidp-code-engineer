# light 精简入口（日常开发/修复默认路径，按需 Read）

> 本文件是 light 任务的**速览入口**：普通 `/sprint-dev`、`/sprint-bugfix` 走下面的固定流程即可，**不必通读** `flows/sprint-dev/light-context.md`（执行策略单一信源，20KB）。仅在下方「何时再读全文」所列情形才按节 Read 它；formal 路径不使用本文件。

## 1. 固定流程（一步一个命令）

```bash
# ① 入口：resolve + route(dev) + 读取分支策略 + 绑定本任务（嵌套/续跑只继承 --execution-context）
python3 {{AIDP_HOME}}/scripts/light_task.py start --root . --version "{version}" \
  --write-set "{实际写集路径}" --acceptance "{本轮可核验业务结果}"
# branch_needs_choice=true 时先按项目记忆的「工作分支偏好」保存选择，再带返回的 context 重跑 start。
```

宿主提供会话 ID 时，给 `start` 传 `--session-id`（或设置 `AIDP_SESSION_ID`），与 hook 的 `session_id` 对齐；被拦截时按提示中的当前会话 ID 绑定。只有 `entry_bound=true` 才完成编辑前置。无会话 ID 的宿主使用明确的项目任务标记；并行子 Agent 必须传各自 `AIDP_EXECUTION_CONTEXT`，不能依赖共享标记切换任务。测试范围校验和入口校验分别控制，开关与适配说明见 `agent-tools.md`。

② **实现**：只改写集内文件。**编辑 `code/**` 之前显式 Read 对应规则**（Codex / DeepSeek Harness 没有按路径自动加载，漏读即漏守约定）：`code/frontend/**` → `{{AIDP_HOME}}/rules/frontend.md`；`code/backend/**` → `rules/backend.md`；任意 `code/**` → `rules/code.md`；其余路径无需读。
③ **静态**：按 `flows/sprint-dev/verification-inputs.md` 先跑只读 `plan-validation`，再按项目工具链检查；缺工具/失败如实保留。
④ **相关测试 + 汇总**（一条命令完成 选测 → 执行 → 汇总）：

```bash
EXECUTION_CONTEXT="{start 返回的 execution_context}"
python3 {{AIDP_HOME}}/scripts/light_task.py all --root . \
  --execution-context "$EXECUTION_CONTEXT" --runners-json "$UNIT_RUNNERS_JSON" --env-id "$TEST_ENV_ID"
# 也可分步：select（选测+白名单）→ run（命令守卫 + test_ledger run-scope + verify）→ report（verdict）
```

⑤ **读 report**：`verdict=PASS` 直接收口；`FAIL` 看 `known_failure_diff.new_failures`，真实新失败交原实现者修复（自有 `bugfix` SKILL，`report_mode=evidence-only`；传父 context 与明确 failures/真实证据/写集/验收，见 `reference/skills.md`，不创建问题 Markdown）后只复验失败项（`run --reselect`）；`UNVERIFIED`/`unmapped`/`unrunnable` 如实列出，不得写成已覆盖或 PASS。
⑥ **开发任务收口**：`entry_context.py check`（本任务必要证据齐备后 `complete`；只有上下文已有交付 grant 才要求相应回执，纯交付请求不走本步），参数取自 report 的 `scope_hash`、`run_ids`、`env_id` 与 static 的 `evidence_file`；围栏见 `light-context.md`「close」。终端结果按 task 范围列 PASS / 不适用 / 未执行 / FAIL / 阻塞，不写报告 Markdown、不建 Sprint。

## 2. 硬边界（脚本与 hook 会拦，别绕）

| 事项 | 做法 |
|---|---|
| 测试命令 | 只跑显式测试文件/节点 ID；**禁止整目录、无参数、全量**（`test_command_guard.py` 拒绝，`light_task.py` 不生成此类命令）；手工运行也走 `test_command_guard.py wrap -- CMD...` |
| 失败基线 | **禁止 `git stash` 对照**；已有失败用 `test_baseline.py record/diff` 的「已知失败基线」，只处理「新失败」 |
| 长时测试 | 后台跑用 `test_command_guard.py wrap --background --log FILE -- CMD...`，Monitor 等 `FILE.exit`，不轮询 sleep |
| 授权 | 默认只有 `implement`、`static`、`related-test`；review / full-cvl / 文档须本轮真实请求，不得自行追加；普通 commit / push / deploy 由用户一句话授权，只做 git commit、git push、项目现有部署脚本，不建 context/grant/回执文件，不为纯交付调用 check/complete |
| 普通推送 | 按约定31.5：CICD 未启用不观察；启用且分类需监听时只读 `cicd_watch.py`，现场取得 commit，不需 version/context、不写 baseline、不 trigger/retry/探针 |
| 无 Git | 可开发、显式文件本地测试、本地归档；自动 test_scope/相关证据链需有效 commit，记 `UNVERIFIED / unsupported:vcs-disabled`，不称完整闭环、不自动 `git init` |
| 范围 | 写集扩大先 `entry_context.py revise`；light 不建 Sprint/卡片，不改 activeContext/progress |
| 部署资产 | `docs/deployment` 内相关数据库脚本、实际配置文件可随开发/修复实时更新；操作手册、说明、清单和台账等文档性内容集中在版本规划/正式发布整理 |
| 并行 | 可拆成 ≥2 个互不相交写集（各读≥3 或改≥2 文件）时按 `flows/sprint-dev/light-parallel.md` 先跑 `dispatch_plan.py` |

## 3. 何时再读 `light-context.md` 全文（按节）

- 增加/撤销动作授权、`authorization_source`、`revise` → 「入口、继承与 grant revision」
- 直接调用工具/Agent、预算 reserve/settle、失败与重试规则 → 「执行围栏、预算与失败」
- 规模预判 `development_scope.py`、C 号登记、用例族 defer → 「prepare / dev / repair」
- review / full-cvl / 等价证据 / 已授权 commit·push·deploy 收口 → 「test」「close」
- 子命令嵌套、`bind-sprint`、fork → 「入口、继承与 grant revision」末段

## 4. 输出与退出码（`light_task.py`）

stdout 末行恒为 JSON。退出码 0 = 已核验成功或明确 NOT_APPLICABLE；1 = 测试 FAIL / 存在新失败；2 = 输入错误、授权缺失、命令守卫拒绝或未核验。`report.verdict` 取值：`PASS`、`PASS_WITH_GAPS`、`KNOWN_FAILURE_ONLY`、`FAIL`、`UNVERIFIED`、`NOT_APPLICABLE`。
