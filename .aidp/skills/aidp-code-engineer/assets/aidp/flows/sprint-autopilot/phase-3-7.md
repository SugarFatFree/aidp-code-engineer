# sprint-autopilot · Phase 3 详情分片 [7/13]（3.2.1 Step D 就绪探针 + 探针超时熔断）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 7/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.2.1（Step D 部署就绪探针 + 探针超时熔断）
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-7.md`。理据见同目录 `rationale.md`。

---

**Step D — 部署就绪探针（流水线成功 ≠ 可测；先等≥15 秒、按技术栈延长，启动就绪才算可测）**

> **★ 进入本 Step 前置判定**：读取当前 build 的 `change_classification`。若 `cicd_skipped=true` 且 `classification_error=false`，本 Step **不执行**，因为该 push 不触发远端部署；保留 push 成功与 `cicd_skipped` 留痕即可。分类缺失、分类命令失败或 `classification_error=true` 一律继续执行本 Step（fail-closed）。

CICD「成功」只代表**部署完成**（镜像发布 / 文件落盘），服务可能仍在启动（容器拉起 / 应用编译 / DB 连接池预热）。
- **★ 先等≥15 秒、按技术栈延长再探**：流水线报「成功」后服务未必立刻可连（容器拉起 / 应用编译 / DB 连接池预热），**最少等 15s**（`cicd_post_deploy_wait_seconds`，默认 15），并**按本项目后端技术栈的冷启动特性额外延长**——命令端探测 `code/backend/` 构建文件自动判定基线：**JVM 系（`pom.xml`/`build.gradle`，如 Spring Boot：JVM 预热 + 容器上下文 + 连接池预热较慢）取 30~45s**；Node（`package.json`）/ Python（`requirements.txt`/`pyproject.toml`）/ Go（`go.mod`）等较轻量取 20~25s；多服务并存取最重者。用户在 `cicd_post_deploy_wait_seconds` 显式填值则覆盖自动判定，但**下限恒为 15s**。本固定等待只是"别太早探"的下限，真正就绪仍由下方探针轮询判定。
- **⛔ 严禁用登录页可达性当就绪判据**：登录页很可能是**第三方登录页 / SSO**（与本应用不同源、本应用没起来它也照样 200），登录页能打开**不能**证明本应用已就绪。**有登录系统的应用必须以「登录成功后」的自身页面 / 自身鉴权接口为准。**
- **必须**通过下列就绪探针（HTTP 层探测，非浏览器——遵守 autopilot「不跑浏览器」边界，浏览器实测仍归 `/sprint-aiauto-test`）后才判定"可测"：
  - **情形① 应用有登录系统（`cloud_ready_requires_login: true`）**——主信号 = **登录成功 + 登录后自身接口取到数据**：
    - **★ 测试账号占位/未填的无人值守降级门（GAP 兜底，登录探针之前先判）**：`/loop` 无人值守下若账号文件 `研发自测/01_测试环境与账号.md` 的凭证仍是占位（含"请填写" / 空值）→ **绝不用假账号硬探、也不无限重试登录**：按契约写齐 `versions.{V}.needs_human=true` + `aiauto_frozen_at=@now` + `freeze_reason=account-missing` + 顶层 `aiauto_blocked_reason`（`needs_human_reason="测试账号未填，浏览器实测跳过"`），**开发/部署成果照常 finalize（本 build 报告按静态-only 收尾、浏览器实测延后）—— ⛔ 这不是一句描述，是**三步可执行清单**（照 `phase-3-9.md` 静态-only 收尾同款形态执行）：① `emit-report.py --kind exec` finalize 本 build 的 AI执行报告，`testSummary` **如实标注**「浏览器实测未执行（测试账号未填）」，⛔ **不填 0/0/0**（会被读成「测了且全挂」）；② 发 #3（携该结论 + 报告链接，必带 `#/build/{BUILD}` hash）；③ 游标 `run-state` **推进到 3.3-audit**，⛔ 不得停在 `3.2.1-probe`——停在探针前就进不了 3.3/3.4，build 铸了却永远停在骨架态，与本行自己写的「照常 finalize」相反**，发一次 #4（正文「测试账号未填 → 浏览器实测已跳过；补 `研发自测/01_测试环境与账号.md` 账号后等配置类自动解冻，或重挂测试 loop」），**不写 `last_deployed_at`**（不把登录不通的环境放进测试链路空转）、不阻塞 dev 主流程；本版随 `needs_human` 冻结（同失败处置 step 5，`/loop` 后续跳过、不刷屏）。**交互式调用**则照 Phase 0.5.5 用 `AskUserQuestion` 收集账号，不走本降级。
      - **★ 配置类冻结的自动解冻（区别于环境类只认新部署）**：`freeze_reason` 属**配置类**（`account-missing` / `account-invalid` / `testplan-incomplete` / `cicd-auto-trigger-off` / `config-missing`——问题在配置、凭证或 loop 挂载，不是环境起不来）时，Phase 0.3.4 候选筛选每 tick 额外**复检配置源**：前四者按**配置源 mtime**（账号文件 / 测试方案 / `memory/aidp-config.yaml`）晚于冻结时刻判，`config-missing`（测试链路未挂载）按**心跳** `aiauto_test_heartbeat_at` 判（补挂第二条 loop 不碰任何文件，mtime 判据对它恒假）→ 命中即**自动清 `needs_human` 重回候选重测**，无需等新部署、也无需人工 `retry`。环境类（枚举表「解冻类别=环境类」，含 `probe-timeout` / `cicd-unreachable` / `cicd-cli-unavailable` 等）走 0.3.4 的指数退避自动复探。枚举与解冻信号的权威表见 `/sprint-aiauto-test` `rationale.md`；⛔ **判据键恒为 `freeze_reason`**——`needs_human_reason` 是给人读的自由文本，拿它做分支判定必然匹配不到（写的人用中文、读的人用枚举）。
    1. **登录拿凭证**：`curl` POST **项目自身的登录接口** `cloud_ready_login_url`（**本应用实现的登录端点，非第三方登录页**）+ 测试账号（复用 `/sprint-aiauto-test` 维护的测试账号，读 `docs/testing/{version}/研发自测/01_测试环境与账号.md`，**不放 PRD**）→ 从响应体 / `Set-Cookie` 取鉴权凭证（token / cookie）。登录失败（拿不到凭证）= 应用未就绪 → 按 `cloud_ready_interval_seconds` 间隔重试。
    2. **登录后自身鉴权接口取数（刷新 2 次都正常）**：带上凭证访问 `cloud_ready_api_url`（**项目自身实现、需登录鉴权**的取数接口，非第三方、非匿名公开；健康端点只作前置必要条件，不能替代它）——要求**连续 2 次**都 HTTP `200` 且响应体确实**含数据**（`cloud_ready_api_expect`：非空 JSON / 含预期字段，如 `"code":"0"` 或 `data` 数组非空）。首次失败属"启动中"正常现象 → 按间隔重试直到连续 2 次成功或超 `cloud_ready_timeout_seconds`。
    3. **（可选）登录后页面**：若配 `cloud_ready_page_url` 为**登录后**自身首页 / 受保护页（非登录页）→ 带凭证刷新 2 次校验含 `cloud_ready_page_marker`；纯前后端分离项目可只靠步骤 2 的接口信号。
    - **★ HTTP 登录不可脚本化时**（纯第三方 SSO 跳转 / 验证码，无可 `curl` 的自身登录端点）→ **绝不退回用登录页可达性蒙混**；改为：autopilot 仅在「流水线成功 + 等 10s」后**暂记部署完成**，把"登录后就绪确认"**显式交给 `/sprint-aiauto-test` 首次登录**（其登录成功即真正就绪门），并在 #1d 通知标注「就绪以测试链路首次登录为准」。
  - **情形② 应用无登录系统（`cloud_ready_requires_login: false`）**——主信号 = **后端健康端点 UP**，配了 `cloud_ready_api_url`（自身公开取数接口）时再要求连续 2 次 HTTP `200` + 含数据。
  - **★ 情形③ 前端产物特征探针（`deploy_ends.frontend` 已声明且 `trigger != none` 且 `ready_asset_probe.must_contain` 非空时**必跑**——堵"半截部署：后端更新了、前端产物没换"）**：后端就绪信号（情形①/②）只证明**后端**起来了，**证明不了前端跑的是新版本**。`curl` 抓 `ready_asset_probe.url` 首页 HTML → 提取其引用的主 JS/CSS 资源（`<script src=.../assets/index-*.js>` 等）→ `curl` 拉该主资源 → **grep `must_contain[]` 的每个本次特征串**（本轮新增的占位文案 / 新配置接口路径 / 新路由 slug 等**可判定**串）。**全部命中**才算前端已部署新版本；**任一缺失** = 前端产物仍是旧版（构建未跑 / 发布到别处 / CDN 缓存）→ **不写 `last_deployed_at`**（不放行测试链路对半截部署空转），走「失败处置」#4（正文「前端产物特征探针未命中：首页主资源不含本次特征串 {缺失串}，疑似前端未部署 / 发布了旧产物」）。**命中 → 写 baseline `versions.{V}.builds[current_build].frontend_deploy_verified=true`**（供 ceremony-gate 3e 校半截部署）。`must_contain` 为空（本轮无可判定前端特征）→ 跳过本探针但 #1d/终端 WARN「前端产物特征探针跳过（未提供特征串），无法确认前端是否部署新版本」。
- **通过**（情形①：登录成功 + 登录后接口连续 2 次取到数据；情形②：公开接口连续 2 次取到数据；**情形③：前端已声明部署则前端产物特征探针一并命中**）→ 先写当前 build 的 `builds[].probe_passed=true`、`probe_at=@now`、`probe_commit=$GIT_PUSH_COMMIT`，再写 baseline `versions.{V}.last_deployed_at`（= 部署就绪、可测信号，aiauto-test 读它触发浏览器实测）+ `phase_beta_done_at`，发 #1d 部署完成通知（正文标注「CICD 流水线已成功 + 部署就绪探针通过：登录后自身接口连续 2 次取到数据〔+ 前端产物特征探针命中〕」）。
  **★ 探针轮询 = `autopilot-deploy-watch.py`（单一实现，⛔ 不在分片里手写轮询循环）**：它内置冷启动容忍、
  health 必要判据（HTML 兜底页不认）、`--auth-url` 连续 2 次取到非空数据、总超时与**单次调用上限**
  （`--max-seconds 480`，适配 Bash 工具时限；到时未就绪 rc=4 = 未探完，下 tick 续探、不记失败）。
  情形① 由执行体先按步骤 1 登录拿到凭证，以 `--auth-header` 传入；情形③ 前端特征探针在脚本 rc=0 后另跑。

  ```bash
  # ⛔ 分片间 shell 变量不持久：必须在本分片就地取回
  eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell)"
  BE="python3 .aidp/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"; mkdir -p memory/.aidp
  HEALTH_URL="<后端健康端点，无则留空>"
  AUTH_HEADER="<情形① 登录拿到的凭证头，如 'Authorization: Bearer …'；情形② 留空>"
  COLD="<Step D 开头按技术栈判定的冷启动等待秒数，下限 15>"
  # ★ 跨 tick 续探：冷启动窗口与总超时从「首次探测时刻」起算（首次写入，就绪 / 判超时后删除）
  PSA=$($BE --version "$V" get probe_started_at --default "")
  [ -n "$PSA" ] || { $BE --version "$V" set probe_started_at @now; PSA=$($BE --version "$V" get probe_started_at --default ""); }
  ARGS=(--version "$V" --timeout "${CLOUD_READY_TIMEOUT:-600}" --interval "${CLOUD_READY_INTERVAL:-15}" \
        --since "$PSA" --max-seconds 480 --cold-start-seconds "$COLD" --no-write)   # 就绪信号统一由下方落盘块写（情形③ 通过后）
  [ -n "$HEALTH_URL" ] && ARGS+=(--health-url "$HEALTH_URL")
  [ -n "${CLOUD_READY_URL:-}" ] && ARGS+=(--auth-url "$CLOUD_READY_URL")
  [ -n "$AUTH_HEADER" ] && ARGS+=(--auth-header "$AUTH_HEADER")
  python3 .aidp/scripts/autopilot-deploy-watch.py "${ARGS[@]}" > memory/.aidp/deploy-watch.json
  DRC=$?; cat memory/.aidp/deploy-watch.json
  TF="python3 .aidp/scripts/autopilot_tick_flags.py set --command autopilot PROBE_PASSED"
  case "$DRC" in
    0) $BE --version "$V" del push_probe_fail_streak probe_started_at || true ;;   # 就绪 → 情形③（如适用）→ 下方落盘
    4) $TF 0; echo "⏳ 就绪探针本次调用时限内未探完 → 游标留 3.2.1-probe，下 tick 续探（不记失败）"; exit 0 ;;
    5) $TF 0; echo "⚠️ 已就绪但写 last_deployed_at 失败 → 下 tick 原地重试，⛔ 不计 streak、不冻结"; exit 0 ;;
    *) $TF 0; $BE --version "$V" del probe_started_at || true   # 本轮探测结束，下次重新计时
       # rc=2 超时 / rc=3 探针参数缺失：部署成功但未就绪；⛔ 不写 last_deployed_at（不把不通的环境放进测试链路）
       python3 .aidp/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "${BUILD:-}" \
         --phase 3.2.1-probe --reason probe-timeout --streak-key push_probe_fail_streak --threshold 3 \
         --why "就绪探针未通过（rc=$DRC）：登录失败 / 登录后接口未返回数据 / 探针 URL 未配置"
       exit 0 ;;
  esac
  ```

  **★ 判定当场落盘结论（不可省，下方出口靠它推进游标）**：
  ```bash
  eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell)"
  python3 .aidp/scripts/autopilot_tick_flags.py set --command autopilot PROBE_PASSED 1
  # ⛔ 以下三个字段是**跨链路交接信号**，必须落成可执行语句（散文从句不算写入）：
  #    读侧恒空时，测试链路每 tick 选不出版本、静默 exit 0，而开发链路因心跳还在而判
  #    "测试链路健康"，两条 loop 都在刷屏、什么都没测，最后冻结在错误的原因上。
  BE="python3 .aidp/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
  # ⛔ `GIT_PUSH_COMMIT` 赋在 phase-3-5b 推送围栏、跨不过 Bash 调用：取空会让出口判据
  #    `PROBE_COMMIT == PUSH_COMMIT` 恒不等、游标卡在 3.2.1-probe，故从 baseline 读回。
  [ -n "${GIT_PUSH_COMMIT:-}" ] || GIT_PUSH_COMMIT=$([ -n "${BUILD:-}" ] && $BE --build "$BUILD" get push_commit --default "" || echo "")
  [ -n "${BUILD:-}" ] && $BE --build "$BUILD" set probe_passed true probe_at @now \
      probe_commit "${GIT_PUSH_COMMIT:-}"
  # ★ 情形③（前端产物特征探针命中）必须**可执行地**写 frontend_deploy_verified，
  #   否则 gate 3e「部署覆盖度」对任何动过前端的 build 恒 FAIL（见 rationale.md）。
  #   FE_PROBE_OK 由执行体按情形③实测结果就地代入（同 IS_LOOP_CONTEXT 范式）。
  FE_PROBE_OK=0   # ← 情形③前端产物特征探针命中则改为 1
  [ "$FE_PROBE_OK" = "1" ] && [ -n "${BUILD:-}" ] \
    && $BE --build "$BUILD" set frontend_deploy_verified true
  $BE set last_deployed_at @now phase_beta_done_at @now
  # 新部署完成 = 自动修复闭环的「修复 + 重部署」已落地 → 清进行中标记，测试链路据此对新部署复测
  $BE del auto_fix_in_progress_since || true
  # 本轮 autopilot 推到的 HEAD：retest-cap 的"人工修复"判别靠它与 retest_frozen_head 双重不等；
  # 恒空则第二个不等式恒真 → 自动解冻 → 3 轮上限退化为无限自动复测。
  python3 .aidp/scripts/baseline_edit.py set last_autopilot_head "$(git rev-parse HEAD)"
  ```
- **超 `cloud_ready_timeout_seconds` 仍未通过**（脚本 rc=2）→ 部署成功但服务未就绪 / 登录不通（与"流水线失败"不同，重跑流水线通常无济于事）→ 上方代码块已按 `push_probe_fail_streak` 记账（连续 3 次冻结 `probe-timeout`，环境类自动复探），**不写 `last_deployed_at`**；`PROBE_PASSED=0` 已当场落盘。
- **情形③ 前端特征探针未命中**（脚本 rc=0 之后）→ 同样调 `autopilot_fail_handle.py --reason probe-timeout --streak-key push_probe_fail_streak --threshold 3`（正文写明缺失的特征串），`PROBE_PASSED=0`，⛔ 不执行下方「判定当场落盘结论」。


---

## ⛳ 本 Phase 出口：`run_state` 写盘（Step D 自己的出口，不可省）

> ⛔ **为什么 Step D 必须有独立出口**：上一分片 `phase-3-6.md`（Step A–C）出口写的是 `next=3.2.1-probe`，就绪探针要靠**本片**把它推进到 `3.3-audit`。本片若不写盘，游标会永远停在 `3.2.1-probe`：探针明明过了，下一 tick 仍从头重探，`last_deployed_at` 反复重写、Phase 3.3 永不开始。（`invariants.md`「阶段推进不变式」：只在 `invariants` 里描述 `run_state` 而分片不写盘 = 状态机不存在。）

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
BE="python3 .aidp/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
# ★ 读回上文当场落盘的探针结论。⛔ 绝不能直接读 shell 变量 `$PROBE_PASSED`：本段与上文
#   探针判定分属**不同 Bash 工具调用**，shell state 不跨调用持久 —— ⛔ 这里不得写成
#   `${PROBE_PASSED:-0}`，而全仓无人给它赋值 → 恒取 0 → 恒走 else → 探针明明过了游标也
#   永远停在 `3.2.1-probe`，下 tick 从头重探、`last_deployed_at` 反复重写，Phase 3.3/3.4
#   永不开始、build 永不收口，最后只能靠通用 stuck 熔断（8 tick + 滞留 2h）冻结待人。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
# 事实兜底：只认当前 build 的显式探针证据，禁止用版本级 last_deployed_at 反推。
#   —— 旧版本的部署时间戳不能证明本 build 已就绪，否则失败/未探测的新部署会被放行。
BUILD=$($BE --version "$V" get current_build --default "")
if [ -z "$PROBE_PASSED" ] && [ -n "$BUILD" ]; then
  PROBE_PASSED=$($BE --version "$V" --build "$BUILD" get probe_passed --default "0")
  PROBE_COMMIT=$($BE --version "$V" --build "$BUILD" get probe_commit --default "")
  PUSH_COMMIT=$($BE --version "$V" --build "$BUILD" get push_commit --default "")
  # ⛔ 运算符优先级：`[ A ] || [ B ] && C` 在 shell 里结合为 `(A || B) && C` ——
  #    写成一行时 PUSH_COMMIT 为空即无条件把 PROBE_PASSED 清 0。必须用显式 if。
  if [ -z "$PUSH_COMMIT" ] || [ "$PROBE_COMMIT" != "$PUSH_COMMIT" ]; then
    PROBE_PASSED=0
  fi
fi
# ★ 值域归一：写侧是 `set probe_passed true`（存 JSON 真值，读回打印字符串 `true`），
#   而下方判据比的是 `= "1"` —— 不归一则**恒假**，游标永远留在 3.2.1-probe、
#   Phase 3.3/3.4 永不开始（同围栏的 cicd_skipped 用的就是 `= "true"`，本处曾是单点漏改）。
case "${PROBE_PASSED:-0}" in true|True|TRUE|1) PROBE_PASSED=1 ;; *) PROBE_PASSED=0 ;; esac
# ★ 本 push 无正式代码变更（cicd_skipped）时【没有部署要等、也没有探针会跑】——
#   必须直接把游标推到 3.3-audit。否则探针恒 0 → 恒走 else → 游标永远留在 3.2.1-probe，
#   下 tick 重来一遍，last_deployed_at 永不写、Phase 3.3/3.4 永不开始，最后只能靠通用
#   stuck 熔断（8 tick + 滞留 2h）冻结待人 —— 一次纯文档提交就能让整版停摆。
BUILD_CS=$($BE --version "$V" get current_build --default "")
CICD_SKIPPED=$([ -n "$BUILD_CS" ] && $BE --version "$V" --build "$BUILD_CS" get cicd_skipped --default "" || echo "")
CLS_ERR=$([ -n "$BUILD_CS" ] && $BE --version "$V" --build "$BUILD_CS" get classification_error --default "" || echo "")
if [ "$CICD_SKIPPED" = "true" ] && [ "$CLS_ERR" != "true" ]; then
  $BE --version "$V" run-state "3.2.1-probe" "3.3-audit" "done" \
    --summary "本 push 无正式代码变更（cicd_skipped），无部署可探，直接进 Phase 3.3" --pending ""
elif [ "${PROBE_PASSED:-0}" = "1" ]; then
  # 探针通过：last_deployed_at 已在上文写入，可以进审计
  $BE --version "$V" run-state "3.2.1-probe" "3.3-audit" "done" \
    --summary "Step D 就绪探针通过（last_deployed_at 已写），进 Phase 3.3" --pending ""
else
  # 未通过（超时让位 / 本 tick 未探完）：游标留在本步，下 tick 继续探
  $BE --version "$V" run-state "3.2.1-probe" "3.2.1-probe" "done" \
    --summary "Step D 就绪探针未通过（超时或本 tick 未探完），下 tick 续探" --pending "deploy-probe"
fi
```

- **探针超时熔断**（上文已置 `needs_human` / `freeze_reason=probe-timeout`）时同样走 `else` 分支写盘——冻结与游标各司其职：冻结决定「还选不选这个版本」，游标决定「选中后从哪一步继续」，二者都要落。
