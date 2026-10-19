# sprint-autopilot · Phase 3 详情分片 [4b/14]（3.1.6 约定 22 阶段级联收口）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的 **阶段级联 片**。
> - **本片覆盖**：3.1.6（约定 22 攒批级联的**阶段收口** —— autopilot 阶段入口）
> - **适用条件**：build 已铸（3.1.5 完成）。本片**不**适用于 `ENTRY_MODE=test-only` 且带 `--skip-aiauto-test` 的轮次（两族集合皆空 → 整片跳过、无需 Read）
> - **同 Phase 其它分片**：`phase-3-1.md` … `phase-3-9b.md`（清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：约定 22 的规则本体（条目格式 / 合并同类项 / 失效消解 / 落盘形态 / 清理规则）
> **单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`**。本片只定「本轮收哪几族、什么时候收、怎么派」。
> **进入本步第一动作 = Read 那份详规。**
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-4b.md`。

---

### 3.1.6 约定 22 阶段级联收口（autopilot 阶段入口；**必须先于 3.2 与任何浏览器实测**）

`/sprint-autopilot` 是约定 22 的**三个收口触发入口之一**（另两个是 `/version` 规划期与发布期）。
**收哪几族跟着本轮实跑的阶段走** —— 判据是「哪个阶段要照着这一族的主文档干活」：

| 收口点 | 族 | 本轮是否收（判据）|
| :-: | :- | :- |
| **5** | `需求` `设计` `计划` | `ENTRY_MODE != test-only` —— 开发阶段要照着**设计与计划**写码 |
| **6** | `用例` | `SKIP_AIAUTO_TEST != 1` —— 实测要照着**用例册**跑 |

> ⛔ **用例族的判据刻意取 `SKIP_AIAUTO_TEST != 1`，【不是】`WILL_BROWSER_TEST`**：
> 后者在 `phase-3-8.md` 才算出（还要掺 `DEPLOY_MODE` / `SKIP_DEPLOY`），在这里复算就是**第二份实现**。
> 而两种误判的代价**完全不对称**：多收 = 多级联一批用例（有成本、不出错）；
> 漏收 = 实测跑的是**不含本批新增的用例集**，且全绿收尾、无任何信号。故取**宁可多收**的那一侧。
>
> ⛔ **为什么两个收口点合在同一个落点、且落在 3.2 之前**：浏览器实测的委派点是**分散**的
> ——test-only 在 3.0 内委派、交互单次在 3.4 的 P0-4 自跑、而 `HAS_WAKE_SOURCE=1` 时
> 实测由**第二条 `/loop` 异步承担、autopilot 根本管不到**。把收口挂在"委派前"就必然散成三处、
> 且第三处压根没有落点。挂在 3.1.6 则**早于全部三条路径**，一处即够。
>
> ⛔ **`test-only` 轮的时序必须盯死**：该轮不进 3.2，**委派紧跟在 3.1.5/3.1.6 之后**（`phase-3-2.md` 的 test-only 流程：R-1 铸 build → R-3 骨架 → 委派前硬门 → invoke）。**本步必须跑在那次 invoke 之前** —— 顺序颠倒的失败形态是「实测跑的是旧用例集」，且该轮全程零告警、收尾门全绿。

**1. 跳过判定（⛔ 先判，两族集合皆空则整步跳过、不派 Agent）**

> ⛔ **下面每个 ```bash 围栏都是一次独立 Bash 调用 —— 围栏之间、分片之间 shell 变量都不持久。**
> 故每个围栏**自己 `eval` 一次 tick flags、自己赋 `BE`/`V`/`B`**，⛔ 不沿用上一个围栏的变量
> （沿用的失败形态是**取空**：判据恒真或恒假，而终端上与正常执行完全同形）。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"   # ENTRY_MODE / SKIP_AIAUTO_TEST / TARGET_VERSION / BUILD
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
V="$TARGET_VERSION"; B="$BUILD"      # 3.1.5 已铸/复用
FAMS=""
[ "${ENTRY_MODE:-full}" != "test-only" ] && FAMS="需求,设计,计划"
if [ "${SKIP_AIAUTO_TEST:-0}" != 1 ]; then
  FAMS="${FAMS:+$FAMS,}用例"
fi
# ★ 幂等：标志落【build 级】。autopilot 默认逐 tick 单 Sprint，Phase 3.1.x 每个 tick 都会进；
#   不按 build 幂等，本步就退化成每 10 分钟一次的级联 —— 比挂在提交节奏上还频繁。
#   ⛔ 别落版本级：那会让同一版的后续 build 永远收不了口。
DEV_DONE=$($BE --version "$V" --build "$B" get cascade_dev_closed_at --default "")
CASE_DONE=$($BE --version "$V" --build "$B" get cascade_case_closed_at --default "")
```

- `FAMS` 为空（test-only 且 `--skip-aiauto-test`）→ 打印 `⏭️ 本轮无需级联收口（无阶段消费任何族）` 并进 3.2/3.3。
- 对应标志**已有值** → 该组族本 build 已收过，从 `FAMS` 中剔除；剔空则整步跳过。
- 四族增量册**全部不存在或无待级联条目**（`commit_gate.py` 的 `pending_cascade`，⛔ 不自拼路径）
  → 打印 `⏭️ 四族增量册无待级联条目` + **照常落两个标志**（"本 build 这一阶段已尝试过收口"），进下一步。

**2. 派独立子 Agent 执行收口（约定 36 授权；无人值守同样派，⛔ 不弹窗、不等人）**

简报必须含四项，缺任一即派单不合规：

1. **第一动作 = `git pull --rebase` 后重读四族增量册**。⛔ 不得消费主 Agent 传来的 `pending_cascade`
   快照（增量册是入库共享文件，别人可能刚收口过）；重读后已无待级联条目 → **直接退出、不做事、不报错**。
2. **本轮族白名单 = `$FAMS`**。⛔ **不在白名单内的族一个字都不许动** —— 这是"按阶段裁剪"的全部落点：
   test-only 轮去级联详细设计，是把四族里最贵的一族压进一个不碰代码的 tick。
3. **逐条结合代码现状核实**（被后续改动推翻的条目直接作废、不产文档）→ 按 `C-NNN` 跨族合并同类项
   → 四级级联**一律传 `--ledger-cascade`**（就地改该族内容主文档正文，⛔ 不新建 `NN_<业务主题>.md` 分册）
   → 成功的条目即删、某族清空即删该族册子。细则（含**增量范围读代码**、按合并后总量重判档位）
   以 `{{AIDP_HOME}}/reference/开发期族增量.md`「收口执行要点」为准。
4. **提交归属**：`ENTRY_MODE != test-only` 时产物**留在工作区**，由 Phase 3.2 的 Sprint 提交一并带走；
   **test-only 轮本轮没有任何后续提交点** → 子 Agent **自行 `commit` + `push` 单独成笔**
   （⛔ 否则收口产物停在工作区，下一 tick 的 `git status` 把它当成"未提交的脏改动"）。

**3. 终态门 + 落点门（确定性，⛔ 不通过不得进 3.2 / 不得委派实测）**

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"; V="$TARGET_VERSION"
python3 {{AIDP_HOME}}/scripts/check_cascade_landing.py --ledger-closed --version "$V"   # 终态门（档②）
python3 {{AIDP_HOME}}/scripts/check_cascade_landing.py --worktree   --version "$V"      # 落点门
```

- **终态门（档②）**：断言**文件存在 ⟺ 确有未决条目**。⚠️ **本步只收白名单内的族**，
  故门报"白名单外的族仍有未决条目"是**正常**的，不算失败；真失败 = **白名单内**某族空着却没删、
  或整档打了 `<!-- LEDGER-ARCHIVED -->`（标记不替代删除）、或有实质内容却一条都解析不出（fail-closed）。
- **落点门**：四族目录的改动里不得出现中转册或**本批次新建的** `NN_<业务主题>.md`。
- 两个门**正交**（一个看"册子收没收"、一个看"改动落在哪"），缺一即留缺口。
- 失败条目**留在该族册子**（版本开发中途，留到下个收口点是正常节奏）+ WARN；
  ⛔ **但幂等标志照常落** —— 标志的语义是"本 build 这一阶段已尝试过收口"、不是"已收干净"；
  不落会让同一 build 的每个 tick 都重跑一遍注定失败的级联。

**4. 写盘 + 推进**

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
V="$TARGET_VERSION"; B="$BUILD"; TS=$(date -Iseconds)
# ★ 标志判据**直接取原始 flag**（= 上文那两条判据的同一个权威源），⛔ 不沿用 FAMS、
#   也不在这里把族集合算法抄第二遍 —— 抄一遍就是两份实现，漂移时两处各说一套。
[ "${ENTRY_MODE:-full}" != "test-only" ] && $BE --version "$V" --build "$B" set cascade_dev_closed_at  "$TS"
[ "${SKIP_AIAUTO_TEST:-0}" != 1 ]       && $BE --version "$V" --build "$B" set cascade_case_closed_at "$TS"
# ★ 下一步从 3.1.5 落盘的 run_state **读回**（⛔ 不跨分片沿用 shell 变量：phase-3-4.md 里的
#   NEXT_PHASE / NEXT_SPRINT 到这里必然取空，会把 next_phase 写成空串、断点续跑形同虚设）
NP=$($BE --version "$V" get run_state.next_phase  --default "3.2-dev")
NS=$($BE --version "$V" get run_state.next_sprint --default "done")
$BE --version "$V" run-state "3.1.6-cascade" "$NP" "$NS" \
  --summary "Phase 3.1.6 完成：阶段级联收口" --pending "" >/dev/null \
  || echo "⚠️ run_state 写盘失败（见上行 stderr）—— stuck 熔断将失去计数来源，须排查"
```

**打印**：`📋 阶段级联收口（族=<本轮白名单>）：处理 N 条（成功 M / 失效 K / 失败 J）→ 已就地写回各族内容主文档；册子：…`
