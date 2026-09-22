# .aidp/scripts/tests/ — 确定性脚本回归单测

防「产出即错、直到人肉发现才知道」——把发现时机前移到脚本产出时。覆盖四条链路：**AI 报告**（契约 + 渲染）、**提交前门禁与推送分类**、**里程碑通知 / 多 Agent 装配**、**确定性护栏**。

> ★ **新增测试文件必须【同时】登记进 `run.sh` 与下方文件表**：漏登 `run.sh` = 该套件永远绿不了也红不了（`test_guard_scripts.py` 的「run.sh 收录全部 test_* 文件」用例会机器回检）；漏登文件表 = 维护者按表核对时会以为它不存在，改动相关脚本时不会想到要跑它。

一键跑全（仓库根）：`bash .aidp/scripts/tests/run.sh` —— 末尾汇总「套件数 · 断言 passed / failed / skipped」，任一套件失败即非零退出。

| 文件 | 覆盖 | 运行 | 依赖 |
|------|------|------|------|
| `test_report_schema.py` | `emit-report.py` 数据契约校验（`validate_payload`）+ `buildNo` 派生 + **示例文件自校验（示例即契约、永不分叉）** + 改坏必红 | `python3 .aidp/scripts/tests/test_report_schema.py` | Python 标准库；③④ 加载 JS 示例需 `node`（缺则跳过、非失败） |
| `test_report_render.js` | 渲染口径（`pct` 经渲染路径：0.84→84%、100.0→100% 不出 10000%）+ 坏数据健壮性（risks 分组对象不白屏 / cases 别名无 undefined / 无 buildNo 不 `#undefined`） | `node .aidp/scripts/tests/test_report_render.js` | `node` |
| `test_commit_gate.py` | `commit_gate.py`（约定 24）：模板项目判定 / 业务代码与纯脚手架判定 / 约定 22 台账积压（stale、多态识别、已级联未清理、归档标记、格式漂移）/ `suspected_cascade_bypass` / 约定 41 `offchain` 档位 / `pending_cicd` 推送欠账 / CLI 退出码 0·3 与 `--quiet` 告警恒打印 / `commit_gate.enabled` 总开关；另含 `classify_commit_change` · `classify_push` 分类（按 commit 键控记录、部署终态） | `python3 .aidp/scripts/tests/test_commit_gate.py` | Python 标准库 + `git` |
| `test_notify.py` | `notify.py`（约定 32）：feishu / dingtalk / wecom / lark-cli / command 渠道渲染与发送、飞书 · 钉钉签名、`--auto` 渠道回落、`--sender`、`--print-only` / `--json` 结构、退出码 0/1/2/3、项目名解析与 `--check-name`、发送成功才登记台账 | `python3 .aidp/scripts/tests/test_notify.py` | Python 标准库（本地 127.0.0.1 HTTP 桩 + 假 lark-cli，不联网） |
| `cicd_watch.py --selftest`（脚本自带，非本目录文件） | CICD 多提供方监听（`cicd_watch.py` + `cicd_providers.py`）的离线自测，由 `run.sh` 一并调起 | `python3 .aidp/scripts/cicd_watch.py --selftest` | Python 标准库 |
| `test_agent_sync.py` | `agent_env.py`（detect / memory-file / `--self-check`）+ `agent_sync.py`（临时 git 仓库装配 Claude Code / Codex / DeepSeek Harness、记忆文件搬迁、幂等、`--check` 漂移、copy 模式、清理与合并、`--self-check`） | `python3 .aidp/scripts/tests/test_agent_sync.py` | Python 标准库 + `git` |
| `test_guard_scripts.py` | 确定性护栏全套（分组清单见下方「test_guard_scripts.py 分组」——**该表是唯一信源**，其它文档只放指针、不复制清单也不复制组数） | `python3 .aidp/scripts/tests/test_guard_scripts.py` | Python 标准库；依赖脚手架 skill 内部实现的断言默认 SKIP，设 `AIDP_TEST_SKILL_INTERNALS=1` 开启 |
| `test_baseline_archive.py` | baseline 归档/迁移链路（`baseline_archive` 归档范围 + 墓碑判据 + `baseline_edit get` 归档回落 + `autopilot_decisions` 双信源） | `python3 .aidp/scripts/tests/test_baseline_archive.py` | Python 标准库 |
| `test_field_level_and_evidence.py` | 写读错层（`decidable_skips` 版本级/build 级）+ memory 保护面 + flock 锁路径单一信源 + 运行时产物落点收编（`aidp_paths` / `aidp_config` / `commit_gate` 同口径） | `python3 .aidp/scripts/tests/test_field_level_and_evidence.py` | Python 标准库 |
| `test_offchain_scope.py` | 约定 41 链外档位（`commit_gate.py::offchain_budget` 的 XS/S/M/L 分档与动作预算）+ 链外推送欠账 + 约定 17 反向门 | `python3 .aidp/scripts/tests/test_offchain_scope.py` | Python 标准库 |
| `test_release_gates.py` | 发布期硬门（`check_release_residual_gate.py` 等的双侧对照 + 各脚本 `--self-check`） | `python3 .aidp/scripts/tests/test_release_gates.py` | Python 标准库 |
| `test_report_immutability.py` | 报告不可变门（已 finalize build 的篡改检出 + skeleton 期前移）+ driver 如实性窗口 + `renderMode` 取证来源 | `python3 .aidp/scripts/tests/test_report_immutability.py` | Python 标准库 |
| `test_unattended_recovery.py` | 无人值守失败处置与自动恢复：`autopilot_fail_handle.py --command` 按链路取唤醒源、同 reason 冻结幂等、未达阈不发通知、冻结写本地告警台账 `memory/.aidp/alerts.jsonl`；`autopilot_unfreeze.py` 环境类复探（退避 + 上限）/ `--clear` / `--manual` | `python3 .aidp/scripts/tests/test_unattended_recovery.py` | Python 标准库 |
| `test_aidp_scheduler.py` | `aidp_scheduler.py`（7×24 操作系统调度）：systemd / crontab / launchd / schtasks 渲染、周期解析、install / uninstall / status、心跳巡检告警、`agent_loop.sh --once` 参数补齐 | `python3 .aidp/scripts/tests/test_aidp_scheduler.py` | Python 标准库 |
| `test_agent_sync_router.py` | Codex / DeepSeek Harness 原生命令生成、Codex frontmatter 与 `$ARGUMENTS` 正文保真、命令/SKILL 重名保护、`--check` 漂移、gitignore 托管块去重 | `python3 .aidp/scripts/tests/test_agent_sync_router.py` | Python 标准库 + `git` |
| `test_runtime_and_vcs.py` | `.aidp` / `.claude/aidp` / `.agents/aidp` 运行根与项目根解析、环境覆盖路径 containment、`git|none` 能力检测、开发者身份四级回落、`unsupported: vcs-disabled` 结构 | `python3 .aidp/scripts/tests/test_runtime_and_vcs.py` | Python 标准库；Git 阳性用例用临时仓库（不可用则仅该用例跳过） |
| `test_runtime_paths.py` | 下发运行契约中的 `{{AIDP_HOME}}`、根 `.aidp/` 硬编码和渲染态未解析 token 守卫 | `python3 .aidp/scripts/tests/test_runtime_paths.py` | Python 标准库 |
| `test_command_skill_contracts.py` | 命令 ↔ SKILL 调用契约：脚手架调用形态、SQL 隔离门两轨布局、`code-verification-loop` 仅验收模式、`bugfix` 输入面、质量门委派接线、发布欠账唯一写入口、写前快照 | `python3 .aidp/scripts/tests/test_command_skill_contracts.py` | Python 标准库 + `git` |
| `test_doc_reference_guards.py` | 文档引用与开源卫生三道门：`check_code_symbol_refs.py`（`脚本::符号` 存在性）/ `check_cli_invocation.py`（子命令与 flag 归属）/ `check_private_markers.py`（内网地址 / 主机名 / MCP 服务名 / 下游项目名 / 示例子项目名 / 本地名单）双侧对照 + `--self-check` | `python3 .aidp/scripts/tests/test_doc_reference_guards.py` | Python 标准库 |
| **脚手架侧（不在本目录、由 `run.sh` 一并调起）** | `.aidp/skills/aidp-code-engineer/scripts/tests/` 下的 `test_mirror.py` / `test_scaffold_lib.py` / `test_runtime_layout.py` / `test_installed_init_docs.py` / `test_scaffold_modes.py` / `test_sync_memory_md.py` | 见 `run.sh`「脚手架 skill 侧」段 | Python 标准库 |
| `sync_group_table.py` | 维护工具：把 `test_guard_scripts.py` 的实跑分组同步进本 README 的分组表 | `python3 .aidp/scripts/tests/sync_group_table.py` | Python 标准库 |
| `fixtures/*.js` | AI 报告数据缺陷形态的回归样本（脱敏） | — | — |
| `run.sh` | 一次跑全部 | `bash .aidp/scripts/tests/run.sh` | 同上 |

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
| 7 | `发布基线 · 明文凭据门覆盖面` | — |
| 8 | `报告 na 结果态` | — |
| 9 | `约定 22 义务登记门` | — |
| 10 | `tick TARGET_VERSION 按命令分流` | — |
| 11 | `片数声明：路径归属 + 标识符不误取` | — |
| 12 | `SKILL 引用：assets 覆盖 + 安装态文件豁免` | — |
| 13 | `跨文件双写：整行片段` | — |
| 14 | `骨架表编号识别的两种形态` | — |
| 15 | `handback-check 自动触发点` | — |
| 16 | `tests/README 分组表行数` | — |
| 17 | `DEPLOY_MODE 的 PRD 兜底按版本取` | — |
| 18 | `研发执行计划 → Sprint 集合口径` | — |
| 19 | `实现偏离设计门` | — |
| 20 | `版本标识 · 继承 pom 透明化` | — |
| 21 | `台账终态门 --ledger-closed` | — |
| 22 | `全量设计 section 级前滚` | — |
| 23 | `SKILL 引用漂移门` | — |
| 24 | `autopilot 主干：转义 / 零写入方键 / 游标越权 / 冻结解冻` | — |
| 25 | `发布基线：布局探测 / 列注释误报 / 占位豁免 / build 补登记 / 版本改名` | — |
| 26 | `无人值守死锁 + 守卫旁路` | — |
| 27 | `SKILL doc_split 的 _ 前缀例外` | — |
| 28 | `链式调用免检变体 / SKILL 入参 / 尾段选版 / Stop hook / 分组计数` | — |
| 29 | `版本层字段 / 占位符 / 回落 / 枚举拆分` | — |
| 30 | `check_convention_dup 形态探测 + 双写检出` | **形态 A 分离型 / 形态 B 内联型都要真检** + 双写检出 + 跳过分类 |
| 31 | `check_version_identifier 版本标识对齐` | 漂移检出 / 归一化 / deny-list 后缀匹配 / 占位豁免 / pom 继承 / 依赖目录不下钻 |
| 32 | `baseline_edit run-state 推进判定 + current-version 选版` | run-state 状态机推进条件 + 当前版本选取 |
| 33 | `baseline_edit builds[] 寻址 + 切碎版本号护栏` | builds 数组按 build 号寻址 + 版本号被切碎的护栏 |
| 34 | `阶段完成判据 + 收尾义务清算` | autopilot 阶段完成判据 + 收尾义务是否被清算 |
| 35 | `通知门：build 口径计数 + 脚本自算期望集` | 里程碑通知按 build 计数、期望集由脚本自算而非人填 |
| 36 | `release_baseline_check 双轨部署基线 12 项机器门` | 约定 37 全量/增量基线的 12 项确定性校验 |
| 37 | `autopilot_stuck_check 既不失败也不推进的兜底熔断` | 7×24 空转（不报错也不前进）的熔断判据 |
| 38 | `ceremony-gate 台账：无 build 的卡可登记且被 check 认账` | 无 build 的里程碑通知也能登记并被闸门认账 |
| 39 | `notify 标题固定前缀：项目中文名称恒在` | — |
| 40 | `check_changelog_fix_scope 修复段准入判据` | — |
| 41 | `autopilot_tick_flags TARGET_VERSION 空目标可表达` | — |
| 42 | `Phase 2 跨 Bash 准发布门` | — |
| 43 | `check_version_identifier 多层反应堆 parent 同步` | — |
| 44 | `check_md_anchors 站内锚点死链` | 站内 `#锚点` 死链检出 |
| 45 | `check_ghost_flags 幽灵旗标 / 零误报` | 检出幽灵旗标 + 四类零误报（owner 判定 / 续行继承 / CSS 变量 / 假定义防护） |
| 46 | `check_loop_examples /loop 示例必带 --unattended` | 漏写检出 + 逐"出现"判 + 显式豁免 |
| 47 | `check_line_refs 硬编码行号引用` | 四种行号写法 + `L1-L3` 层级不误报 + 目标可解析性分组 |
| 48 | `check_shard_counts 分片自称片数 / 范围记法` | 片数少算检出 + 范围记法漏 `b` 分片检出 + 三类零误报（显式列出 / 序数「第 N 片」/ 跨命令同名前缀） |
| 49 | `check_sprint_numbering Sprint 编号跨版本 + 划分粒度` | 跨版本重号检出 + 同功能前后端被拆成两 Sprint 检出 |
| 50 | `tick flags：单 flag 解析 + 变量供给链` | 单 `--flag` 不再 argparse exit 2 + 登记变量必须有 set/回落/推导来源 |
| 51 | `骨架表 ↔ flow 分片 Step 覆盖` | 分片定义了 Step 但骨架表漏登记（= 定义了永不执行） |
| 52 | `跨文件长片段双写` | ≥150 字符逐字重复跨文件出现（改一处漏一处的漂移源） |
| 53 | `单一信源指针 + 分片标题风格` | 「单一信源 = X」指针指不到 + 同层级标题编号风格混用 |
| 54 | `WebMCP 启用判定 + 三项守卫` | 未启用必须彻底静默 + 按需安装闭环 + 判据归属 SKILL 的防回归断言 |
| 55 | `check_ui_fidelity R2/R3/R10 + 零误报` | 约定 39 三条确定性检查各自命中 + **每条配零误报反例**（颜色随值绑定 / 兄弟节点插值不算本标签内容 / 循环翻页捞全量 / 普通分页列表非导出）+ 豁免不串号 + R10 Critical 退出码 |
| 56 | `tick 供给链：动态兜底 / 关断旗标 / 回落键写入者` | 动态兜底档必须接进 `cmd_shell`；`--no-notify` 必须有生效路径；回落键须有真实写入者 |
| 57 | `check_upstream_call_log C1/C2/I1/I2/I3 + 零误报` | — |
| 58 | `check_skill_ref_freshness SKILL 编号引用新鲜度 + 零误报` | — |
| 59 | `tick 命名空间按命令隔离（两条 7×24 链路互不清空）` | — |
| 60 | `check_flow_bash_syntax 三类真错 + 零误报` | — |
| 61 | `check_chain_unattended G-CHAIN-1 棘轮` | — |
| 62 | `code_inventory 跨版本增量缓存` | — |
| 63 | `requirement_query 历史需求读时查询` | — |
| 64 | `archive_old_artifacts 老版本留仓归档` | — |
| 65 | `handback-check 中途交还控制权机器门` | — |
| 66 | `收尾门 3m 缺陷复验闭环` | — |
| 67 | `WebMCP 入口探测：白名单优先 + 全局扫描兜底` | — |
| 68 | `entry_mode build 级优先（版本级槽位互相覆盖的回归）` | — |
| 69 | `口述档位门有生产方 + 口径反转清算门` | — |
| 70 | `设计目标棘轮 + 实现名词体检` | — |
| 71 | `约定22 绕过反向判据 + 约定24 提交前门禁` | — |
| 72 | `文档编号连续性 + 检查脚本阳性对照骨架` | — |
| 73 | `yield 守卫棘轮 + HAS_WAKE_SOURCE 供给链` | — |
| 74 | `memory 整段被吞：确定性落点` | — |
| 75 | `约定 22 绕过检出：补「只改代码、册子零动」这一最常见形态` | — |
| 76 | `隐形漂移：内容变了但 git status 报 clean` | — |
| 77 | `失败处置五步：记账 → 判阈 → 冻结四件套 → 发 #4 → 让位` | — |
| 78 | `Mock 守卫策略按标记分流（两类目的相反，混用即出事）` | — |
| 79 | `收敛进脚本后，各门仍看得见` | — |
| 80 | `失败处置：--freeze-now / --extra / 枚举不可解析` | — |
| 81 | `CommonMark 围栏判定 + env/.env 键集新鲜度` | — |
| 82 | `收尾门 3p/3q 缺陷分流 + 上轮 block 复评` | — |
| 83 | `classify_push 同 build 多次推送累积` | — |
| 84 | `口径残留门 短形式词表 + 判决行` | — |
| 85 | `exec 报告继承 cases[]/testSummary` | — |
| 86 | `notify --section-file + 渲染冒烟检测面` | — |
| 87 | `设计目标三条形式落地的收口` | — |
| 88 | `--reset-* 旗标执行器` | — |
| 89 | `冻结字段写入契约` | — |
| 90 | `SKILL 阻断名单棘轮` | — |
| 91 | `术语一致性 + 约定 30 正文体检` | — |
| 92 | `台账多态识别 + 格式漂移告警` | — |
| 93 | `收尾门 3n 测试结果挂靠用例基线` | — |
| 94 | `子 Agent 派单契约（cascade_mode / dev_scale）` | — |
| 95 | `业务计数声明表全库回扫` | — |
| 96 | `约定 30 棘轮键：内容指纹而非行号` | — |

> ⚠️ **本表不是"要靠人记得改"的清单，也不写死分组数**——真值只能现算（写死必漂）。
> 两种打印形态（早期 `【…】` 与后加的 `[NN] …`）都算分组，上表已含**全部**分组、按实跑顺序排列。
> - **重排** → `python3 .aidp/scripts/tests/sync_group_table.py`（`--check` 只比对）；
> - **行数回检** → `test_guard_scripts.py` 的「tests/README 分组表行数」用例（拿现算真值比对）；
> - **数字回检** → `check_count_claims.py` 的「测试分组」类（两种形态一并统计）。


> 关联：生成端 `.aidp/scripts/emit-report.py`（`validate_payload`/`enrich_build_no`）、渲染端 `.aidp/templates/reports/*/assets/app.js`、闸门 `.aidp/scripts/autopilot-ceremony-gate.py`（3g 内容契约 + 3h 渲染冒烟，复用 `.aidp/scripts/report_render_smoke.js`）。三处同一套契约，示例文件是单一信源。
