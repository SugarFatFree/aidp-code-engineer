# /sprint-dev — A/B 共用完成前验证与 Phase 2–4

> 本片覆盖：A/B 共用完成前验证与 Phase 2–4。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

### 完成前验证

调用 `superpowers:verification-before-completion`：
- 确认本 Sprint 范围内代码已实现、无遗留 TODO
- ★ **不在开发阶段逐任务编译/校验**——后端编译 / 前端校验（lint + 类型检查，**不打包**）已收敛到 **Sprint 验收（`/sprint-test`）**，届时**仅处理本 Sprint 改动的一侧**（改前端才校验前端、改后端才编后端）且以**资源受限方式**执行（`nice` + 限并发，避免 CPU 打满），配方见 `agents/backend.md`「Step 7」/ `agents/frontend.md`「Step 4」。前端验收期只做 lint + 类型检查、**不跑完整打包**，部署打包由使用者按需自行执行。静态证据用 entry_context static 生成；普通开发仍须自动完成 related-test，真实 skip 仅受限返回

更新 `memory/{version}/{user}/activeContext.md`：
- 在「子迭代记录」中追加开发阶段的 Round 记录
- 在「已完成工作」中追加完成项
- 更新「当前工作焦点」为"开发完成，等待测试"

> ★ **若本命令触发 `git commit`**：提交前跑 `commit_gate.py --quiet`（并发写集派发时加 `--owner` 与重复 `--allow-path`，见 `incremental-contract.md`“写集派发”），每次读取完整 JSON；无需 execution-context/grant。暂存区外路径 WARN 核对归属，不覆盖他人索引。退出码3/4是欠账信号、不阻止提交；台账结构/清理异常修正复核，实际级联仅由阶段入口或显式 `--cascade-now` 触发，CICD 已启用时的 commit 提示行按约定 31.5 现场补监听。默认仅主流程写 Git，用户明确授权 worker 时须串行交接索引。

> **日常累进的推送时机**：部署触发前只复用已授权验证的当前证据；仅 commit/push/deploy 不追加测试、重回归或审计。未授权测试记 NOT_REQUESTED，不变成部署欠账。

> ★ **推送（约定 31.5，独立跑本命令时同样适用）**：先 `python3 {{AIDP_HOME}}/scripts/aidp_config.py cicd-enabled`；退出 1（未启用）→ 推送只有 `git push`，不跑脚本、不写文件。已启用才用只读 `python3 {{AIDP_HOME}}/scripts/classify_push.py --root . [--base-ref R --head H]` 分类（不落盘）：无正式代码变更且分类无错误 → 只校验 push 成功，不触发/监听远端 CICD、不跑就绪探针；正式代码变更或分类错误（fail-closed）→ 经 `python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode watch --commit "$(git rev-parse HEAD)" --env <env>` 监听本次推送触发的运行至终态，仅获 deploy grant 且预算允许才主动 retry 和运行就绪探针。规则单一信源 = 约定 31.5 +「推送分类与监听不变式」（`{{AIDP_HOME}}/flows/sprint-autopilot/invariants.md`）。

---

### Phase 2-4：自动串联后续（分支 A / B 共用 —— 串联规则单一信源）

**串联按父策略选择**：只有 related-test/review/full-cvl 获授权时才调用 `/sprint-test --execution-context "$EXECUTION_CONTEXT" [--unattended]`；原始参数与无人值守标记继续透传。test 子入口继承，不因入口名自行取得公开组合。实现修复需 implement；同根因同 inputs 未变化则停止 retry，报告事实与当前授权范围。

默认开发完成 static 后自动进入当前 task/单 Sprint 的 related-test，真实失败修复复验，再按 `light-context.md` 收口；无测试/缺工具不能当 PASS 或 NOT_REQUESTED。formal 需要关闭时进入 `/sprint-close {NNN} --execution-context "$EXECUTION_CONTEXT" [--unattended]`，只消费已要求的证据并执行原编号/归档门；不因 close 补跑测试或审计。父编排传 `skip-test` 只移交测试，不取消 related-test；仅用户真实明确 skip 按 source 限制并返回 LIMITED，不能标完整开发通过。

---


按真实授权与证据终端回传并 return。参考输出见 `{{AIDP_HOME}}/flows/sprint-dev/output-examples.md`，不预读输出示例。
