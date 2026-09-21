> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-1.md`。理据见同目录 `rationale.md`。

# sprint-aiauto-test · Phase 1 详情（部署完成探测 1.1–1.3）

## Phase 1：部署完成探测

### 1.1 探测策略（按 deployment.mode 分流）

| mode | 探测方式 |
|------|--------|
| `local` | `curl -s -m 3 $LOCAL_FRONTEND_URL` 直到 200，最长 `local_ready_wait_seconds`（默认 30s）；超时 → **统一走下方 1.2 `probe_fail_streak` 熔断**（首条 #4 话术可含「local dev server 未启动？请检查 sprint-autopilot 是否完成 Phase 3 部署阶段」，但**不走独立分支**——同 cloud 一样累加 streak、达阈值即冻结，避免 `/loop` 下每 tick 重探 + @用户刷屏）。⚠️ **local 模式的 dev server 生命周期绑 autopilot 当前 tick**（tick 退出即可能被回收）；跨 tick 的 7×24 无人值守**推荐 `cloud`（CICD 常驻部署）**，`local` 更适合单次 `--once` |
| `cloud` + 配 `cloud_deploy_check_url` | `curl -s -m 3 $CLOUD_DEPLOY_CHECK_URL` 直到 200，间隔 10s，最长 `cloud_deploy_check_timeout_seconds`（默认 900s） |
| `cloud` 无 check_url | 直接探测 `$CLOUD_DEPLOY_URL` 首页是否 200 |
| `none` | Phase 0 已退出，不会到这里 |

> ⛔ **就绪判据统一（对齐 sprint-autopilot Phase 3.2.1 Step D「部署完成 ≠ 可测」）**：上表 `curl … 200` **仅对无登录系统的应用**足够。**有登录系统的应用**——**首页/check_url 返回 200 不代表应用就绪**（登录页常是第三方/SSO，应用没起来也照样 200，即"可达性即就绪"陷阱）：`REQUIRES_LOGIN=true` 时，探测**必须以「登录成功后、自身鉴权接口连续 2 次正常取到数据」为就绪判据**（与 CICD 部署路径同一标准），而非纯首页 200。此判据对 `local` / `cloud` 全部 trigger（git-push / manual-script / ci-pipeline / github-actions）一致适用，堵住"未就绪即放行浏览器测试"的空档。

### 1.2 探测失败处置

- 探测超时 → 里程碑通知 #4（`notify.py --auto`，模板规则见 sprint-autopilot 0.1bis）：
  ```
  ⏰ {项目名称} {TARGET_VERSION} · 部署探测超时      ← 标题（按 0.1bis 固定前缀，必带项目中文名称）
  目标 URL：https://uat.example.com/health
  等待时长：900s
  可能原因：CI 流水线未跑完 / 部署失败 / 网络问题
  📌 选项：① 回复 "retry" 再探 300s ② 回复 "skip" 跳过本轮 ③ 回复 "abort" 终止
  ```
  - **交互式**（`LOOP_UNATTENDED=0`）→ 发 #4 后监听用户回复（同失败处置）。
  - **★ `/loop` 无人值守**（`LOOP_UNATTENDED=1`）→ 无人可答：**一次调用做完「记账 → 判阈 → 冻结四件套 → 发 #4」**，随后走 `UNATTENDED_YIELD` 退出本 tick、不轮询。⛔ 散文的「+1」「置 needs_human」「发 #4」**都不是**写入/发送——逐处手抄必漏其一：漏 bump 则阈值永不达（每 tick 重探 900s + 刷 #4），漏 #4 则「停得住但停不响」（一条通知都没有）：

    ```bash
    eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "${TARGET_VERSION:?}" \
      --phase 1-probe --reason probe-timeout --streak-key probe_fail_streak --threshold 3 \
      --why "连续多轮部署探测超时、疑似环境未就绪，暂停本版自动重探待人工介入"
    RC=$?   # 0=已记账、让位本 tick（下轮仍重探）｜3=已达阈或无唤醒源→已冻结本版｜2=入参错，⛔ 什么都没写
    ```

    `RC=3` 即**冻结本版测试**：后续 `/loop` 唤起跳过 `needs_human=true` 的版本（一行日志、不再重探、不再刷 #4）。解冻靠 `last_deployed_at` 刷新（新部署）或人工 `retry`/`--reset-baseline`。
- 探测成功 → **可执行地**清零后进 Phase 2（与上面的 bump 对称——散文的「清零」同样不是写入；只增不减的计数器会把偶发抖动累成"连续 3 轮超时"并按 `probe-timeout` 冻结，而告警文案与事实不符）：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell --command aiauto-test)"
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del probe_fail_streak 2>/dev/null || true
  ```

### 1.3 ★ 里程碑通知 #D（部署完成-开始自动化测试，模板规则见 sprint-autopilot 0.1bis）

> 经 `python3 {{AIDP_HOME}}/scripts/notify.py --auto` 发送（渠道取 `memory/aidp-config.yaml` 的 `notify.channels`；含公共字段 项目名称 / 工作目录 / **时间——#D 属开始类通知（测试开始语义），标签用「开始时间」，见 sprint-autopilot 0.1bis「时间字段标签分层」，⛔ 不用「完成时间」**）。`notify.enabled=false`（`NOTIFY_ENABLED=0`）或 `notify.py` 退出码 3（未配置任何渠道）时静默跳过，⛔ 不弹窗问人。

（**首行 = 通知标题 `notify.py --title`，按 0.1bis「通知标题固定前缀」必带项目中文名称**；其余为正文）

```
✅ {项目名称} {TARGET_VERSION}_Build{N} · 部署完成 · 开始自动化测试      ← 标题
版本：{TARGET_VERSION}
部署模式：cloud / URL：https://uat.example.com
渲染模式：无头(--headless=new) | 有头　驱动：cli(本地) | mcp-remote(远程) | mcp-plugin-fallback(本机插件降级)
等待时长：实际 N 秒（预估 300s）
测试范围：主集 {N} 例（正式用例/ {X} 份，测试人员方案）+ 补集 {K} 例（研发自测/ 查漏）= 共 {N+K} 例
　　　　（正式用例/ 为空时写「研发自测 {Z} 例（正式用例/ 为空，兜底）」；★ 按 sprint-autopilot 0.1bis「通知内「AI 自动化测试范围」标注规则」+「对称计数铁律」——主集必须点算用例条目数，不报份数）
将开始测试：role=all + login=enabled
```

> ⚠️ **#D 在 Phase 1（早于 Phase 2.0/2.1 用例解析）**：`{N}`（主集用例条数）需就地扫 `docs/testing/{version}/正式用例/` 用例文件**点算条目**（表格行 / `T-NNN` / 用例标题），`{K}` 扫 `研发自测/`；不得用「份数」顶替「例数」。详见 0.1bis 对称计数铁律。

