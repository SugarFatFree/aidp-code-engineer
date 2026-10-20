# 上游剩余能力落地记录

**目标**：完成已审阅增量中的阶段级联、按实际测试意图生成用例、通用工具接线和测试链路停滞熔断。

**实现边界**：契约真源仍在 `.aidp/`，bundle 由脚本生成。只运行与变更相关的测试；本轮不执行全量 `run.sh`。

## 验收矩阵

- [x] 提交门保留台账事实、结构/清理/绕过检查，不因日期积压自动派发级联。
- [x] `/version` 规划期、发布期、autopilot 阶段入口负责实际收口；`--cascade-now` 保留显式即时处理。
- [x] autopilot 按开发/测试阶段选择族；build 级标志实际参与派单过滤，终态/落点门用 `--family` 限定范围。
- [x] 批次保留 Step 5.6 的真实机器门，无 Git 时不执行 Git 落点检查。
- [x] `/sprint-dev` 通过 `--prepare` 根据外层测试意图决定生成或延期；`batch/full` 透传已安排实测的生成义务。
- [x] 延期同时写 baseline 和用例族台账；误删台账仍由 `deferred_sprints[]` 检出。
- [x] 显式测试/用例生成请求不能被开发期 `aiauto_test_required=false` 取消。
- [x] 正式用例生成且 QR 通过、对应台账已清理后才逐 Sprint `--complete`，再复跑测试前置门。
- [x] `check_scale_budget.py` 使用整版 `req_scale` 对账整版产出；未知事实不按0降档，零采集量不报通过。
- [x] `preflight_cache.py` 按同次调用身份和输入/命令指纹复用成功探针；命中后保留原 stdout，来源写 stderr。
- [x] `PREFLIGHT_RUN_ID` 每次独立 tick 自动更新，同步委派可以透传；动态通知/脏树总检实时执行。
- [x] `batch_probe.py` 验证基线绿、阳性真实失败、逐条可辨认、按字节还原后复跑绿；不把超时或共享失败码当全部命中。
- [x] 批量探针在 `rules/code.md` 有实际入口；既有 `selfcheck.py` 的隔离探针机制保留，不迁移为另一套实现。
- [x] `shard_gate_digest.py` 在 autopilot 有可选定位入口，支持运行路径 token；摘要不授权跳过硬门。
- [x] 测试 Phase 1/2/3 入口和出口通过 `aiauto_phase_entry.py` 维护独立 `aiauto_run_state`。
- [x] 先核验未完成旧阶段，再更新状态；同 tick 不重复计数，真实终态任务推进才重置窗口。
- [x] `--complete` 只在阶段证据落盘后使用；状态缺失、越权推进、冻结写盘失败均非零返回。
- [x] stuck 双阈值统一冻结并记录通知结果；人工解冻重置测试停滞窗口，避免立即重冻。
- [x] 新工具登记 README、测试入口和自检覆盖；模板与脚手架用镜像同步。

## 相关验证入口

```bash
python3 .aidp/scripts/tests/test_remaining_tools.py
python3 .aidp/scripts/tests/test_preflight_cache.py
python3 .aidp/scripts/tests/test_batch_probe.py
python3 .aidp/scripts/tests/test_unattended_recovery.py
python3 .aidp/scripts/tests/test_commit_gate.py
python3 .aidp/scripts/tests/test_command_skill_contracts.py
python3 .aidp/scripts/tests/test_guard_scripts.py
python3 .aidp/scripts/selfcheck.py --only check_scale_budget.py --json
python3 .aidp/scripts/selfcheck.py --only check_chain_unattended.py --json
python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check
python3 skills/aidp-code-engineer/scripts/verify.py . --template --read-only
```

流程契约只陈述最终行为；生成物不手工修改。
