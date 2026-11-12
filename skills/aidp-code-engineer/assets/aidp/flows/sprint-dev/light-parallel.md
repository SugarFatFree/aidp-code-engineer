# light 并行分派（可拆分的独立子任务）

> 仅用于 light 的 dev/repair 在**已有 execution_context** 下，任务可拆成互不相交写集时。派发是已授权动作的执行方式，授权/预算/prompt 基本项以 `light-context.md`「执行围栏、预算与失败」与 AIDP-AGENTS.md 约定 36 为准，本片只补「何时并行、怎么出 prompt、谁来测」。

## 并行判定

满足全部 → **默认并行派子 Agent**（不必再问用户）：

1. 可拆成 ≥2 个**互不相交**的写集（文件相同、或一方为另一方目录前缀即相交）；
2. 每个子任务各自读 ≥3 个文件**或**改 ≥2 个文件。

写集有交集的子任务串行（并行批完成后由主 Agent 依次做）；不达阈值的小改动主 Agent 直接做，不为凑并行而拆。共享状态（ledger、activeContext、报告、编号）只由主流程串行写。

## 用 dispatch_plan.py 判定并出 prompt

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?父路径}"
BUDGET_JSON="${BUDGET_JSON:?父剩余预算摘要}"
python3 {{AIDP_HOME}}/scripts/dispatch_plan.py \
  --task "a=src/a.py,tests/test_a.py" --task "b=src/b.py,tests/test_b.py" \
  --reads a=3 --reads b=4 \
  --emit-prompts --execution-context "$EXECUTION_CONTEXT" --action implement --budget "$BUDGET_JSON"
```

也可 `--tasks-json '[{"id":"a","writes":[...],"reads":3,"summary":"..."}]'`（或 `@文件`）。退出码 0=已判定，2=输入错误。消费输出：

- `decision=parallel` → 把 `parallel_groups[0]` 内各任务**同一消息内**并发派子 Agent，prompt 取 `prompts[].prompt`；`serial` 中的任务等并行批结束后主 Agent 自己做；
- `decision=serial` → 不派发，按 `reasons`/`conflicts`（冲突文件与任务）串行执行；
- 派发前按 `light-context.md` 围栏对 `agents` 资源预留并先 `execution_policy.py require-delegable --action "$ACTION"`（只判有资格委派；真正执行仍由各动作的 require-action 把关）。

## 子 Agent prompt 必带项（脚本模板已含）

父 execution_context 路径、action、剩余 budget、本子任务写集、「只跑本写集对应的相关测试」。子 Agent **只在父授权动作内工作，不得传入/追加 grant、不得 revise、不得再派发**；不新建任务身份、不改写集外文件、不改共享状态。

## 完成后统一收口

子 Agent 只回传改动清单与静态结果，不各自重复跑同一批测试。全部返回后，主 Agent 对**合并后的总写集**统一执行一次相关测试（`light-context.md` 的 test 能力，范围由 `select_related_tests.py` 推导），再汇总；真实失败按失败修复复验流程处理，同根因同输入不重试。
