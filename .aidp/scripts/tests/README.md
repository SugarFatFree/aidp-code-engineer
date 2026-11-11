# .aidp/scripts/tests/ — 确定性脚本回归单测

防「产出即错、直到人肉发现才知道」——把发现时机前移到脚本产出时。覆盖四条链路：**AI 报告**（契约 + 渲染）、**提交前门禁与推送分类**、**里程碑通知 / 多 Agent 装配**、**确定性护栏**。

> ★ **新增测试文件必须【同时】登记进 `run.sh` 与下方文件表**：漏登 `run.sh` = 该套件永远绿不了也红不了（`test_guard_scripts.py` 的「run.sh 收录全部 test_* 文件」用例会机器回检）；漏登文件表 = 维护者按表核对时会以为它不存在，改动相关脚本时不会想到要跑它。

**执行范围以根 `AGENTS.md`「维护验证：默认按影响范围」为准**：日常选择下表中受影响的测试或用例；审计、提交本身不要求全量。需要完整验收时，在仓库根运行 `bash .aidp/scripts/tests/run.sh`，末尾汇总「套件数 · 断言 passed / failed / skipped」，任一套件失败即非零退出。它已包含脚手架侧测试，无需再单独重复跑整个脚手架测试目录。

| 文件 | 覆盖 | 运行 | 依赖 |
|------|------|------|------|
| `test_report_schema.py` | `emit-report.py` 数据契约校验（`validate_payload`）+ `buildNo` 派生 + **示例文件自校验（示例即契约、永不分叉）** + 改坏必红 | `python3 .aidp/scripts/tests/test_report_schema.py` | Python 标准库；③④ 加载 JS 示例需 `node`（缺则跳过、非失败） |
| `test_report_render.js` | 渲染口径（`pct` 经渲染路径：0.84→84%、100.0→100% 不出 10000%）+ 坏数据健壮性（risks 分组对象不白屏 / cases 别名无 undefined / 无 buildNo 不 `#undefined`） | `node .aidp/scripts/tests/test_report_render.js` | `node` |
| `test_report_lightbox.js` | 截图灯箱交互：滚轮缩放（含以光标为锚点、上下限、阻止页面滚动）、放大后拖拽平移、双击复位、换图重置。⛔ 判据是**真触发 wheel/mousedown 再断言 transform**，不是「源码里有没有 wheel 字样」——那种字符串匹配改坏了照样绿 | `node .aidp/scripts/tests/test_report_lightbox.js` | `node` |
| `test_release_unit_report.js` | 发布测试报告独立保留实测/单测事实，失败与未核验不判绿，历史兼容 | `node .aidp/scripts/tests/test_release_unit_report.js` | Node.js |
| `test_commit_gate.py` | `commit_gate.py`（约定 24）：模板项目判定 / 业务代码与纯脚手架判定 / 约定 22 台账积压（stale、多态识别、已级联未清理、归档标记、格式漂移）/ `suspected_cascade_bypass` / 约定 41 `offchain` 档位 / `pending_cicd` 推送欠账 / CLI 退出码 0·3 与 `--quiet` 告警恒打印 / `commit_gate.enabled` 总开关；另含 `classify_commit_change` · `classify_push` 分类（按 commit 键控记录、部署终态） | `python3 .aidp/scripts/tests/test_commit_gate.py` | Python 标准库 + `git` |
| `test_alloc_id.py` | 原子号段分配：历史取号、作用域交叠、账本损坏、空洞与引用、并发锁 | `python3 .aidp/scripts/tests/test_alloc_id.py` | Python 标准库、POSIX 文件锁 |
| `test_test_ledger.py` | 真实测试执行与PASS复用：内容树、范围/命令/环境/输入隔离、并发、失败与树漂移、验收快照及差量 | `python3 .aidp/scripts/tests/test_test_ledger.py` | Python 标准库、POSIX 文件锁、Git |
| `test_test_scope.py` | Sprint 单测确定性推导（按运行器分组、无对应单测、无运行器、不回落全量）+ `run-scope` 逐套记账（PASS 复用/FAIL/EMPTY）+ 全量单测 worktree 账本复用（清理后仍命中） | `python3 .aidp/scripts/tests/test_test_scope.py` | Python 标准库、Git |
| `test_entry_context.py` | 轻量/正式身份、嵌套续跑、正式子任务、真实完成门及族义务 | `python3 .aidp/scripts/tests/test_entry_context.py` | Python 标准库、Git |
| `test_execution_policy.py` | 分离动作授权、共享预算、无变化工具失败终止与显式等价证据 | `python3 .aidp/scripts/tests/test_execution_policy.py` | Python 标准库、临时 Git |
| `test_scope_performance.py` | 同树分析缓存、资源映射、子模块指纹、计划去重与安全合批 | `python3 .aidp/scripts/tests/test_scope_performance.py` | Python 标准库、临时 Git |
| `test_verification_tools.py` | 项目配置与 CI 验证命令选择、语法/lint/类型/编译/单测分类、只读 shell/容器边界 | `python3 .aidp/scripts/tests/test_verification_tools.py` | Python 标准库、离线工具替身 |
| `test_deployment_ops.py` | 备份频率与真实回执、跨类型并发限额、待同步操作指引和精简 SQL 台账 | `python3 .aidp/scripts/tests/test_deployment_ops.py` | Python 标准库、临时 Git、离线命令替身 |
| `test_development_scope.py` | 风险与文件成本分离、真实SQL差异与基线不确定性 | `python3 .aidp/scripts/tests/test_development_scope.py` | Python 标准库、临时 Git |
| `test_sprint_baseline.py` | `baseline_ref` 解析：契约卡/透传/工作区未提交/merge-base≠HEAD/none，非祖先与选项形态拒绝，无 Git 标注 | `python3 .aidp/scripts/tests/test_sprint_baseline.py` | Python 标准库、临时 Git |
| `test_audit_carryover.py` | version-auditor 结转：轮次 +1、Important 连续 3 轮升级 Critical、Warning 不升级、回检轮次与升级标记、零重合 WARN | `python3 .aidp/scripts/tests/test_audit_carryover.py` | Python 标准库 |
| `test_plan_ac.py` | 计划验收标准形式初筛：空白/占位/套话/过短无落点命中、链接与反引号命令放行、随附样例零命中 | `python3 .aidp/scripts/tests/test_plan_ac.py` | Python 标准库 |
| `test_sql_reorg.py` | SQL 整理语句守恒：多重集合比对、0 条与空侧 fail-closed、回滚脚本排除 | `python3 .aidp/scripts/tests/test_sql_reorg.py` | Python 标准库 |
| `test_sprint_discovery.py` | 计划分册/启动/归档/关闭共同发现，保留证据分域 | `python3 .aidp/scripts/tests/test_sprint_discovery.py` | Python 标准库、临时 Git |
| `test_light_task_flow.py` | 默认开发/修复的相关单测闭环、断言修改必实跑、明确跳过的受限结论；临时 Git/离线部署复用测试证据，重复收尾不重放，已有 Sprint 字节不变 | `python3 .aidp/scripts/tests/test_light_task_flow.py` | Python 标准库、Git、离线部署替身 |
| `test_build_unit_test.py` | 部署完整提交隔离执行、并发缓存、超时清理 | `python3 .aidp/scripts/tests/test_build_unit_test.py` | Python 标准库、Git、Node（报告渲染） |
| `test_unit_report.py` | 全量单测/实测独立展示、缺证据不能通过、旧报告兼容 | `python3 .aidp/scripts/tests/test_unit_report.py` | Python 标准库、Git、Node（报告渲染） |
| `test_aiauto_test_join.py` | 单测失败幂等登记、未核验不冻结、准发布状态 | `python3 .aidp/scripts/tests/test_aiauto_test_join.py` | Python 标准库、Git、Node（报告渲染） |
| `test_aiauto_parallel.py` | 真实并行替身、执行器→报告→状态汇总、不同build复跑 | `python3 .aidp/scripts/tests/test_aiauto_parallel.py` | Python 标准库、Git、Node（报告渲染） |
| `test_notify.py` | `notify.py`（约定 32）：feishu / dingtalk / wecom / lark-cli / command 渠道渲染与发送、飞书 · 钉钉签名、`--auto` 渠道回落、`--sender`、`--print-only` / `--json` 结构、退出码 0/1/2/3、项目名解析与 `--check-name`、发送成功才登记台账 | `python3 .aidp/scripts/tests/test_notify.py` | Python 标准库（本地 127.0.0.1 HTTP 桩 + 假 lark-cli，不联网） |
| `test_delivery_boundaries.py` | 通知配置本地诊断、受管缺键补齐、上传失败回落与只补交付 | `python3 .aidp/scripts/tests/test_delivery_boundaries.py` | Python 标准库、离线替身 |
| `cicd_watch.py --selftest`（脚本自带，非本目录文件） | CICD 多提供方监听（`cicd_watch.py` + `cicd_providers.py`）的离线自测，由 `run.sh` 一并调起 | `python3 .aidp/scripts/cicd_watch.py --selftest` | Python 标准库 |
| `test_agent_sync.py` | `agent_env.py`（detect / memory-file / `--self-check`）+ `agent_sync.py`（临时 git 仓库装配 Claude Code / Codex / DeepSeek Harness、记忆文件搬迁、幂等、`--check` 漂移、copy 模式、清理与合并、`--self-check`） | `python3 .aidp/scripts/tests/test_agent_sync.py` | Python 标准库 + `git` |
| `test_guard_scripts.py` | 确定性护栏全套（分组清单见下方「test_guard_scripts.py 分组」——**该表是唯一信源**，其它文档只放指针、不复制清单也不复制组数） | `python3 .aidp/scripts/tests/test_guard_scripts.py` | Python 标准库；脚手架内部集成断言默认执行，缺少必要外部工具时按具体用例报告 SKIP |
| `test_baseline_archive.py` | baseline 归档/迁移链路（`baseline_archive` 归档范围 + 墓碑判据 + `baseline_edit get` 归档回落 + `autopilot_decisions` 双信源） | `python3 .aidp/scripts/tests/test_baseline_archive.py` | Python 标准库 |
| `test_field_level_and_evidence.py` | 写读错层（`decidable_skips` 版本级/build 级）+ memory 保护面 + flock 锁路径单一信源 + 运行时产物落点收编（`aidp_paths` / `aidp_config` / `commit_gate` 同口径） | `python3 .aidp/scripts/tests/test_field_level_and_evidence.py` | Python 标准库 |
| `test_offchain_scope.py` | 约定 41 链外档位（`commit_gate.py::offchain_budget` 的 XS/S/M/L 分档与动作预算）+ 链外推送欠账 + 约定 17 反向门 | `python3 .aidp/scripts/tests/test_offchain_scope.py` | Python 标准库 |
| `test_release_gates.py` | 发布期硬门（`check_release_residual_gate.py` 等的双侧对照 + 各脚本 `--self-check`） | `python3 .aidp/scripts/tests/test_release_gates.py` | Python 标准库 |
| `test_report_immutability.py` | 报告不可变门（已 finalize build 的篡改检出 + skeleton 期前移）+ driver 如实性窗口 + `renderMode` 取证来源 | `python3 .aidp/scripts/tests/test_report_immutability.py` | Python 标准库 |
| `test_unattended_recovery.py` | 无人值守失败处置与自动恢复：`autopilot_fail_handle.py --command` 按链路取唤醒源、同 reason 冻结幂等、未达阈不发通知、冻结写本地告警台账 `memory/.aidp/alerts.jsonl`；`autopilot_unfreeze.py` 环境类复探（退避 + 上限）/ `--clear` / `--manual`；推送围栏「合并到部署源」失败即中止并切回开发分支、`DEV_BRANCH` 登记；`autopilot_tech_boundary.py` 技术边界预确认判定 | `python3 .aidp/scripts/tests/test_unattended_recovery.py` | Python 标准库 |
| `test_stop_guard.py` | 缺build与handback失败的Stop阻止上限、告警去重及成功清计数 | `python3 .aidp/scripts/tests/test_stop_guard.py` | Python标准库、真实hook进程 |
| `test_unattended_edges.py` | JSON渲染取证正反例、实测参数、脏树默认及旧运行路径说明 | `python3 .aidp/scripts/tests/test_unattended_edges.py` | Python标准库、Bash |
| `test_dispatch_retry.py` | C1/C2退避封顶、无唤醒源失败处置、成功清零及实际规划围栏 | `python3 .aidp/scripts/tests/test_dispatch_retry.py` | Python标准库、Bash |
| `test_cicd_deployment.py` | CICD降级probe、need-accept边界、即时冻结及成功出口 | `python3 .aidp/scripts/tests/test_cicd_deployment.py` | Python标准库、离线提供方替身 |
| `test_planning_orchestration.py` | 版本规划编排层：SKILL 阶段计量与 `规划耗时.md` 渲染 / `--qr-level` 透传与移交清单结清门（用各 SKILL 自己的 `qr_orchestration.py` 写清单对账）/ Critical 维度永不移交 / `--fast` 发布前补审 / PRD 行对账表 / 计划‖自测并行回填围栏实跑 / Sprint 开工范围与真实归档门 | `python3 .aidp/scripts/tests/test_planning_orchestration.py` | Python 标准库 + bash |
| `test_aidp_scheduler.py` | `aidp_scheduler.py`（7×24 操作系统调度）：systemd / crontab / launchd / schtasks 渲染、周期解析、install / uninstall / status、心跳巡检告警、`agent_loop.sh --once` 参数补齐 | `python3 .aidp/scripts/tests/test_aidp_scheduler.py` | Python 标准库 |
| `test_agent_sync_router.py` | Codex / DeepSeek Harness 原生命令生成、Codex frontmatter 与 `$ARGUMENTS` 正文保真、命令/SKILL 重名保护、`--check` 漂移、gitignore 托管块去重 | `python3 .aidp/scripts/tests/test_agent_sync_router.py` | Python 标准库 + `git` |
| `test_runtime_and_vcs.py` | `.aidp` / `.claude` / `.agents` 平铺运行根 + 降层前嵌套旧形态（`.claude/aidp` / `.agents/aidp`）的运行根与项目根解析、环境覆盖路径 containment、`git|none` 能力检测、开发者身份四级回落、`unsupported: vcs-disabled` 结构 | `python3 .aidp/scripts/tests/test_runtime_and_vcs.py` | Python 标准库；Git 阳性用例用临时仓库（不可用则仅该用例跳过） |
| `test_runtime_paths.py` | 下发运行契约中的 `{{AIDP_HOME}}`、根 `.aidp/` 硬编码和渲染态未解析 token 守卫 | `python3 .aidp/scripts/tests/test_runtime_paths.py` | Python 标准库 |
| `test_command_skill_contracts.py` | 命令 ↔ SKILL 调用契约：脚手架调用形态、SQL 两轨、CVL 仅验收与基线/分级边界、bugfix 输入面、质量门委派、发布欠账、写前快照；实跑 aiauto 四格式截图归集与最新轮覆盖、client_mcp 新旧声明、gen_report 失败不收敛/巡检分流、SPA 字段映射 | `python3 .aidp/scripts/tests/test_command_skill_contracts.py` | Python 标准库 + `git` + bash + `jq` |
| `test_remaining_tools.py` | 探针红绿还原、缓存输出/身份、整版预算、用例延期收口、Phase 生命周期、阶段族过滤与解冻、版本事实快照指纹、约定 38 反向对账 | `python3 .aidp/scripts/tests/test_remaining_tools.py` | Python 标准库；bash |
| `test_batch_probe.py` | 批量阳性对照：阴性侧必须绿、阳性侧变红、失败后按快照还原目标文件 | `python3 .aidp/scripts/tests/test_batch_probe.py` | Python 标准库 |
| `test_preflight_cache.py` | 前置检查成功结论按 run_id + 输入指纹缓存，失败不缓存、跨 tick 不复用 | `python3 .aidp/scripts/tests/test_preflight_cache.py` | Python 标准库 |
| `test_ceremony_cards.py` | full / incremental / test-only 的部署与静态分支期望通知集 | `python3 .aidp/scripts/tests/test_ceremony_cards.py` | Python 标准库 |
| `test_execution_contract_lite.py` | 精简执行契约 ↔ 权威枚举的三方对账：`auto-test-runner/references/execution-contract-lite.md`（执行子 Agent 默认只读这一份）把 `status` / `block_reason` / `execution_mode` / `mechanism` / `entry_kind` 五组枚举**抄了一遍**，本套件逐组比对它与 `scripts/check_result.py` 常量、`assets/result-schema.json` 的 `$field_notes`。⛔ 每个用例先断言「解析到的枚举值个数 > 0」——本门的失效形态与通过同形（正则认不出写法 ⇒ 空集合相等 ⇒ 绿） | `python3 .aidp/scripts/tests/test_execution_contract_lite.py` | Python 标准库 |
| `test_doc_reference_guards.py` | 文档引用与开源卫生三道门，及后补四道文档描述面守卫（`check_readme_registry.py` README 登记 / `check_cn_count_claims.py` 中文数字计数 / `check_stale_phrases.py` 陈旧短语黑名单 / `check_identity_source.py` 扫描面扩到 `agents/` 与 `docs/init/`，另 `check_loop_examples.py` 的 `--no-loop` 判据在 `test_guard_scripts.py`）：`check_code_symbol_refs.py`（`脚本::符号` 存在性）/ `check_cli_invocation.py`（子命令与 flag 归属）/ `check_private_markers.py`（内网地址 / 主机名 / MCP 服务名 / 下游项目名 / 示例子项目名 / 本地名单）双侧对照 + `--self-check` | `python3 .aidp/scripts/tests/test_doc_reference_guards.py` | Python 标准库 |
| **脚手架侧（不在本目录、由 `run.sh` 一并调起）** | `skills/aidp-code-engineer/scripts/tests/` 下的 `test_mirror.py` / `test_scaffold_lib.py` / `test_runtime_layout.py` / `test_installed_init_docs.py` / `test_scaffold_modes.py` / `test_verify_guard_observability.py` / `test_bundle_skill_mask.py` / `test_sync_memory_md.py` / `test_downstream_portability.py` / `test_dsh_plugin_state.py` | 见 `run.sh`「脚手架 skill 侧」段 | Python 标准库 |
| `sync_group_table.py` | 维护工具：把 `test_guard_scripts.py` 的实跑分组同步进本 README 的分组表 | `python3 .aidp/scripts/tests/sync_group_table.py` | Python 标准库 |
| `fixtures/*.js` | AI 报告数据缺陷形态的回归样本（脱敏） | — | — |
| `run.sh` | 一次跑全部 | `bash .aidp/scripts/tests/run.sh` | 同上 |

## 范围测试成本复现（手动）

`benchmark_scope_cost.py` 使用临时 Git 仓库和真实 unittest 比较同一冻结输入下的 derive、依赖分析、内容快照、测试进程、scope/ledger 字节数及耗时。例：`python3 .aidp/scripts/tests/benchmark_scope_cost.py --repo . --out memory/.aidp/scope-cost.json --files 16`。`--files` 支持 1–512；前后比较保持脚本、解释器与文件数一致，只切换 `--repo` 指向的实现。该工具不加入 `run.sh`，避免日常验证重复跑性能夹具；本地进程数据不代表真实容器或下游全量业务测试的耗时。

## test_guard_scripts.py 分组（单一信源）

> 顺序 = 脚本 `__main__` 的实跑顺序，与终端里的 `【…】` / `[NN] …` 标题逐条对应。
> **新增分组时同时改这里**——组数别再往其它文档里抄一份数字（`.aidp/scripts/README.md`
> 只放指针、不写死组数：抄一次就漂一次）。
>
> 机器回检 = `check_count_claims.py`（分组数字）+ `test_guard_scripts.py` 的「tests/README 分组表行数」用例（表格行数）。
> 「覆盖」列为 `—` 的分组，标题即覆盖面。
>
> **★ 重排本表不要手工做**：跑 `python3 .aidp/scripts/tests/sync_group_table.py`——它按实跑顺序重建，「覆盖」列按标题原样保留、新增分组填 `—`；`--check` 只比对不写。

| # | 分组标题 | 覆盖 |
|---|---------|------|
| 1 | `README 共享范围策略` | — |
| 2 | `通知承诺守卫：运行根占位符与否定句` | — |
| 3 | `README 三档判定 + 扫描降噪` | — |
| 4 | `级联落点门` | — |
| 5 | `口径残留门` | — |
| 6 | `提交分类 · 业务语义词不误伤源码` | — |
| 7 | `发布基线 · 密码明文门覆盖面` | — |
| 8 | `发布基线 · 引导层同形与跨 profile 补齐` | 环境段副本与源码同形 + 跨 profile 缺项 + 运行时部署文件不漏收（约定 37.4-2） |
| 9 | `报告 na 结果态` | — |
| 10 | `约定 22 义务登记门` | — |
| 11 | `tick TARGET_VERSION 按命令分流` | — |
| 12 | `片数声明：路径归属 + 标识符不误取` | — |
| 13 | `SKILL 引用：assets 覆盖 + 安装态文件豁免` | — |
| 14 | `跨文件双写：整行片段` | — |
| 15 | `骨架表编号识别的两种形态` | — |
| 16 | `handback-check 自动触发点` | — |
| 17 | `tests/README 分组表行数` | — |
| 18 | `DEPLOY_MODE 的 PRD 兜底按版本取` | — |
| 19 | `研发执行计划 → Sprint 集合口径` | — |
| 20 | `实现偏离设计门` | — |
| 21 | `版本标识 · 继承 pom 透明化` | — |
| 22 | `台账终态门 --ledger-closed` | — |
| 23 | `全量设计 section 级前滚` | — |
| 24 | `SKILL 引用漂移门` | — |
| 25 | `autopilot 主干：转义 / 零写入方键 / 游标越权 / 冻结解冻` | — |
| 26 | `发布基线：布局探测 / 列注释误报 / 占位豁免作废 / build 补登记 / 版本改名` | — |
| 27 | `无人值守死锁 + 守卫旁路` | — |
| 28 | `SKILL doc_split 的 _ 前缀例外` | — |
| 29 | `链式调用免检变体 / SKILL 入参 / 尾段选版 / Stop hook / 分组计数` | — |
| 30 | `版本层字段 / 占位符 / 回落 / 枚举拆分` | — |
| 31 | `check_convention_dup 形态探测 + 双写检出` | **形态 A 分离型 / 形态 B 内联型都要真检** + 双写检出 + 跳过分类 |
| 32 | `check_version_identifier 版本标识对齐` | 漂移检出 / 归一化 / deny-list 后缀匹配 / 占位豁免 / pom 继承 / 依赖目录不下钻 |
| 33 | `baseline_edit run-state 推进判定 + current-version 选版` | run-state 状态机推进条件 + 当前版本选取 |
| 34 | `baseline_edit builds[] 寻址 + 切碎版本号护栏` | builds 数组按 build 号寻址 + 版本号被切碎的护栏 |
| 35 | `阶段完成判据 + 收尾义务清算` | autopilot 阶段完成判据 + 收尾义务是否被清算 |
| 36 | `通知门：build 口径计数 + 脚本自算期望集` | 里程碑通知按 build 计数、期望集由脚本自算而非人填 |
| 37 | `release_baseline_check 双轨部署基线 13 项机器门` | 约定 37 全量/增量基线的 13 项确定性校验 |
| 38 | `autopilot_stuck_check 既不失败也不推进的兜底熔断` | 7×24 空转（不报错也不前进）的熔断判据 |
| 39 | `ceremony-gate 台账：无 build 的卡可登记且被 check 认账` | 无 build 的里程碑通知也能登记并被闸门认账 |
| 40 | `notify 标题固定前缀：项目中文名称恒在` | — |
| 41 | `check_changelog_fix_scope 修复段准入判据` | — |
| 42 | `autopilot_tick_flags TARGET_VERSION 空目标可表达` | — |
| 43 | `Phase 2 跨 Bash 准发布门` | — |
| 44 | `check_version_identifier 多层反应堆 parent 同步` | — |
| 45 | `check_md_anchors 站内锚点死链` | 站内 `#锚点` 死链检出 |
| 46 | `check_ghost_flags 幽灵旗标 / 零误报` | 检出幽灵旗标 + 四类零误报（owner 判定 / 续行继承 / CSS 变量 / 假定义防护） |
| 47 | `check_loop_examples /loop 示例必带 --unattended --no-loop` | 漏写检出 + 逐"出现"判 + 显式豁免（含 loop-example-ignore 仅豁免 --no-loop）|
| 48 | `check_line_refs 硬编码行号引用` | 四种行号写法 + `L1-L3` 层级不误报 + 目标可解析性分组 |
| 49 | `check_shard_counts 分片自称片数 / 范围记法` | 片数少算检出 + 范围记法漏 `b` 分片检出 + 三类零误报（显式列出 / 序数「第 N 片」/ 跨命令同名前缀） |
| 50 | `check_sprint_numbering Sprint 编号跨版本 + 划分粒度` | 跨版本重号检出 + 同功能前后端被拆成两 Sprint 检出 |
| 51 | `tick flags：单 flag 解析 + 变量供给链` | 单 `--flag` 不再 argparse exit 2 + 登记变量必须有 set/回落/推导来源 |
| 52 | `骨架表 ↔ flow 分片 Step 覆盖` | 分片定义了 Step 但骨架表漏登记（= 定义了永不执行） |
| 53 | `跨文件长片段双写` | ≥150 字符逐字重复跨文件出现（改一处漏一处的漂移源） |
| 54 | `单一信源指针 + 分片标题风格` | 「单一信源 = X」指针指不到 + 同层级标题编号风格混用 |
| 55 | `WebMCP 启用判定 + 三项守卫` | 未启用必须彻底静默 + 按需安装闭环 + 判据归属 SKILL 的防回归断言 |
| 56 | `check_ui_fidelity R2/R3/R10 + 零误报` | 约定 39 三条确定性检查各自命中 + **每条配零误报反例**（颜色随值绑定 / 兄弟节点插值不算本标签内容 / 循环翻页捞全量 / 普通分页列表非导出）+ 豁免不串号 + R10 Critical 退出码 |
| 57 | `tick 供给链：动态兜底 / 关断旗标 / 回落键写入者` | 动态兜底档必须接进 `cmd_shell`；`--no-notify` 必须有生效路径；回落键须有真实写入者 |
| 58 | `check_upstream_call_log C1/C2/I1/I2/I3 + 零误报` | — |
| 59 | `check_skill_ref_freshness SKILL 编号引用新鲜度 + 零误报` | — |
| 60 | `tick 命名空间按命令隔离（两条 7×24 链路互不清空）` | — |
| 61 | `check_flow_bash_syntax 三类真错 + 零误报` | — |
| 62 | `check_chain_unattended G-CHAIN-1 棘轮` | — |
| 63 | `code_inventory 跨版本增量缓存` | — |
| 64 | `requirement_query 历史需求读时查询` | — |
| 65 | `archive_old_artifacts 老版本留仓归档` | — |
| 66 | `handback-check 中途交还控制权机器门` | — |
| 67 | `收尾门 3m 缺陷复验闭环` | — |
| 68 | `WebMCP 入口探测：白名单优先 + 全局扫描兜底` | — |
| 69 | `entry_mode build 级优先（版本级槽位互相覆盖的回归）` | — |
| 70 | `口述档位门有生产方 + 口径反转清算门` | — |
| 71 | `设计目标棘轮 + 实现名词体检` | — |
| 72 | `约定22 绕过反向判据 + 约定24 提交前门禁` | — |
| 73 | `文档编号连续性 + 检查脚本阳性对照骨架` | — |
| 74 | `yield 守卫棘轮 + HAS_WAKE_SOURCE 供给链` | — |
| 75 | `memory 整段被吞：确定性落点` | — |
| 76 | `约定 22 绕过检出：补「只改代码、册子零动」这一最常见形态` | — |
| 77 | `隐形漂移：内容变了但 git status 报 clean` | — |
| 78 | `失败处置五步：记账 → 判阈 → 冻结四件套 → 发 #4 → 让位` | — |
| 79 | `Mock 守卫策略按标记分流（两类目的相反，混用即出事）` | — |
| 80 | `收敛进脚本后，各门仍看得见` | — |
| 81 | `失败处置：--freeze-now / --extra / 枚举不可解析` | — |
| 82 | `CommonMark 围栏判定 + env/.env 键集新鲜度` | — |
| 83 | `收尾门 3p/3q 缺陷分流 + 上轮 block 复评` | — |
| 84 | `classify_push 同 build 多次推送累积` | — |
| 85 | `口径残留门 短形式词表 + 判决行` | — |
| 86 | `exec 报告继承 cases[]/testSummary` | — |
| 87 | `notify --section-file + 渲染冒烟检测面` | — |
| 88 | `设计目标三条形式落地的收口` | — |
| 89 | `环境降级：无 bash / 无 Git / SKILL 安装位（阴性 + 阳性成对）` | — |
| 90 | `--reset-* 旗标执行器` | — |
| 91 | `冻结字段写入契约` | — |
| 92 | `SKILL 阻断名单棘轮` | — |
| 93 | `术语一致性 + 约定 30 正文体检` | — |
| 94 | `台账多态识别 + 格式漂移告警` | — |
| 95 | `收尾门 3n 测试结果挂靠用例基线` | — |
| 96 | `子 Agent 派单契约（cascade_mode / dev_scale）` | — |
| 97 | `业务计数声明表全库回扫` | — |
| 98 | `约定 30 棘轮键：内容指纹而非行号` | — |
| 99 | `check_version_audit_landed 审计落地门` | — |

> ⚠️ **本表不是"要靠人记得改"的清单，也不写死分组数**——真值只能现算（写死必漂）。
> 两种打印形态（早期 `【…】` 与后加的 `[NN] …`）都算分组，上表已含**全部**分组、按实跑顺序排列。
> - **重排** → `python3 .aidp/scripts/tests/sync_group_table.py`（`--check` 只比对）；
> - **行数回检** → `test_guard_scripts.py` 的「tests/README 分组表行数」用例（拿现算真值比对）；
> - **数字回检** → `check_count_claims.py` 的「测试分组」类（两种形态一并统计）。


> 关联：生成端 `.aidp/scripts/emit-report.py`（`validate_payload`/`enrich_build_no`）、渲染端 `.aidp/templates/reports/*/assets/app.js`、闸门 `.aidp/scripts/autopilot-ceremony-gate.py`（3g 内容契约 + 3h 渲染冒烟，复用 `.aidp/scripts/report_render_smoke.js`）。三处同一套契约，示例文件是单一信源。
