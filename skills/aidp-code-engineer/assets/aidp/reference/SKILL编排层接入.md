# SKILL 编排层接入（版本规划四个子命令的共用契约）

> **谁读**：`/sprint-requirements` · `/sprint-design` · `/sprint-plan` · `/sprint-selftest` 在调用生成能力前读；
> `/version` 规划链在传这些入参前读。单独调用同样按父授权确定QR档位，不把缺参数解释成自动full。
>
> 协议本身归 SKILL：各 SKILL 的 `references/flow-orchestration.md`（四份内容相同）与
> `dev-manual-testcase/references/flow-scale-control.md`。本文只写**命令端要做的事**，⛔ 不复述 SKILL 判据。

## 一、入参只由编排层传

| 命令 flag | 传给 SKILL 的入参 | 谁传 |
| :- | :- | :- |
| `--qr-level=scripts\|critical\|full` | `qr_level` | AIDP生成调用层按下方父策略选择；version保留已有critical/fast配方|
| `/sprint-selftest --prd-presence-table=<路径>` | `prd_presence_mode=table` + `prd_presence_table` | `/version` Step 2.4.3.5：`prd_presence_table.py` 生成了对账表时 |
| `/sprint-selftest --module-case-cap=N` | `module_case_cap` | `/version` Step 2.4.3.5：L 档传 30 |
| `/sprint-selftest --matrix-scope=p0` | `matrix_scope` | `/version` Step 2.4.3.5：L 档传 |
| `/sprint-selftest --module-kind=…` | `module_kind` | `/version` Step 2.4.3.5：恒传，缺省 `auto`（SKILL 读详细设计「模块类型」，缺字段按页面模板）|
| `/sprint-selftest --plan-ref-mode=deferred` | `plan_ref_mode` | `/version` Step 2.4.3.5：仅 fresh 模式与 `/sprint-plan` 并行时 |

- `qr_level` 必须由下方调用层显式计算并传给SKILL，不能遗漏而回落full；其余规模入参仍只透传实际收到的值，不自行补默认。

### 文档生成的授权与最小QR

动作来源、预算与grant revision按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`；本节只定义四个生成入口的调用适配。微小文档编辑直接复用必要编辑能力，不机械调用整套生成SKILL。显式生成职责包括依赖无法拆开的最低质量自检：四Skill的scripts档仍跑全部机器门及不可关闭Critical语义，不能宣称“纯脚本/关闭全部QR”，不编none档。

入口先建立/继承真实execution_context；以下围栏在每次Skill调用前执行。REQUESTED_QR_LEVEL来自本次或父入口实际参数，缺省空；没有document授权时整段NOT_REQUESTED返回，不创建目录或生成产物。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?生成入口必须传父上下文}"
REQUESTED_QR_LEVEL="${REQUESTED_QR_LEVEL:-}"
QR_ROUTE=$(python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . \
  --execution-context "$EXECUTION_CONTEXT" --phase route --json) || exit $?
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action document || exit $?
DOCS_AUDIT_ALLOWED=$(printf '%s' "$QR_ROUTE" | python3 -c 'import json,sys; print(int("docs-audit" in json.load(sys.stdin)["authorized_actions"]))') || exit $?
QR_LEVEL=scripts
if [ "$DOCS_AUDIT_ALLOWED" = 1 ]; then QR_LEVEL="${REQUESTED_QR_LEVEL:-critical}"; fi
case "$QR_LEVEL" in scripts|critical|full) ;; *) exit 2 ;; esac
printf 'qr_level=%s\n' "$QR_LEVEL"
```

调用prompt必须带 `qr_level=$QR_LEVEL`、父context/revision/action/budget及真实输入hash；每个新Agent先按light-context预留agents预算。SKILL返回按本节原parse-handoff解析，保留既有索引移交块与真实未审事实，不另造清单。没有docs-audit时，非Critical语义/独立审计为NOT_REQUESTED，不登记成本轮欠账、不立即派qr-handoff-auditor，不以清块为由补审。若用户仅要求编辑而不能承担依赖最低生成校验，继续必要编辑能力，不谎称完整生成已通过。

**落盘后复核去重**：机器门及不可关闭Critical属于所请求生成的最低自检，优先复用同revision/inputs真实hash的既有证据；缺证据/产物改动时仅补失效项。额外代码侧report-only巡检、非Critical语义复核、version-auditor/qr-handoff-auditor须docs-audit，未授权跳过，不以生成后处理名义另叠完整QR。每次派Agent前require_action(document或docs-audit按真实职责)并预留父agents预算，工具失败不自动换一套审计求绿。

有docs-audit的公开/version组合、显式qr-level与fast保留原职责：fast明确延期的检查仍按原收口处理。缓存只复用同revision/inputs真实hash证据；修复只delta，不能因为再进生成子入口叠一轮完整QR。

- `dev-manual-testcase` 的这些入参（`prd_presence_*` / `module_case_cap` / `matrix_scope` / `module_kind` / `plan_ref_mode`）**只改产物写法与体量**，不放松 PRD 功规点 100% 覆盖、上游溯源、字段核对、
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

1. **调用时**：始终传上方实际得出的 `qr_level=$QR_LEVEL`，不按未带flag省略；档位不能给父任务新增docs-audit权限。
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
4. **移交的维度不是「审过了」**：仅docs-audit已授权时由 `/version` Step 2.4.7 的 qr-handoff-auditor 接手，与 version-auditor 并行；
   审计通过后由主流程清掉清单块（见 `{{AIDP_HOME}}/agents/qr-handoff-auditor.md`）。子命令**单独**带 `--qr-level` 调用时，
   清单保留真实未审事实；本轮未授权审计记NOT_REQUESTED，不能推成本轮待办。已授权的fast延期仍为待统一审计，不得手工删除冒充通过。
