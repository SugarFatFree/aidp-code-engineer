# light 并行分派（可拆分的独立子任务）

> light 的 dev/repair 在已有 execution_context 下，先做并行判定，再实现。派发是已授权动作的执行方式，授权/预算以 `light-context.md`「执行围栏、预算与失败」与 AIDP-AGENTS.md 约定 36 为准。本片说明判定、受限子 context 与合并验证。

## 固定前置：输出决定和理由

入口绑定后、任何实现之前，列出候选子任务的实际写集及读/改规模，运行 `dispatch_plan.py`，向用户说明 `decision` 与 `reasons`；有冲突时同时说明 `conflicts`。单个任务也做判定，不把并行留到实现之后考虑。

满足全部 → 默认并行派子 Agent（不必再问用户）：

1. 可拆成 ≥2 个互不相交写集；相同路径、目录与其子路径都算相交。`pkg`、`pkg/`、`pkg/**` 均保守视为目录范围，不把不存在的目录当作可安全并行的独立文件；
2. 每个子任务各读 ≥3 个文件或改 ≥2 个文件。

写集相交的任务等并行批完成后由主 Agent 串行做；不达阈值的小改动由主 Agent 直接做，不为凑并行拆分。共享业务状态（族册、activeContext、总报告、编号）只由主流程串行写。预算不足或宿主不支持并发时说明理由并串行执行，不补授权。

## 先判定，再由主流程冻结子集并出 prompt

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?父路径}"
BUDGET_JSON="${BUDGET_JSON:?父剩余预算摘要}"
python3 {{AIDP_HOME}}/scripts/dispatch_plan.py --root . \
  --task "a=src/a.py,tests/test_a.py" --task "b=src/b.py,tests/test_b.py" \
  --reads a=3 --reads b=4
```

也可使用 `--tasks-json '[{"id":"a","writes":["src/a.py","tests/test_a.py"],"reads":3,"summary":"实现 A"}]'` 或 `@文件`。退出码 0=已判定，2=输入错误。`decision=serial` 时按理由直接串行执行；`decision=parallel` 时只为 `parallel_groups[0]` 中的任务执行以下步骤。

主流程先以父 context 调用 `execution_policy.py require-delegable --action implement`（同时传 `--root . --execution-context "$EXECUTION_CONTEXT"`），再创建受限子 context：

```bash
python3 {{AIDP_HOME}}/scripts/entry_context.py fork --root . \
  --execution-context "$EXECUTION_CONTEXT" --child-key a \
  --write-set src/a.py tests/test_a.py --json
python3 {{AIDP_HOME}}/scripts/entry_context.py fork --root . \
  --execution-context "$EXECUTION_CONTEXT" --child-key b \
  --write-set src/b.py tests/test_b.py --json
# 分别保存两次返回的 execution_context 为 CHILD_A、CHILD_B。
CHILD_A="${CHILD_A:?a 返回的 execution_context}"
CHILD_B="${CHILD_B:?b 返回的 execution_context}"
python3 {{AIDP_HOME}}/scripts/dispatch_plan.py --root . \
  --task "a=src/a.py,tests/test_a.py" --task "b=src/b.py,tests/test_b.py" \
  --reads a=3 --reads b=4 --emit-prompts \
  --execution-context "$EXECUTION_CONTEXT" --action implement --budget "$BUDGET_JSON" \
  --child-context "a=$CHILD_A" --child-context "b=$CHILD_B"
```

`child-key` 与任务 ID 对应。子写集必须是父当前写集子集；默认动作只取父已有 `implement/static/related-test` 的交集，也可用 `--allow-action` 进一步收窄，不增加 grant。子任务保留父原始基线和父 revision，共用根预算，context 与验证状态位于各自独立目录。已用 child-key 幂等复用，不重置预算或起点。父 revision 变化后旧子 context 失效，主流程停止旧派发、重新判定后使用新 child-key；不得自动刷新旧子任务权限。正式 `fork --sprint` 保持原协议。

脚本会实际读取父子 context，核验父身份、当前 revision、子任务 ID、动作与写集；仅提供路径文本、复用父路径或拿宽子写集冒充窄写集都会拒绝。

派发前对每个子 Agent `acquire-slot --kind agent`（沿用父 context；agents 是并发硬限，满额排队），结束后 `release-slot`。将同批任务在同一消息内并发派发，prompt 使用 `prompts[].prompt`。串行项留待并行批全部结束后处理。

## 子 Agent 执行边界

子 Agent 显式设置 `AIDP_EXECUTION_CONTEXT` 为本子 context，所有验证命令也传该路径；不得使用父宽 context 配窄 `--write-set` 选测。不得新建根身份、追加 grant、revise、再派发或修改写集外文件；发现范围不足交回主流程。

每个子任务按「实现 → 静态 → 选测 → 测试」执行：静态用子 context；相关测试已授权时运行 `light_task.py select` 再 `run`，使用子目录内 `unit-scope.json` 与状态文件。未授权相关测试则回报未执行。不得跑全量、目录级测试，不写父目录中的 scope/状态/报告。子任务只回传改动清单、静态结果、子 scope/运行证据路径及未解决问题，保留分片文件。

## 测试运行器并发

相关测试默认串行。确认测试隔离后，runner 可声明 `parallel:{enabled:true,workers:1,group:"共享资源名"}`；省略或 `enabled:false` 为串行屏障，同 `group` 在根任务槽位池互斥，父子上下文及多个 `run_scope` 也不能同时占用该资源；CLI 手动取槽可用 `acquire-slot --group 共享资源名`。

已知 runner 必须在冻结 argv 中显式限制内部 worker：pytest `-n0`（须已安装 xdist）、Jest `--runInBand`、Vitest `--maxWorkers=1 --minWorkers=1 --no-file-parallelism`、Maven `-T1 -DforkCount=0 -Dparallel=none -DthreadCount=1`；拒绝 auto、百分比、CPU 倍数等不定上限。这些参数须与项目实际版本匹配，不自动安装工具。Python 脚本/unittest 的 `workers:1` 是项目对内部无额外 worker 的声明，脚本或配置自行启动子进程不能由静态 argv 校验证明，须先确认真实工具行为。

批次在选测阶段由 runner 的 `batch_size` 或 `group_by:"directory"` 冻结，不在执行阶段改 argv。`light_task.py run/all --max-parallel N` 或 `light-context.md` 测试围栏的 `TEST_MAX_PARALLEL=N` 启用外层并发，仍受父子任务共享根 `processes` 槽位约束。每项保留独立账本和验证预留，失败、超时、中断均结算；仅主流程汇总一次并验证完整 scope，不因完成顺序改变结论。Python 槽位以本机持有 PID 存活和启动身份保护长任务；CLI 无持有 PID 的槽位仅接受正有限租约，调用方须在任务结束时释放。

## 主流程独占合并验证与汇总

所有子任务和串行项完成后，主流程核对合并改动及接口联动，使用父 context 对总写集重新按「静态 → 选测 → 测试」完成合并验证，独占最终总 scope 和汇总。子分片通过不等于合并通过；依据真实输入、环境、范围身份复用符合条件的证据，不冒用子结果。父 scope 不覆盖子 scope，子运行证据及状态分片全部保留。合并验证出现真实失败时按失败项修复复验，同根因同输入不重试，不扩大为全量。
