# sprint-aiauto-test · Phase 0 详情分片 [9/9]（0.1.6 WebMCP 驱动就绪 — ★ 可选，未启用整段跳过）

> 本文件是 `/sprint-aiauto-test` 命令 **Phase 0** 详情的**第 9/9 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.1.6（WebMCP 启用判定 + 入参供给 + 驱动就绪委派）
> - **同 Phase 其它分片**：`phase-0-1.md` … `phase-0-7.md`（含 `phase-0-6b.md`）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 0.1.6 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-8.md`。理据见同目录 `rationale.md`。

---

### 0.1.6 ★ WebMCP 驱动就绪（可选能力；未启用 = 整段跳过，不留任何痕迹）

> ⛔ **本片只写「命令端该做什么」，不复述 SKILL 规则（约定 21）。**
> 驱动版本要求 / 两个浏览器开关怎么传 / origin 三段精确匹配 / 连接后两行自检 /
> `getTools` 与 `executeTool` 的调用约定 / 与 CDP 的分工 / `invoke` 能力归属 / 报告纪律——
> **单一信源 = `auto-test-runner` 的 `references/driver-web-webmcp.md`**，由执行子 Agent 自行 Read。
> 命令端**只做三件事**：判启用 → 传入参 → 委派预检。
>
> **Why 不在这里抄一份**：抄了就有两份会各自演进的调用约定，而规范本身还在变
> （能力入口的挂载位置已经迁移过一次）。上游改了、本片不跟，执行体就照着旧的做——
> 这正是本仓反复在修的漂移形态。

#### 步骤 1：启用判定（本步的第一动作，判定为否就没有后面所有步骤）

```bash
python3 {{AIDP_HOME}}/scripts/check_webmcp.py --detect --json
# → {"enabled": true|false, "entry_symbols": [...], "symbols_source": "..."}
```

| 判定 | 行为 |
| :- | :- |
| **`enabled: false`（默认，绝大多数项目）** | **整个 0.1.6 跳过**。⛔ 不打印、不 WARN、不写 run-context、不建任何产物位、不影响任何硬门——与本能力上线前**逐字节一致** |
| `enabled: true` | 继续步骤 2 |

> ⛔ **判定权归命令端，且只有这一个实现**。`auto-test-runner` 与其余三个 SKILL 都**明令不自行探测**
> （判定散落多处必然漂移，一处判错就给未启用项目凭空长出 block 项与报告位）。
> 所以**这里不判，就没有别人会判**。同样，⛔ 不要自己 grep PRD 顶替这条命令。

#### 步骤 2：把入参传下去（★ 不传 = 上游整块能力永不启用）

启用时，`webmcp_enabled` 与 `webmcp_entry_symbols` 必须进入两个地方：

1. **run-context**（Phase 2.0.5 组装时写入）—— 执行子 Agent 从这里读；
2. **派测试执行子 Agent 的 prompt** —— 点明本轮启用了 WebMCP，令其额外 Read `driver-web-webmcp.md`。

⚠️ **`webmcp_entry_symbols` 不可省略、也不可写死**：挂载位置已迁移过一次、规范仍在演进，
上游在缺该入参时**直接报入参错（exit 2）而不是猜默认值**——猜错的方向是「扫不到 → 0 命中 → 假绿」。
把 `--detect` 返回的数组**原样**传下去即可。

> 📌 `symbols_source` 若显示"内置默认"，说明项目没在 PRD 里声明 `entry_symbols`、用的是可能过期的
> 兜底清单。**这不阻断**，但值得在报告里提一句，便于日后规范再变时定位。

#### 步骤 3：驱动版本预检（委派上游探测器，不自己写探测）

```bash
python3 {{AIDP_HOME}}/skills/auto-test-runner/scripts/detect_drivers.py web --webmcp --json
```

- ⚠️ **端类型是【位置参数】不是 `--client` 选项**（`detect_drivers.py web`）——写成 `--client web` <!-- flag-check: ignore 反面教材，非真旗标引用 -->
  会被 argparse 判 `unrecognized arguments` 直接退出、拿不到任何输出。上游 `driver-web.md` 专门
  点名过这个错法，说明它是高频误写。
- ⛔ **不传 `--webmcp` 就没有 `webmcp` 段**（上游刻意设计：未启用时结果里连字段都不占）。
- 版本不足 / 取不到 → 由 SKILL 标 `block(webmcp-driver-too-old)` / `block(webmcp-driver-version-unknown)`，
  相关用例 block、**其余用例照跑**。⛔ **版本校验不影响退出码**（版本不足 ≠ 驱动缺失），
  命令端**不得**据此终止整轮，更**不得静默降级为「就当没有 WebMCP」**——
  那会让这一整类用例**全绿式消失**、报告看不出漏测。
- ⛔ 命令端**不要**自己 `npm ls` 判版本：判据在上游探测器里，两处各写一套必然漂移。

#### 步骤 4：带参浏览器启动命令的取用（AIDP 特有落点）

完整启动命令取自 `docs/testing/{version}/研发自测/01_测试环境与账号.md` 的「WebMCP 带参浏览器」段
（由 `/sprint-selftest` Step 3 产出，启用后为必填段；机器回检 = `check_webmcp.py` 的 `testenv-section`）。

- 该段缺失 → 标 `block(env-unavailable)`（⛔ **只能用 SKILL `BLOCK_REASON_ENUM` 内的裸枚举值**——自造值会被 `check_result.py` 判 Critical `bad_block_reason`，且 `gen_report` 把这条**纯环境阻塞计成产品缺陷**；「启动命令未登记」写进 `error`/`note`） + 在报告写明"启动命令未登记"，
  **⛔ 不即兴自拟命令**——自拟命令跑通了也无法复现，等于把配置藏进一次性会话里。
- 参数为何必须带、origin 怎么对齐、两行自检怎么读，**全见 `driver-web-webmcp.md`**，本处不复述。

#### 步骤 5：写入 run-context

追加：WebMCP 启用来源（`source`）、`entry_symbols` 与其来源、驱动版本预检结果、`webmcp_launch_command` = **完整命令字符串**（原样传，⛔ 不传「取用位置」、不改写、不自拟）。
报告侧的达成路径标注纪律见 `driver-web-webmcp.md`「七、报告纪律」。

---

> **收口**：0.1.6 跑完（或因未启用整段跳过）→ 回到 Phase 0 骨架表继续 0.2。
