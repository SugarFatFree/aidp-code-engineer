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

### 3.0 ★ 双路汇合门（已部署 build 的所有入口均生成报告）

新调用先按 `phase-2-unit.md` 固定 version/build/commit，再接收两路终态。**本阶段只有主协调者执行**。standalone、纯后端、浏览器工具不可用同样生成 AI测试报告；`REPORT_ENABLED` 仅决定是否存在 autopilot AI执行报告及仪式台账，不能取消测试报告。沿用 Phase 2 冻结的 `$BUILD`，本阶段不得重读最新 `current_build` 替换它。

实测子 Agent 把真实结果写到 `docs/reports/{V}/AI测试报告/.build-input-{BUILD}.json`。没有可执行浏览器面写 `browserTests:{status:"N/A",reason:"..."}`；未启动/工具或账号阻塞写 `UNVERIFIED`，预算耗尽写 `TIMEOUT`，尚在执行写 `RUNNING`（均须非空 reason）。没有执行用例时 `cases:[]`，summary 的真实计数为 0、passRate 为 null；不得补假用例或占位截图。已有真实执行结果仍保留逐条事实。单测结果路径固定为 `memory/.aidp/build-unit/{V}/{BUILD}/result.json`（或 Phase 2 主协调保存的同身份副本）。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
: "${TARGET_VERSION:?}" "${BUILD:?需要 Phase 2 固定的已部署 build}"
SKIP_REPORT=0
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test SKIP_REPORT 0
python3 - "$TARGET_VERSION" "$BUILD" <<'JOIN_WAIT'
import json, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from build_unit_test import read_status
v, b = sys.argv[1:]
unit = read_status(Path.cwd(), v, b)
p = Path(f"docs/reports/{v}/AI测试报告/.build-input-{b}.json")
if not p.exists():
    raise SystemExit("实测分支尚未交付 payload；继续等待，不 finalize")
data = json.loads(p.read_text(encoding="utf-8"))
if data.get("build") != b:
    raise SystemExit("实测 payload build 不匹配，拒绝串入其它 build")
if (unit.get("status") == "RUNNING" or (data.get("browserTests") or {}).get("status") == "RUNNING"
        or (data.get("summary") or {}).get("pendingBrowserTest")):
    raise SystemExit("至少一路仍 RUNNING；保留游标并让位，不能收尾或登记失败")
if unit.get("commit"):
    snapshot = Path(f"memory/{v}/aiauto-unit-{b}.json")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(unit, ensure_ascii=False), encoding="utf-8")
print("两路已终止或超时；继续生成合并报告，终态不等于通过")
JOIN_WAIT
```

上块未通过时止于汇合等待，**不进入以下任何产物/通知/finalize 步骤**，不 bump/freeze；有唤醒源留待下一 tick，没有唤醒源则报告仍在运行并返回。结果文件缺失时后续 `emit --unit-result` 会记未核验，不能编 PASS。存量无单测任务的历史报告继续读取兼容，但新命令不能走下面旧的 standalone 不产报告规则。

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
BTR="docs/reports/${TARGET_VERSION}/AI测试报告"
BROWSER_EMPTY_TERMINAL=$(python3 - "$BTR/.build-input-$BUILD.json" "$BTR/build-$BUILD" <<'BROWSER_EMPTY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
state = (d.get("browserTests") or {}).get("status")
print(int(state in ("N/A", "UNVERIFIED", "TIMEOUT") and not list(Path(sys.argv[2]).glob("round-*/results/*.json"))))
BROWSER_EMPTY
)
if [ "${SKIP_REPORT:-0}" = "1" ] || [ "$BROWSER_EMPTY_TERMINAL" = "1" ]; then
  echo "无浏览器执行结果：保留明确 N/A/未核验/超时说明，跳过不适用截图义务；继续合并单测报告"
else
BTR="docs/reports/${TARGET_VERSION}/AI测试报告"
SHOT_DIR="${BTR}/screenshots/${BUILD}"
mkdir -p "$SHOT_DIR"

if [ -f {{AIDP_HOME}}/skills/auto-test-runner/scripts/check_result.py ]; then
  CR_WEBMCP=""
  CR_CLIENT_JSON=$(python3 {{AIDP_HOME}}/scripts/check_client_mcp.py --version "${TARGET_VERSION:?}" --detect --json); CR_CLIENT_EXIT=$?
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
print(len([i for i in (d.get('issues') or []) if i.get('level')=='Critical']))" 2>/dev/null || echo -1)   # 阻断只看 level=='Critical'（SKILL 单一信源）
  if [ "$CR_EXIT" -ge 2 ] || [ "${CR_BLOCKING:-0}" != "0" ]; then
      echo "❌ 执行结果不合 auto-test-runner 结果契约（阻断项 ${CR_BLOCKING} 条）→ 在报告标「证据形状不合契约」"
      SHAPE_BAD=1
  fi
else
  # SKILL 缺 check_result.py = 安装残缺：不得继续往下清空/覆盖已归集截图，按证据形状不合处理
  echo "❌ 缺 auto-test-runner/scripts/check_result.py（SKILL 安装残缺）→ 在报告标「证据形状不合契约」"
  SHAPE_BAD=1
fi

# ① 归集：消费 check_result.py --json 的 artifacts（已解析且确认归属本轮 evidence；`SHAPE_BAD=1`——退出码≥2、存在 Critical 或 check_result.py 缺失——不消费，改由下方非空核验门拦截）
CR_JSON="${CR_JSON:-}" python3 - "$SHOT_DIR" "${SHAPE_BAD:-0}" <<'SHOTS'
import json, os, re, shutil, sys
from pathlib import Path
dest, shape_bad = Path(sys.argv[1]), sys.argv[2] == "1"
if shape_bad:
    sys.exit(0)   # 结果契约不合：上游明确不应消费 artifacts，缺图交给非空核验门判定
EXTS = {".webp", ".png", ".jpg", ".jpeg"}
try:
    shots = [a for a in (json.loads(os.environ.get("CR_JSON") or "{}").get("artifacts") or []) if a.get("kind") == "screenshot"]
except ValueError:
    shots = []
def round_no(item):   # artifacts 按 round-* 目录的字符串序给出（round-10 在 round-2 前），必须按数字序重排，保证新轮覆盖旧轮
    found = re.search(r"/round-(\d+)/", item.get("path", "").replace(os.sep, "/"))
    return int(found.group(1)) if found else -1
for old in dest.iterdir():
    if old.is_file() and old.suffix.lower() in EXTS:
        old.unlink()
for item in sorted(shots, key=round_no):
    source = Path(item["path"])
    if not source.is_file():
        continue
    for old in dest.iterdir():
        if old.stem == source.stem and old.suffix.lower() in EXTS:
            old.unlink()   # 同主干格式变更不留旧图
    shutil.copy2(source, dest / source.name)
SHOTS

python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del shot_gate_fail_streak || true
fi   # ← SKIP_REPORT 守卫结束
```

继续 3.2.5bis 质量检查，再进 3.2.6 生成 HTML。已进入 UI 且具有 capture 义务的用例缺图，按 SKILL 的证据契约记执行缺陷；前置 block 使用实际探测证据，不要求占位截图。`SHAPE_BAD=1`、质量检查 Critical 或 block 结果都不能宣称通过；报告必须保留真实失败原因。


### 3.2.5bis ★ 派 SKILL 的 8 维度独立质量检查子 Agent（Critical 门）

> **对实际执行的实测 round 必须派独立子 Agent，主流程不得直接内联或跳过**；仅派发失败时按下文降级。`tasks_state.py scan` 必须在报告生成前跑到。若 3.2.5 已核实明确 `N/A/UNVERIFIED/TIMEOUT` 且根本没有实测 results/round，本步无浏览器产物可审，记「浏览器质量检查不适用/未执行」后直接进 3.2.6；不伪造 tasks/env-facts/screenshots，不把单测交给浏览器质量门。存在实际 round 时仍完整执行原 Critical 门。
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
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$V" \
    --phase 3.3-qr --reason audit-critical --streak-key qr_gate_fail_streak --threshold 3 \
    --why "质量检查清单 Critical 连续未过（详见本步输出）"
  ```

  未达阈 → **回 3bis 重取证/补跑后重来**（≤3 轮）；达阈按上式冻结并发 #4。通过时 `$BE --version "$V" del qr_gate_fail_streak`。**不得**在有 Critical 未过的情况下继续发 #F。
- 其余维度不通过 → 终端 `⚠️` 告警 + 写进报告「遗留风险」，不阻断。
- 子 Agent 派发失败 / 无法回传 → **转前台内联执行同一份清单**（降级但不跳过），并在报告里注明"质量检查以内联方式完成"。
