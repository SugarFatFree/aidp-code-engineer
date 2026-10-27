<!-- 二次切分 · phase-3 片1/6：覆盖 3.0 报告生成门 / 3.1 报告产物 / 3.2 报告内容 / 3.2.5 截图落盘硬核验-->
# sprint-aiauto-test · Phase 3 详情（测试报告生成 3.0–3.7）

> 本文件是 `/sprint-aiauto-test` 命令 **Phase 3** 详情的**第 1/6 片**（⛔ 本片不含 Phase 3 全部子步——后续子步在 `-2` / `-3` / `-3b` / `-4` / `-5` 分片，按进度依次 Read，勿读完本片即认为已覆盖全段），由命令主体（`{{AIDP_HOME}}/commands/sprint-aiauto-test.md`）在**进入 Phase 3 时用 Read 工具按需加载**。命令主体只保留 Phase 3 的**硬门 + 3.0–3.8 骨架 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入 Phase 3 后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/`。理据/根因见同目录 `rationale.md`。

---

## Phase 3：测试报告生成（HTML — AI测试报告）

> ⛔⛔ **RED FLAG：测试报告唯一形态 = HTML 离线 SPA**。禁止在 `AI测试报告/` 根层另写叙述性 `.md`（各级 `README.md` 除外）；按 3.2.6 经模板生成 `index.html`+`assets/`、写 `data/{BUILD}.js` 并注册脚本。**`build-*/round-*/` 下 SKILL 契约产物一律保留、绝不删**，尤其 `tasks.md` 与 `run-context.md`。误删会破坏断点续跑；根因见 `rationale.md`。
>
> ★ 自检口诀：测试跑完、要落报告时，问自己"我是在 `cp` HTML 模板 + 写 `.js` 数据，还是在写 `.md`？"——若是后者，回到 3.2.6 重来。

### 3.0 ★ 报告生成门（AI测试报告仅 autopilot 流水线驱动时生成）

> 🛑 **进入 3.1~3.2.6 前先判 `REPORT_ENABLED`（Phase 0.2 步骤 2.5 设定）**。AI测试报告是 `/sprint-autopilot` 流水线的官方产物（按 build 归档、随 #F 里程碑通知播报、`/version` 合并为版本测试报告）；直接调用（`--once` standalone / 未挂 autopilot 的独立 /loop / 其他命令经 sprint-batch 但无 autopilot build）时**不产报告**，避免在非流水线场景散落官方报告文件。

```bash
# ★ 跨分片取回本 tick 变量 —— flow 每个分片是**独立的 Bash 调用**，shell 变量不持久；
#   漏这一行会让下方判据读到空串、`${VAR:-默认}` 静默落默认值（恒真/恒假）。
#   真源在 baseline 的（BUILD/DRIVER/DEPLOY_MODE/NOTIFY_ENABLED/LOOP_UNATTENDED…）由脚本自动回落。
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
if [ "$REPORT_ENABLED" != "1" ]; then
  echo "⏭️ 非 autopilot 驱动（无 current_build）→ 跳过 Phase 3 的 AI测试报告 HTML 生成"
  echo "   已完成：测试执行 + 终端结果摘要 + 失败用例回写「问题汇总清单」（供 /sprint-bugfix 拾取）+ baseline aiauto_test_result"
  # 终端打印本轮测试摘要（套件/角色 + 通过/失败/阻塞/忽略 + 通过率 + 失败用例清单 + 运行时错误 R-NNN 计数）
  # baseline 仅写测试结果摘要字段；aiauto_test_report 置 null（标记"未生成报告，非 autopilot 驱动"），见 3.3
  # → 跳过 3.1 / 3.2.5 / 3.2.6（HTML 生成与截图硬核验）；直接进 Phase 3.3 baseline 回写（按 REPORT_ENABLED=0 分支）
  SKIP_REPORT=1   # ★ 真正的流程控制信号，不能只留注释
fi
export SKIP_REPORT="${SKIP_REPORT:-0}"
# ★ 落盘：`export` 跨不过 Bash 调用，而 3.2.5 / 3.2.6 在别的分片里判它
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test SKIP_REPORT "$SKIP_REPORT"
# REPORT_ENABLED=1（autopilot 驱动）→ 正常往下走 3.1 ~ 3.2.6 生成 AI测试报告 HTML
# ⛔ 3.1 / 3.2.5 / 3.2.6 每步开头必须先判 `[ "$SKIP_REPORT" = "1" ] && 跳过本步`：
#    "跳过"若只以注释形式存在，standalone 轮次逐字执行会继续进 3.2.5 截图硬核验
#    （它也没有 BUILD 归属）并 exit 1 —— 把一轮跑完的真实结论整个丢掉。
```

### 3.1 报告产物（HTML 唯一形态 — 不产出 docs/testing markdown 报告）

测试报告**只产出 HTML**，落 AI测试报告离线静态项目（由 3.2.6 生成/刷新）：
```
docs/reports/{TARGET_VERSION}/AI测试报告/
├── index.html                          ← 综合首页 + 各 build 子页（图表）
├── data/{BUILD}.js                     ← 本轮 build 测试数据（window.__BUILDS__.push）
└── screenshots/{BUILD}/{TC-ID}-step{N}.{ext}   ← ext 取 capture 实际产物（.webp 默认 / .png 回退 / .jpg·.jpeg 兼容）
```

> ⚠️ **测试报告唯一形态 = 上面的 HTML 离线 SPA 项目**：测试结果与截图全部进该项目，不生成任何 markdown 测试报告。同一 build 多轮收敛 → 覆盖 `data/{BUILD}.js` 为最新一轮（历史轮次差异由 git 历史追溯）；`/version` 发布时取最终验收 build（buildNo 最大的一轮）→ 版本测试报告单文件 HTML。

★ 截图在 HTML 子页内**缩略图 + 点击放大**（由 `index.html` / `assets/` 渲染），路径相对 `AI测试报告/`，离线 `file://` 可解析；截图缺失一律按执行缺陷处理（见 3.2.5）。

### 3.2 报告内容（捕获后渲染进 HTML 的数据）

> 编号说明：本节子步骤为 3.2 / 3.2.5 / 3.2.6 / 3.2.7（无 3.2.1–3.2.4，编号保持稳定不重排以免下游引用漂移）。

每轮捕获以下内容，按 3.2.6 数据契约写入 `data/{BUILD}.js`，由 `index.html` 渲染为图表 + 表格：
- **测试摘要**：部署模式 / URL / 渲染模式 / 驱动；套件 + 角色；总计 通过/失败/阻塞/忽略/**不适用** + 通过率（分母 = 总数−不适用）+ **无依据的 direct pass 条数**（>0 才列，Important 不阻断）；耗时（→ `summary` + 元字段）
- **详细结果**：每用例 状态(pass/fail/block/skip/na) + 失败原因 + 截图引用 + console/network 错误（→ `cases[]` / `suites[]`）
- **运行时错误汇总**（Phase 2.4 全程捕获，含通过用例 / 自由巡检上的报错）：`R-NNN` + 触发点 + 类别 + 详情 + 截图 + 关联功能 + 严重度（→ `runtimeErrors[]`）
- **问题汇总**（待 sprint-bugfix）：① 用例失败 ② 运行时错误（→ `defects[]`）；② 类每条仍回写主用例文档末尾「问题汇总清单」表（状态 `待修复`，`/sprint-bugfix` 扫描拾取）

> `/sprint-bugfix` 触发文案：如"动态测试失败 + 运行时错误：…"（结果以 HTML 图表呈现）。

### 3.2.5 ★ 归集 skill 证据 + 截图落盘硬核验（强制；缺失绝不生成"完成"报告）

> 先把 SKILL 的 `build-${BUILD}/round-{M}/evidence/{TC-ID}-step{N}.{ext}` 归集到 `AI测试报告/screenshots/{BUILD}/`，再核验非空，**通过后才能生成 HTML / 写完成字段**。格式以 `check_result.py` 为准：Web 默认 `.webp`、不支持才回退 `.png`，兼容 `.jpg/.jpeg`；实际文件名来自证据，禁止按 TC-ID 猜扩展名（约定 21）。
>
> **无头同样必须截图**：`--headless=new` 支持 capture，缺证据按执行缺陷处理，禁止以无头为由豁免本门。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# ⛔ 每步开头必判 SKIP_REPORT（3.1 已落盘）：standalone 轮次没有 BUILD 归属，
#    `SHOT_DIR` 会拼出空 BUILD 段 ⇒ 恒无截图 ⇒ 本门恒失败 ⇒ 3 tick 后冻掉一个
#    本就不该产报告的版本。散文写了"跳过"不算数，必须是可执行判据。
if [ "${SKIP_REPORT:-0}" = "1" ]; then
  echo "⏭️ SKIP_REPORT=1（非 autopilot 驱动，本轮不产 AI测试报告）→ 跳过 3.2.5 截图硬核验"
else
BTR="docs/reports/${TARGET_VERSION}/AI测试报告"
SHOT_DIR="${BTR}/screenshots/${BUILD}"
mkdir -p "$SHOT_DIR"

# ⓪ 归集前跑结果形状硬门；枚举、证据与运行时字段契约均以 check_result.py 为准。
#    多路径通配覆盖全部轮次。形状不合契约时禁止 artifact 兜底制造假绿。
if [ -f {{AIDP_HOME}}/skills/auto-test-runner/scripts/check_result.py ]; then
  # 不用 --strict：I7 direct pass 无轻量事实等 Important 只告警、不阻断。
  # 过滤 issues[].level 与 rule 实名（snake_case），不能拿文档 I 编号作 rule。
  # 新结果必带 --require-runtime-preflight；Web+WebMCP 另加 --webmcp-enabled。
  # 启用判定只走 check_client_mcp.py，兼容旧 webmcp 与新 client_mcp；冲突/检测失败不能当关闭。
  CR_WEBMCP=""
  CR_CLIENT_JSON=$(python3 {{AIDP_HOME}}/scripts/check_client_mcp.py --detect --json); CR_CLIENT_EXIT=$?
  if [ "$CR_CLIENT_EXIT" -ne 0 ] || ! CR_WEBMCP=$(printf '%s' "$CR_CLIENT_JSON" | python3 -c "import json,sys
d=json.load(sys.stdin)
print('--webmcp-enabled' if d.get('declared') is True and d.get('client_type')=='web' and d.get('implementation')=='webmcp' else '')"); then
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
      --phase 3.2.5-client-mcp --reason audit-critical --streak-key client_mcp_gate_fail_streak --threshold 3 \
      --why "客户端 MCP 声明检测失败（exit=${CR_CLIENT_EXIT}），不能按未启用放行"
    exit 0   # 已记账让位，不生成完成报告
  fi
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del client_mcp_gate_fail_streak
  CR_JSON=$(python3 {{AIDP_HOME}}/skills/auto-test-runner/scripts/check_result.py \
    "${BTR}/build-${BUILD}"/round-*/results/ --require-runtime-preflight ${CR_WEBMCP} --json 2>/dev/null); CR_EXIT=$?
  CR_BLOCKING=$(printf '%s' "$CR_JSON" | python3 -c "import json,sys
d=json.load(sys.stdin)
B={'evidence_string_item','runtime_error_incomplete','bad_env_flag','empty_target'}  # 兼容旧名，新契约一律靠下面的 level
print(len([i for i in (d.get('issues') or []) if i.get('level')=='Critical' or i.get('rule') in B]))" 2>/dev/null || echo -1)
  if [ "$CR_EXIT" -ge 2 ] || [ "${CR_BLOCKING:-0}" != "0" ]; then
      echo "❌ 执行结果不合 auto-test-runner 结果契约（阻断项 ${CR_BLOCKING} 条）→ 在报告标「证据形状不合契约」并跳过 artifact 兜底分支"
      SHAPE_BAD=1
  fi
fi

# ① 归集：把 skill 各轮次 evidence 截图（命名 {TC-ID}-step{N}.{ext}）收集/复制到报告路径
#    （skill 产物目录 = 本 BTR，故其 build-${BUILD}/round-*/evidence/ 就在 BTR 下）
#    ★ 扩展名按 SKILL 截图兼容集 .webp/.png/.jpg/.jpeg 收（Web 默认 .webp）。⛔ 只收 *.png
#      ⇒ 默认 webp 产物全落空 ⇒ ② 恒判空 ⇒ 连续 3 次误冻一个健康 build。
#    ★ 按 round **数字升序逐轮覆盖** ⇒ 同名证据以**最新一轮**为准；不用 cp -n。
#      先清本 build 的旧归集图片，防旧 tick 残图冒充本次证据；同主干跨格式只保留最新实际文件。
#      artifact 路径解析与截图扩展名直接消费 SKILL 校验器，避免命令端另造一套解析规则。
python3 - "$BTR" "$BUILD" "$SHOT_DIR" "${SHAPE_BAD:-0}" <<'SHOTS'
import json, re, shutil, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/skills/auto-test-runner/scripts")
from check_result import SCREENSHOT_EXTENSIONS, _artifact_candidates
btr, build, dest, shape_bad = sys.argv[1:]
dest = Path(dest)
for old in dest.iterdir():
    if old.is_file() and old.suffix.lower() in SCREENSHOT_EXTENSIONS:
        old.unlink()
rounds = [p for p in (Path(btr) / ("build-" + build)).glob("round-*")
          if p.is_dir() and re.fullmatch(r"round-\d+", p.name)]
for rd in sorted(rounds, key=lambda p: int(p.name.split("-")[-1])):
    sources = sorted(p for p in (rd / "evidence").rglob("*") if p.is_file())
    if shape_bad != "1":
        for result in sorted((rd / "results").glob("*.json")):
            data = json.loads(result.read_text(encoding="utf-8"))
            for item in data.get("evidence") or []:
                artifact = item.get("artifact") if isinstance(item, dict) else None
                if isinstance(artifact, str) and artifact.strip():
                    sources.extend(p for p in _artifact_candidates(artifact, result) if p.is_file())
    for source in sources:
        if source.suffix.lower() not in SCREENSHOT_EXTENSIONS:
            continue
        for old in dest.iterdir():
            if old.stem == source.stem and old.suffix.lower() in SCREENSHOT_EXTENSIONS:
                old.unlink()
        shutil.copy2(source, dest / source.name)
SHOTS

# ② 硬核验：截图非空才通过；缺图先记账、发 #4，再 exit 0 让位，不能只 echo 或裸 exit 1。
if [ -z "$(find "$SHOT_DIR" -type f \( -iname '*.webp' -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) 2>/dev/null | head -1)" ]; then
  echo "❌ Phase 3 核验失败：截图为空 $SHOT_DIR —— auto-test-runner 未按 capture 契约在关键步骤（登录/提交/状态变化/断言/报错）出图"
  # → 用例已跑完无法回补：data/{BUILD}.js 须把对应 case 的 screenshot 标"缺图"并记执行缺陷，不得静默
  # ★ 记账 + 达阈冻结（防 /loop 每 tick 重撞同一失败）：连续 3 次即按 Phase 0.2「冻结字段写入契约」冻结本版
  N=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" bump shot_gate_fail_streak)   # ★ 本门专属计数，⛔ 不与 3.2.6 两门共用
  # 无唤醒源=没有下一 tick 叠 streak，阈值恒不可达 → 当场按达阈处置（根因见 rationale.md）
  if [ "$N" -ge 3 ] || [ "${HAS_WAKE_SOURCE:-0}" = "0" ]; then
    # ★ `unconverged_frozen_head` 必须与四件套**同批写入**（理据见 rationale.md「冻结快照 HEAD」）
    python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" \
      set needs_human true aiauto_frozen_at @now freeze_reason unconverged \
      unconverged_frozen_head "$(git rev-parse HEAD 2>/dev/null || echo '')" \
      needs_human_reason "连续 $N 次截图核验失败：auto-test-runner 未按 capture 契约出图"
    python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto_blocked_reason "frozen:unconverged@$TARGET_VERSION"
    echo "⏸️ 连续 $N 次截图核验失败 → 冻结本版待人工（解冻靠新提交 / 新部署 / 人工 retry）"
  fi
  # ★ 发 #4 通知：参数须对齐 notify.py 真实签名（无 --kind/--body），写错会被 `|| true` 咽掉
  python3 {{AIDP_HOME}}/scripts/notify.py --node "#4" \
    --auto --title "AI 测试受阻：截图为空" --header-color red \
    --version "$TARGET_VERSION" --build "${BUILD:-?}" \
    --section "截图核验失败第 $N 次（阈值 3）。$SHOT_DIR 下无截图（.webp/.png/.jpg/.jpeg），auto-test-runner 未按 capture 契约出图。本轮结论未采信、已让位。" || true
  exit 0   # ⛔ 不用 exit 1：已记账 + 已告警 → 让位本 tick（同本命令其余各处门）
fi
# 核验通过只清本门计数；截图、finalize、骨架三门各用独立 streak，不能互相清零。
python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del shot_gate_fail_streak || true
fi   # ← SKIP_REPORT 守卫结束
```

- 截图齐 → 进 3.2.6 生成 HTML（3.2.6 末尾再自核验 `data/{BUILD}.js` + `index.html` 落盘 + 注册）；
- 截图缺失且无法当场补 → 按上方代码：**发 #4 告警通知 + 记账 `shot_gate_fail_streak` + `exit 0` 让位本 tick**（⛔ 不是 `exit 1`：裸失败退出会丢掉一整轮已跑完的真实结论、零通知、静默冻结——正是本段上文点名要避免的形态），且**不更新 baseline 的"完成"字段、不发完成类通知**；连续 3 次达阈才按 `report-gate` 冻结本版。


### 3.2.5bis ★ 派 SKILL 的 8 维度独立质量检查子 Agent（Critical 门）

> **必须派独立子 Agent，主流程不得直接内联或跳过**；仅派发失败时按下文降级。`tasks_state.py scan` 必须在报告生成前跑到。
> **不可豁免范围只认 SKILL `quality-review-checklist.md` 的 Critical 标记**，含维度与折入的子核查，命令端不得另列固定编号名单（约定 21）。

**执行**（约定 36：命令既定职责内的派发，无需征询；派不出后台就转前台/内联，**绝不静默跳过**）：

用 `Agent` 工具派**一个独立子 Agent**（隔离上下文），prompt 至少给：

- 质量维度清单路径：`{{AIDP_HOME}}/skills/auto-test-runner/references/quality-review-checklist.md`（**判据以它为单一信源，命令端不复述维度内容**，约定 21）
- 本轮 round 目录：`docs/reports/{TARGET_VERSION}/AI测试报告/build-{BUILD}/round-{M}/`
  （⚠️ **`build-` 前缀不能漏**：SKILL 按其契约把证据落在 `build-${BUILD}/round-{M}/`，同文件上方引用的也是这个形态。少了前缀，质量检查子 Agent 扫的是一个不存在的目录——判通过即恒真空门、判失败即误冻结健康 build，两种结果都错。)
- 要求：先跑 SKILL 自带的确定性脚本（**清单以 checklist 各维度「自动化辅助」行为准，⛔ 不写成闭集**），**逐个按各自签名传参**（⛔ 入参各不相同，一把喂 round 目录会得到与被检对象无关的恒定结论——恒真的空门比没门更坏）：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  S={{AIDP_HOME}}/skills/auto-test-runner/scripts
  M=$(ls -d "docs/reports/${TARGET_VERSION}/AI测试报告/build-${BUILD}"/round-* 2>/dev/null \
      | sed 's|.*/round-||' | sort -n | tail -1)          # 本轮轮次号（取最大）
  RD="docs/reports/${TARGET_VERSION}/AI测试报告/build-${BUILD}/round-${M}"
  python3 $S/tasks_state.py scan "$RD/tasks.md" --json            # tasks.md 不得残留 [ ]/[>]
  python3 $S/check_layer_isolation.py {{AIDP_HOME}}/skills/auto-test-runner --json   # 维度 1：传 SKILL 根目录
  python3 $S/check_env_facts.py "$RD/env-facts.json" --json       # 环境取证：传 env-facts.json
  # ★ 维度 8 必跑：收窄 = 静默漏跑（用例不进 tasks.md，跑完仍全绿）
  python3 $S/tasks_state.py selftest --json
  ```
  再逐维度核；**只读，不改任何文件**
- 回传**精简结构化结果**：`[{dim, critical, status, na_kind, evidence}]`，不回传全文。
  - `critical` 取自清单里该维度/子核查的 `Critical` 标记本身（⛔ 不照命令端的名单填）；
  - `status ∈ pass|fail|na`；`na` 必填 `na_kind`——「本轮不核」分三类且互不等价，口径以清单为单一信源。
  - ⛔ **`status: na` 不得用于消化一条已核出的不通过**（标 N/A ≠ 豁免）。

**判定**：

- **清单中任一 Critical（含子核查）不通过 → 执行下方记账**，不以命令端固定名单代替 SKILL 标记：

  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell --command aiauto-test)"
  BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
  # ★ 本门专属 streak，⛔ 不与 3.2.5 / 3.2.6 共用；记账→判阈→四件套→#4 一次做完
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$V" \
    --phase 3.3-qr --reason audit-critical --streak-key qr_gate_fail_streak --threshold 3 \
    --why "质量检查清单 Critical 连续未过（详见本步输出）"
  ```

  未达阈 → **回 3bis 重取证/补跑后重来**（≤3 轮）；达阈按上式冻结并发 #4。通过时 `$BE --version "$V" del qr_gate_fail_streak`。**不得**在有 Critical 未过的情况下继续发 #F。
- 其余维度不通过 → 终端 `⚠️` 告警 + 写进报告「遗留风险」，不阻断。
- 子 Agent 派发失败 / 无法回传 → **转前台内联执行同一份清单**（降级但不跳过），并在报告里注明"质量检查以内联方式完成"。
