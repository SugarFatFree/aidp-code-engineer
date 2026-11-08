# /sprint-full — Sprint 一键执行（含自动累进）

你正在执行 `/sprint-full` 命令，完成单个 Sprint 的完整闭环：启动 → 开发 → 测试 → 修复 → 关闭。

> 🔀 **与 `/sprint-batch` 的边界**：本命令跑**单个** Sprint；要连续跑完整个版本的多个 Sprint 用 `/sprint-batch`（它内部循环调用本命令）。
> 🔀 **与 `/sprint-dev` / `/sprint-bugfix` 的边界（模式 B 累进时）**：三者都能"传一句描述→累进新 Sprint"，区别在**闭环范围与意图**——`/sprint-dev "<新功能>"` = 累进 + 开发，**默认亦串联 test→bugfix→close**（传 `skip-test` 才只开发）；`/sprint-bugfix "<较大 bug>"` = 缺陷意图专用入口（走 bugfix skill + 系统化调试）；**本命令 = 累进 + 完整闭环 start→dev→test→bugfix→close**，适合"要求一次跑到验收关闭"的新功能。**bug 修复优先用 `/sprint-bugfix`**（意图匹配、缺陷登记/复现更完整），不建议用本命令的模式 B 顶替。

**★ 本命令支持两种模式**：
- **模式 A（按计划执行）**：`/sprint-full {NNN}` — 执行 `01_研发执行计划.md` 中已规划的 Sprint
- **模式 B（自动累进新增）**：`/sprint-full "<目标描述>"` — 创建新 Sprint，序号自动累进，用于首轮 Sprint 全部完成后继续迭代

**★ 本命令是编排器**：按顺序调用子命令 `/sprint-start` → `/sprint-dev` → `/sprint-test` → `/sprint-bugfix` → `/sprint-close`。

参数：$ARGUMENTS
- `/sprint-full 001`                        — 模式 A：执行已规划的 Sprint-001
- `/sprint-full "新增用户导出功能"`          — 模式 B：自动创建新 Sprint 并执行
- `/sprint-full 002 skip-bugfix`            — 跳过 bugfix 循环
- `/sprint-full "xxx" skip-bugfix`          — 模式 B + 跳过 bugfix 循环
- `--from-batch`                             — 批量子任务标志（由 `/sprint-batch` 或 `/sprint-autopilot` 逐 tick 单 Sprint 路径隐式注入）：① 输出切紧凑模式，抑制规则详见下方「`--from-batch` 输出抑制规则」段；② **必须原样透传给 Phase 2/3/4/5 的子命令**——子命令据此**不弹 `AskUserQuestion`**：带 `--unattended` 时按预声明 / 保守默认；否则把需要用户裁决的内容决策门作为「⏸ 待裁决：<门名> / <选项> / <推荐>」返回，⛔ 不自行拍板（交互式由 `/sprint-batch` 主循环代问后续派，见其 Step 3）
- `--unattended`                             — 无人值守：内部决策门改为消费 PRD 预声明、**绝不弹 `AskUserQuestion`**；由 `/sprint-batch`·`/sprint-autopilot` 必传下来（本文件下方多处消费它，必须登记在本参数表内）
- `--aiauto-test-required` — 透传外层后续实测意图给 `/sprint-dev`，仅要求生成用例。
- `--skip-aiauto-test` — 透传外层未安排实测；若同时带 required，required 优先。
- `--stop-on-blocker`                        — 遇阻塞项即停并回传，不继续后续阶段（`/sprint-batch` 的合法停顿来源之一）
- `--resume` — 仅模式 A：恢复同版本、同用户、同编号的已启动未关闭 Sprint；通过下方恢复门后跳过 Phase 1，保留 activeContext，从 Phase 2 继续。不是关闭或开新 Sprint 的豁免。
- `--cascade-now` — 仅用户/父链显式要求时原样透传；不因同轮 test→close 自动加上，S/M/L 依契约协议决定成文时机。
- `--dev-scale=S|M|L` — 原样透传 `/sprint-dev` 判档，不绕过新表/破坏性安全门。

**用例意图透传**：调用 `/sprint-dev` 时必须原样传递 `--aiauto-test-required` / `--skip-aiauto-test`。`--from-batch` 只表达被编排，不表达是否实测；不得据此把已取消的实测恢复，也不得吞掉已安排的实测用例。

## `--from-batch` 输出抑制规则

当参数含 `--from-batch` 时，本命令是 `/sprint-batch` 循环体内的子任务，**单 Sprint 完成 ≠ 整个用户任务结束**。为避免 Claude 把 Phase 5 末尾的"📌 下一步"段落渲染出来后误以为命令到此结束、停止循环：

- ✅ **必须输出**：一行紧凑摘要 `▶ Sprint-{NNN} ✅ 完成（{N} 接口 / {N} 页面 / bugfix {M} 轮 / 待修 {K}）` 或对应软/硬失败状态行
- ❌ **必须抑制**：本文档「最终输出」段中的「📌 下一步：`/sprint-full {NNN+1}` / `/sprint-full "<新功能描述>"` / `/sprint-bugfix`」整段（含「模式 A 输出」「模式 B 输出」两份），不要打印
- ❌ **必须抑制**："各阶段摘要 / 产出文件 / 增量追加的文件"等冗长清单，不要打印
- 控制权立即返还 `/sprint-batch` 由它继续循环下一个 NNN

> 不带 `--from-batch`（用户直接调 `/sprint-full {NNN}`）→ 保持原"最终输出"完整段落不变。

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `python3 {{AIDP_HOME}}/scripts/vcs.py user`（唯一解析实现：显式 → 本地 Git 身份 → `AIDP_USER` → OS 用户；⛔ 别自己拼 `git config user.name`，无 Git 项目上会解析出另一个身份）

## 前置检查

1. **模式 A 非 resume** 确认版本规划文档已生成；`--resume` 先过第 2 条恢复门，正式计划路径保持下列文档检查，已放行 S/M 契约路径读既存版本基线与卡，不要求本轮已成正式计划。模式 B 按下方契约协议判档，不在入口强制先生成本轮四层正式文档：
   - `ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——multi 模式按系统拆分时 `01_研发需求.md` 本就不存在，硬判会把合规项目误判缺失而错误停止）
   - **详细设计**：`ls docs/design/detail/{version}/*.md` 有内容主文档即可（★ **用 glob 探测、兼容约定 14 三态**——拆分态 `00_索引.md`+`01_详细设计.md`… / 单份态 `00_详细设计.md` / 历史存量裸名 `详细设计.md`；**不硬编码裸名**，否则拆分态项目会被误判缺失而错误停止）
   <!-- dup-check: ignore 前置检查清单需各命令自包含，读者不应为一行 glob 跳转 -->
   - 研发执行计划：`ls docs/plans/{version}/{01_研发执行计划,00_索引,00_研发执行计划}.md docs/plans/{version}/0[0-9]_M*研发执行计划.md docs/plans/{version}/NN_研发执行计划-*.md 2>/dev/null` 任一命中即可（**不硬编码裸名**，理由同上一行研发需求；合法布局见 `/sprint-plan` Step 1「输出」）
   - 任一缺失 → **停止执行**，提示先执行 `/version {version} "{里程碑}"`
2. **带 `--resume` 时先执行恢复门，成功即替代下方开工门**（先按参数解析归一 `{NNN}` 为三位数字；自然语言模式 B 不允许 resume；调用方版本必须与前置流程解析的当前版本一致）：

   <!-- resume-gate -->
   ```bash
   python3 - "{version}" "{NNN}" <<'PY'
import json, re, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from check_open_sprints import scan
from vcs import developer_identity
root = Path.cwd(); version, sprint = sys.argv[1:]
user = developer_identity(root)
state = scan(root, version, scope="started")
key = f"Sprint-{sprint}"
if state["open"] != [key]:
    raise SystemExit("resume-conflict: 必须是唯一已启动未关闭 Sprint")
resume_source = "plan"
if key not in state["planned"]:
    # 新协议 S/M 可尚未成正式计划；严格消费启动时的放行块，不按文件存在放行。
    contract_path = f"docs/design/detail/{version}/_sprint-{sprint}-契约卡.md"
    def unique_object(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("契约 JSON 重复键")
            result[name] = value
        return result
    try:
        card = (root / contract_path).read_text(encoding="utf-8")
        fence = chr(96) * 3
        blocks = re.findall(r"(?m)^" + fence + r"aidp-contract\s*\n([\s\S]*?)^" + fence + r"\s*$", card)
        if len(blocks) != 1 or len(re.findall(r"(?m)^" + fence + r"aidp-contract\b", card)) != 1:
            raise ValueError("契约须恰有一个 aidp-contract 块")
        def invalid_constant(value):
            raise ValueError(f"非法 JSON 常量：{value}")
        gate = json.loads(blocks[0], object_pairs_hook=unique_object, parse_constant=invalid_constant)
        revision = gate.get("contract_revision") if isinstance(gate, dict) else None
        if (not isinstance(gate, dict) or gate.get("version") != version
                or gate.get("sprint") != sprint or gate.get("owner") != user
                or gate.get("dev_scale") not in ("S", "M")
                or type(revision) is not int or revision <= 0
                or type(gate.get("approved_revision")) is not int
                or gate["approved_revision"] != revision or gate.get("status") != "approved"):
            raise ValueError("契约身份/档位/批准修订无效")
        context = (root / "memory" / version / user / "activeContext.md").read_text(encoding="utf-8")
        plain = context.replace("**", "").replace("`", "")
        revisions = re.findall(r"(?m)^\s*(?:-\s*)?contract_revision\s*[:：]\s*([1-9]\d*)\s*$", plain)
        paths = re.findall(r"(?m)^\s*(?:-\s*)?contract_path\s*[:：]\s*(\S+)\s*$", plain)
        if revisions != [str(revision)] or paths != [contract_path]:
            raise ValueError("activeContext 契约路径/修订不匹配")
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(f"resume-conflict: {exc}")
    resume_source = "contract"
owners = []
for directory in (root / "memory" / version).iterdir():
    if not directory.is_dir():
        continue
    active = directory / "activeContext.md"
    text = active.read_text(encoding="utf-8") if active.is_file() else ""
    current = any(re.search(r"(?:当前\s*Sprint|Sprint\s*编号)\s*[:：|]\s*" + key + r"\b", line.replace("*", "").replace("`", ""))
                  and not re.search(r"已关闭|未开始|待开始", line) for line in text.splitlines())
    marker = directory / "sprints" / f"sprint-{sprint}.started.json"
    if current or marker.is_file():
        owners.append(directory.name)
    if directory.name == user and not current:
        raise SystemExit("resume-conflict: 当前用户 activeContext 不匹配，禁止重置后冒充恢复")
if owners != [user]:
    raise SystemExit("resume-conflict: 所属用户不唯一或不是当前用户")
print(f"RESUME_OK={sprint}")
print(f"RESUME_SOURCE={resume_source}")
PY
   RESUME_RC=$?
   [ "$RESUME_RC" -eq 0 ] || exit "$RESUME_RC"
   ```

   成功后读取原 activeContext 的已完成/待办、任务清单和实际代码；**跳过 Phase 1 `/sprint-start`**（它会重置上下文）。进入 Phase 2 `/sprint-dev {NNN} skip-test [--cascade-now] [--unattended]` 并透传原有 flags，以实际文件核实已完成项、补完未完成项，然后照常 Phase 3→4→5；测试必须针对恢复后的代码重跑。任何阶段失败即返回 `closed:false`，不得提前归档。
   恢复门非零 → 返回 `resume-conflict` 交调用方失败记账，不改上下文、不自动 close。
3. ★ **未带 `--resume` 才执行约定 9 开工门（确定性判据，⛔ 不读 `activeContext.md` 自行裁量）**：

   ```bash
   python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version {version} --scope started --json
   OPEN_RC=$?        # 0=无已启动未关闭轮次→继续；非0=有在途轮次或状态读取失败→停止
   ```
   - 退出码 `1` → **停止执行**并把 `open[]` 列给用户，要求先 `/sprint-close`
     （与独立 `/sprint-start` 同档——约定 9 是**硬停**不是提示）。
   - 退出码 `2` → 状态读取失败，停止并修复输入；无人值守返回失败信号。
   - 判据单一信源 = 该脚本的 `started` 范围：跨用户启动记录与显式当前状态扣除同时具备同行 ✅ 与 Sprint 归档文件的关闭记录；尚未开始的计划不阻断本轮启动。

## 参数解析

### 判断是模式 A 还是模式 B

```
if 参数第一项是纯数字（如 "001" / "2" / "042"）:
    → 模式 A：Sprint 编号 = 该数字
else if 参数第一项是带引号的字符串或自然语言:
    → 模式 B：需要自动累进 Sprint 序号
    → 新 Sprint 描述 = 该字符串
else:
    → 错误：提示正确格式
```

---

## 模式 A：执行已规划的 Sprint

### Phase 0A：读取 Sprint 范围

从 `docs/plans/{version}/01_研发执行计划.md` 读取指定 Sprint 的任务范围和目标。恢复门输出 `RESUME_SOURCE=contract` 时改读已校验卡的 REQ/AC/Task 与原 activeContext，补完实际未完成项；approved 只代表开发前契约放行，不代表 M 文档已汇合或验收通过。

---

## 模式 B：自动累进新增 Sprint

### Phase 0B.0：★ 版本落点决策门（累进前置，最先跑，先于任何持久副作用）

> 开工门仍先于任何持久副作用。模式 B 的版本落点实际委派 `/sprint-dev [--unattended] [--from-batch]` 的 Phase 0B.0，沿用已有授权/未知状态 fail-closed 规则；本层只传递用户已作出的选择，不重复询问或先建目录。

> 版本号 / tag / 持久目录的决定继续由原版本落点门负责；`--unattended` / `--from-batch` 只改变交互方式，不扩大版本、破坏性操作或部署授权。原门的默认决策留痕仍在 `builds[current_build].decidable_skips[]`（无 build 才回落版本级），本层消费其结果。

### Phase 0B.1：编号由开发入口统一分配

先 Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`。本层不预留编号、不生成文档、不写 activeContext；Phase 2 委派 `/sprint-dev [--unattended] [--from-batch] "{目标描述}" skip-test`，由它执行版本/开工门、全局取号、契约卡与分档并回传 `{NNN}`，本层随后使用该真实编号。

### Phase 0B.2：契约分档与文档时机

`{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md` 为唯一权威，由 Phase 2 的开发入口执行：S 契约先行、四族义务攒批；M 代码/docs 按互斥写集并行并在验收前完整汇合；L 先完成正式文档再开发。本层不另跑 L1→L2→L3→L4 的前置全套，不把 test→close 解释为自动 `--cascade-now`。显式传入的 `--cascade-now` 仍必须原样透传，正式用例 required 门不变。

---

### Phase 0B.3：★ 口述追加 / 口径反转清算门（模式 B 专属，约定 34 ⑥）

> 口径反转仍由 `/sprint-dev` Phase 0B.1.3 在派发实现之前执行，并把失效结论/落点、旧安全结论是否成立及四族义务写入契约。本层核对开发回传，缺失不得进入 Phase 3；S 只推迟成文，不推迟反转清算。

## 阶段检查点协议（模式 A 和 B 通用）

每个阶段完成后输出简要状态。遇到阻塞性问题立即停止并报告。

## Phase 序列（模式 A / B 共用；与上方 `Phase 0A`/`Phase 0B.*` 同级，同属一条 Phase 序列）

### Phase 1：启动 Sprint

模式 B **跳过本阶段**：由 Phase 2 的 `/sprint-dev "{目标描述}" skip-test [--from-batch] [--unattended]` 在契约放行后启动，外层不得先取号/先 start。模式 A 已通过 `--resume` 恢复门时同样跳过本阶段，保留原 activeContext。其余模式 A 按下方启动。

```
执行：/sprint-start {NNN} [--unattended]（无人值守时透传）
```

子命令读取需求和设计文档（模式 B 读取刚追加的增量章节），更新 activeContext。

```
▶ Phase 1 完成：Sprint-{NNN} 已启动
  - Sprint 目标：{目标}
  - 功能范围：{N} 个模块
  - 模式：{A 按计划 / B 自动累进}
```

### Phase 2：开发

```
模式 A：/sprint-dev {NNN} skip-test [--cascade-now] [--from-batch] [--unattended]
模式 B：/sprint-dev "{目标描述}" skip-test [--cascade-now] [--from-batch] [--unattended]
# --cascade-now 仅已有显式参数才传；--dev-scale、实测意图同样原样透传。模式 B 完成后消费真实 {NNN}、契约与汇合证据。
# ★ 必传 skip-test：本命令是编排器，test/bugfix/close 由下方 Phase 3/4/5 统一负责；
#   若不传 skip-test，/sprint-dev 会自行串联 test→bugfix→close（其默认行为），与本命令 Phase 3/4/5 重复执行整条链。
# ★ --unattended（由 /sprint-batch 透传）时必传，令 /sprint-dev 的 UI C/D 门与约定22 级联门消费 PRD autopilot_decisions 预声明、不弹窗（autopilot 7×24 兜底）
```

（`/sprint-dev` 按契约分档、写集隔离和 TDD 执行，汇合时只做一次契约一致性 reviewer；完整质量审查在 Phase 3。M 的 docs 未完成/修订不一致、任一汇合证据失败均返回 `closed:false`，不得进入测试。）

```
▶ Phase 2 完成：代码已实现
  - 后端：{N} 个接口（编译验证移至 Phase 3 验收，仅改动侧 + 资源受限）
  - 前端：{N} 个页面（前端校验（lint + 类型检查，不打包）移至 Phase 3 验收，仅改动侧 + 资源受限）
```

### Phase 3：测试

```
执行：/sprint-test {NNN} [--from-batch] [--unattended]
```

（`/sprint-test` 内部以仅验收模式使用 `code-verification-loop` + 可选 `api-tester`，本命令不另行调用。）前端浏览器仿真测试在部署后走独立命令 `/sprint-aiauto-test`（chrome-devtools-mcp，默认无头），不在本阶段。
发现的 bug 写入 `docs/bugfix/{version}/bugfix-{今日}-{user}.md`。

```
▶ Phase 3 完成：测试已执行
  - code-verification-loop：各维度 Pass/Fail + Critical {N} / Important {N}
  - 新增 bug：{N} 个
```

### Phase 4：只接管未闭环项

Phase 3 已完成当轮原实现者修复、定向测试、reviewer 差量复核与集中 Sprint 单测，本层不重修已闭环项、不重复完整 CVL 或完整 `/sprint-test`。

- 没有未闭环项且验收基线可信 → 进入 Phase 5。
- 只有可修复残项且允许 bugfix → 保留当前 Sprint 与问题 ID，委派原实现者继续；需要独立修复入口才调用 `/sprint-bugfix sprint-{NNN} [--from-batch] [--unattended]`，仅传未闭环项与证据。随后用 `/sprint-test {NNN} --resume-acceptance [--from-batch] [--unattended]` 续接差量与最终 full，不重跑已完成完整质量审查。
- 产品/版本/破坏性或环境待决 → 回传具体原因；不让 bugfix 无谓空转。外层和验收共用本次问题的修复轮次，连续 5 轮仍未闭环返回失败，不能外层重置计数再来 5 轮。
- `skip-bugfix` 只跳过外层补救，不取消验收内部纠错，也不豁免关闭证据。残项未闭环 / `--stop-on-blocker` 命中 → 返回 `closed:false`，保留上下文，不以软失败继续归档。

```
▶ Phase 4 完成：Bugfix 循环
  - 循环轮次：{M}
  - 修复 bug：{N}
```

### Phase 5：关闭 Sprint

```
执行：/sprint-close {NNN} [--from-batch] [--unattended]
# ★ `--from-batch` 与 `--stop-on-blocker` 同族，本命令带则**必须原样透传**：
#   它的语义是「我在批量循环体内、别停下来问人」。少转发这一个参数，
#   交互式 `/sprint-batch`（常规用法，7×24 才必带 --unattended）跑 N 个 Sprint
#   就会在每个 Sprint 末尾的验收门各停一次、共问 N 次 —— 与批量执行的目标
#   「计划里的全部 Sprint 一次跑完，中途不问人」正相反。
#   三段各自都合理（batch 传了、close 也按参数判了），断点恰在中间这一层。
```

记录本 Sprint 验收结论（并入 AI执行报告 / progress.md，不单独出验收报告文件）、归档、更新 progress.md 和 databaseBaseline.md（如模式 B 有新表）。

```
▶ Phase 5 完成：Sprint-{NNN} 已归档
```

---

## 最终输出

> ⚠️ **本段输出受 `--from-batch` 抑制规则约束**（权威定义见顶部「`--from-batch` 输出抑制规则」段）：含 `--from-batch` → 跳过下方「模式 A 输出」「模式 B 输出」，仅输出一行紧凑摘要后 return；不含 → 按下方完整段落输出"📌 下一步"等指引。

### 模式 A 输出（仅在**不含** `--from-batch` 时输出）

```
🎉 /sprint-full {NNN} 完成（按计划执行）

各阶段摘要：
  Phase 1-5：✅ 完成

📋 产出文件：
- docs/testing/{version}/sprint-{NNN}/
- docs/bugfix/{version}/bugfix-*-{user}.md（如有新 bug）
- memory/{version}/{user}/sprints/sprint-{NNN}.md

📌 下一步：
- /sprint-full {NNN+1}          → 继续执行下一个已规划的 Sprint
- /sprint-full "<新功能描述>"    → 自动累进新增 Sprint（模式 B）
- /sprint-bugfix                        → 单独处理待修复的 bug
```

### 模式 B 输出（自动累进；仅在**不含** `--from-batch` 时输出）

```
🎉 /sprint-full "{描述}" 完成（自动累进 Sprint-{新NNN}）

📋 本轮产物（按真实档位与落盘状态列出）：
- docs/requirements/{version}/产品提供/口述补充-{YYYYMMDD-HHMM}.md（口述记录）
- docs/design/detail/{version}/_sprint-{NNN}-契约卡.md（修订、真实写集、汇合证据）
- {已完成的正式需求/设计合册或分册/计划/适用用例与 SQL 路径；不列未生成文件}
- {S 待成文四族义务与用例 required/deferred 状态}

各阶段摘要：
  Phase 0B：{S 契约与义务登记 / M 并行汇合 / L 先完整文档}
  Phase 1-5：✅ 完成

📋 Sprint 产出：
- docs/testing/{version}/sprint-{新NNN}/
- memory/{version}/{user}/sprints/sprint-{新NNN}.md

📌 下一步：
- /sprint-full "<下个目标>"     → 继续新增功能/修复
- /sprint-bugfix                       → 单独处理 bug（无需新 Sprint）
- /version {version}            → 本版本全部完成后发布
```

---

## 使用示例

```bash
# 场景 1：按计划执行
/version V0.1.0 "M1 MVP"       # 规划 5 个 Sprint
/sprint-batch                   # 批量执行完
# ... 人工验证 ...

# 场景 2：新增功能（自动累进 Sprint-006）
/sprint-full "新增用户导出功能"

# 场景 3：修复较大的功能性 bug → ⛔ 不用本命令，走 /sprint-bugfix 方式 C
#   （缺陷意图专用入口：bugfix skill + 系统化调试 + 缺陷登记/复现，本命令都没有）
/sprint-bugfix "修复批量导入重复校验逻辑错误"

# 场景 4：零散的 bug（不需要新 Sprint）
# 先在 docs/bugfix/{version}/bugfix-{今日}-{user}.md 记录 bug
/sprint-bugfix                         # 直接修复，归属当前最近的 Sprint

# 场景 5：只修指定 Sprint 的 bug
/sprint-bugfix sprint-002

# 场景 6：所有工作完成，发布
/version V0.1.0
```

## 模式选择建议

| 场景 | 推荐方式 |
|------|---------|
| 规划阶段确定的 Sprint | `/sprint-full {NNN}` 或 `/sprint-batch` |
| 首轮 Sprint 全部完成，继续新增功能 | `/sprint-full "<描述>"` 自动累进 |
| 简单 bug 修复（单文件/配置调整） | 直接 `/sprint-bugfix`，无需新 Sprint |
| 较大的功能性 bug（含设计变更） | `/sprint-bugfix "修复 xxx"` 方式 C 自动累进（**不用本命令**，见文首边界声明）|
| 需要严格审核每步 | 分步执行 `/sprint-start` → ... → `/sprint-close` |
