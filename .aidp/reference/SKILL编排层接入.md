# SKILL 编排层接入（版本规划四个子命令的共用契约）

> **谁读**：`/sprint-requirements` · `/sprint-design` · `/sprint-plan` · `/sprint-selftest` 在**带了本文入参**时读；
> `/version` 规划链在传这些入参前读。**不带任何入参的单独调用，本文一概不适用、行为与接入前完全相同。**
>
> 协议本身归 SKILL：各 SKILL 的 `references/flow-orchestration.md`（四份内容相同）与
> `dev-manual-testcase/references/flow-scale-control.md`。本文只写**命令端要做的事**，⛔ 不复述 SKILL 判据。

## 一、入参只由编排层传

| 命令 flag | 传给 SKILL 的入参 | 谁传 |
| :- | :- | :- |
| `--qr-level=scripts\|critical\|full` | `qr_level` | 只由 `/version` 规划链传（缺省 `critical`，见 `/version` 参数表）|
| `/sprint-selftest --prd-presence-table=<路径>` | `prd_presence_mode=table` + `prd_presence_table` | `/version` Step 2.4.3.5：`prd_presence_table.py` 生成了对账表时 |
| `/sprint-selftest --module-case-cap=N` | `module_case_cap` | `/version` Step 2.4.3.5：L 档传 30 |
| `/sprint-selftest --matrix-scope=p0` | `matrix_scope` | `/version` Step 2.4.3.5：L 档传 |
| `/sprint-selftest --module-kind=…` | `module_kind` | `/version` Step 2.4.3.5：恒传，缺省 `auto`（SKILL 读详细设计「模块类型」，缺字段按页面模板）|
| `/sprint-selftest --plan-ref-mode=deferred` | `plan_ref_mode` | `/version` Step 2.4.3.5：仅 fresh 模式与 `/sprint-plan` 并行时 |

- ⛔ 子命令**不得自行推断或补默认值**：没收到 flag 就不传入参，SKILL 按缺省（= 现状全量 QR）执行。
  这正是 SKILL 协议的总约束「非缺省值只由编排层传入」——命令端替它「顺手补上 critical」，
  等于让单独调用也悄悄裁掉语义审。

- `dev-manual-testcase` 的这四个入参**只改产物写法与体量**，不放松 PRD 功规点 100% 覆盖、上游溯源、字段核对、
  反向占比 ≥40%、P0/P1 覆盖（见该 SKILL `flow-scale-control.md` 开头）。命令端回检 `check_case_stats.py` 时
  **带同样的参数**（`--scale L --module-case-cap N`、`--prd-presence-table <路径>`），否则 SKILL 内外两次判定口径不一。

## 二、四个命令对应的 SKILL 与产物索引

| 命令 | SKILL | 移交清单所在的 `00_索引.md` |
| :- | :- | :- |
| `/sprint-requirements` | `ux-logic-extractor` | `docs/requirements/{version}/研发需求/00_索引.md` |
| `/sprint-design` | `dev-logic-architect` | `docs/design/detail/{version}/00_索引.md` |
| `/sprint-plan` | `dev-execution-planner` | `docs/plans/{version}/00_索引.md` |
| `/sprint-selftest` | `dev-manual-testcase` | `docs/testing/{version}/研发自测/00_索引.md` |

## 三、调用时与返回后

1. **调用时**：在 SKILL 调用参数里写明 `qr_level=<档位>`（原样传，⛔ 不改写）。
2. **SKILL 执行中**：SKILL 每输出一行 `[AIDP-STAGE] {...}`，按 `/version` Step 2.3.9 当下执行
   `aidp_run_metrics.py ... stage --line '<该行>'` 落盘（计量失败只告警）。
3. **返回后，第一件事**——校验移交清单（档位必须与派发时一致）：

   ```bash
   QO="python3 {{AIDP_HOME}}/skills/<SKILL>/scripts/qr_orchestration.py"
   $QO parse-handoff <上表的 00_索引.md> --expect-level <档位>
   ```

   | 退出码 | 含义 | 处置 |
   | :-: | :- | :- |
   | 0 | 清单与 SKILL checklist 推导结果逐项一致（`full` 档 = 确认无残留块） | 继续 |
   | 1 | 少登记 / 多登记 / 字段被改 / 把 Critical 维度移交 / 位置不对 | **本步未完成**：按该命令既有的「SKILL 产物不合格」处置（交互式停下报出；无人值守按失败处置交熔断） |
   | 2 | SKILL 自身契约坏了（checklist 缺等级列等） | 同上，并在报告里写明是 SKILL 契约问题 |

   ⛔ 不得因为「SKILL 自己说 QR 通过了」就跳过本校验：移交清单写不全时，被漏登记的维度既没被
   SKILL 审、也不会被统一审计接手——两头落空，而产物看起来一切正常。
4. **移交的维度不是「审过了」**：它们由 `/version` Step 2.4.7 的 version-auditor 统一接手，
   审完才清掉清单块（见该 Agent「移交维度」节）。子命令**单独**带 `--qr-level` 调用时，
   清单留在 `00_索引.md` 里即表示「待统一审计」，⛔ 不得手工删除。
