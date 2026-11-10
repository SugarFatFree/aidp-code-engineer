# /version · 规划生成恢复 — 分片 3b/10

> 本片是 `planning-3.md` Step 2.4.3.5 的持久生成节点协议；首次派单与重试前必须 Read。

<!-- BODY-BELOW -->
生成前分别调用（每个节点的 `--input` / `--output` 可重复；下列文件名按实际分册展开，不把索引当内容）：

```bash
python3 {{AIDP_HOME}}/scripts/planning_state.py --root . --version {version} start plan --input docs/requirements/{version}/研发需求 --input docs/design/detail/{version} --input memory/{version}/.planning-plan-params.json --output docs/plans/{version}/01_研发执行计划.md
python3 {{AIDP_HOME}}/scripts/planning_state.py --root . --version {version} start case --input docs/requirements/{version}/研发需求 --input docs/design/detail/{version} --input memory/{version}/.planning-case-params.json --output docs/testing/{version}/研发自测/02_全量自测用例.md
```

`.planning-plan-params.json` / `.planning-case-params.json` 是**本次实际参数的持久记录**（从已有 `.planning-skill-params.json` 各自对象提取，含档位、qr_level、selftest_args、依赖 SKILL/checklist 内容 hash；不是新增项目配置）；必须在 start 前写好，仅值变化时更新。各节点追加真实依赖的 PRD/原型/代码事实/对账表 `--input`；目录指纹包括成员增删。case 生成不依赖计划，不能把 plan 目录或 plan 状态加入它的输入。所有生成输出必须逐文件列入 `--output`，包含实际分册；索引和环境配置不属于并行 case 生成输出，按 repair 自身范围维护。未知分册先按计划确定输出清单，不能只登记主文档漏掉分册。

`action=reused` 就复用该支，`redone` 才派；每支完成立刻保存真实返回 JSON（包含 `status=pass|fail` 与 `exit_code`，不可用写 fail），分别执行：

```bash
python3 {{AIDP_HOME}}/scripts/planning_state.py --root . --version {version} finish plan --result memory/{version}/.planning-plan-result.json
python3 {{AIDP_HOME}}/scripts/planning_state.py --root . --version {version} finish case --result memory/{version}/.planning-case-result.json
```

只执行已返回那支对应的 finish，不等待另一支成功才记账。一支失败另一支成功时，保留成功产物及状态；重试 start 自动返回成功支 `reused`。`--force-replan` 首次派单给两个 start 都加 `--force`，该轮失败恢复时不再加，原有发布保护与已启动 Sprint 保护照旧。repair 不重跑未失效生成节点；补充模式顺序保持 requirements → design → plan → selftest，不启用本并行协议。


五环节 `plan/case/map/ref/verify` 各有真实持久结果与输入指纹。后三步内部调用 `{{AIDP_HOME}}/skills/dev-execution-planner/scripts/export_plan_refs.py`、`{{AIDP_HOME}}/skills/dev-manual-testcase/scripts/resolve_plan_refs.py`、`{{AIDP_HOME}}/skills/dev-manual-testcase/scripts/check_suite_upstream.py`；明细落 `memory/{version}/.planning-results/{map,ref,verify}.json`，状态统一存 `.planning-state.json`。`reused/redone/missing` 明确报告。计划变化只失效 plan→map→ref→verify；case 输入变化只失效 case→ref→verify；共享输入变化失效相关两支。回填从保存的原始 case 快照在临时目录计算，成功才写回，重填新计划链接无需重新生成用例。失败不清成功产物；export skipped 不消费旧 map。

生成阶段对全部必要 inputs 取内容指纹；索引只剥离原协议的 QR 控制两行及其插入空行（围栏示例不剥离），**索引正文/链接/顺序仍取 hash**。这样结清 handoff 不自我失效，真实索引改动仍使依赖节点失效；编号、引用另走每轮全局机器核验。PRD 对账表按确定性内容取 hash，同输入重导出不产生额外失效。串行回退时 case 必须在 plan 完成后重新 start，并把实际计划文件加入其 inputs；此时已不使用 deferred 模式，不能套并行 case 无计划依赖的假设。
