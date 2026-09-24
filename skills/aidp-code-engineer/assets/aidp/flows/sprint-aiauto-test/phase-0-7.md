<!-- 二次切分 · phase-0 片7/9：覆盖 0.3 部署+测试元数据 / 0.4 测试账号加载-->
# /sprint-aiauto-test · 执行分片 分片 [7/9]（0.3 部署+测试元数据 / 0.4 测试账号加载）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-7.md`。理据见同目录 `rationale.md`。

### 0.3 部署 + 测试元数据（研发自测/ 配置优先 → PRD deployment 段兜底）

**URL 取值优先级**：
1. **`versions.{V}.testplan_deploy_url`**（Phase 0.0.5 从 研发自测/ 配置读到、**已落盘**的测试环境 URL）— 非空则直接用，跳过 PRD 读取。⛔ **从 baseline 读、不读 shell 变量**：`python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" get testplan_deploy_url --default ""`（两个 Phase 分属不同 Bash 调用，shell state 不跨调用持久——读变量恒空、本优先级形同虚设）
2. **PRD `autopilot_decisions.deployment`** — 兜底，格式如下（由 sprint-autopilot Phase 0.6 一次性收集 + 写回 PRD；本命令仅读不写）

PRD 头部 `autopilot_decisions.deployment` 段必须含以下字段（与原 `/sprint-autopilot` 设计一致 — 由 sprint-autopilot Phase 0.6 一次性收集 + 写回 PRD；本命令仅读不写）：

```yaml
deployment:
  mode: local | cloud | none
  # ↓ mode=local 段
  local_frontend_url: "http://localhost:5173"
  local_backend_url: "http://localhost:8080"
  local_ready_wait_seconds: 30
  # ↓ mode=cloud 段
  cloud_deploy_url: "https://uat.example.com"
  cloud_backend_url: "https://uat.example.com/api"
  cloud_deploy_check_url: "https://uat.example.com/health"
  cloud_deploy_wait_seconds: 300
  cloud_deploy_check_timeout_seconds: 900
  # ↓ 登录段（AI 自动化测试核心）
  requires_login: true | false
  login_url: "/login"
  login_strategy: form-fill | sso | api-token
  login_form_selectors:
    username_input: "input[name='username']"
    password_input: "input[type='password']"
    submit_button: "button[type='submit']"
    success_indicator: ".user-profile"
  user_roles: [admin, normal-user]
  login_after_seconds: 5
```

**字段缺失处理**：
- mode 缺失 → 记账 + 判阈 + 冻结 + 发 #4 一次做完，退出本 tick（PRD 补齐 `deployment.mode` 后按 PRD 目录 mtime 自动解冻）：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
    --phase 0.3-deploy-mode --reason prd-missing --streak-key prd_missing_streak --threshold 3 \
    --why "PRD frontmatter 缺 autopilot_decisions.deployment.mode，无法判定部署模式；在 PRD 补齐或跑 /sprint-autopilot Phase 0.6 收集"
  exit 0
  ```
- mode=none → 命令直接退出，标"该版本不做浏览器测试"
- 登录字段 + credentials 文件 → 详见 Phase 0.4

### 0.4 测试账号加载（研发自测/ 配置优先 → credentials 文件兜底）

> 📌 **本节的"跳到 Phase 1"是【流程指令】不是 shell 语句**：下面代码块里凡出现 `CREDS_DONE=1` 的分支，含义都是"账号环节到此结束、**直接往下执行 0.4bis 冒烟预检，随后进入 Phase 1**"——不要去找/自造 `GOTO_PHASE_1` 之类的函数，也不要 `exit`（`exit` 会终止整条测试链路）。

```bash
CRED_FILE="memory/.sprint-autopilot-credentials.json"
CREDS_DONE=0     # =1 表示账号环节已收口 → 跳过本节余下分支，往下走 0.4bis → Phase 1
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"   # 读回 SKIP_LOGIN / REQUIRES_LOGIN

# 1. 不需要登录 → 账号环节直接收口
# ⛔ `REQUIRES_LOGIN` 取空时**不得**当成"不需要登录"：那会跳过账号收集、让需要登录的应用
#   直接去测公开页，测出一堆"页面空白"假缺陷。取不到即按**需要登录**处理（fail-closed），
#   真源 = 测试方案「二·连接模式/登录」，由 Phase 0.0.5 读出后经 tick 变量落盘。
# ⚠️ 值域是 **0/1**（`autopilot_tick_flags.py` 的 FALLBACK_DEFAULT 就是 `"1"`），不是 true/false。
#    ⛔ 曾写成 `[ "$REQUIRES_LOGIN" != "true" ]` —— `--shell` 恒输出 `REQUIRES_LOGIN=1`，
#    该判据恒真 ⇒ 需登录的系统整批跳过账号加载，正是本段要防的"页面空白假缺陷"。
#    且 `--shell` 恒输出赋值行，`:=` 默认值永不生效，故 fail-closed 要显式判空。
[ -z "$REQUIRES_LOGIN" ] && REQUIRES_LOGIN=1
[ "$REQUIRES_LOGIN" = "0" ] && CREDS_DONE=1

# 2. 命令带 --skip-login → 收口（测公开页）
[ "$SKIP_LOGIN" = "1" ] && CREDS_DONE=1

# ★ 优先路径：从 研发自测/ 配置读取账号
# TESTPLAN_CREDS_READY=1 表示 Phase 0.0.5 检测到账号已填写
if [ "$CREDS_DONE" = "0" ] && [ "$TESTPLAN_CREDS_READY" = "1" ]; then
  # ⬇⬇ 这一步没有 shell 命令可写，由 Claude 亲自执行（**必须真做，不是注释**）：
  #   ① 用 Read 工具打开 $TESTPLAN，定位「四、测试账号」表；
  #   ② 按角色（admin / 普通用户）逐行取「用户名」「密码」两列，赋给 CRED_USER_<角色> / CRED_PASS_<角色>；
  #   ③ 任一字段为空或仍含「请填写」→ 视为未配置：置 TESTPLAN_CREDS_READY=0 并**继续往下走** credentials 文件兜底路径；
  #   ④ 全部取到 → CREDS_DONE=1（账号环节收口，**不弹任何 AskUserQuestion**）。
  :
fi

# 兜底路径（向后兼容旧机制）：从 credentials JSON 文件读
if [ "$CREDS_DONE" = "0" ] && [ ! -f "$CRED_FILE" ]; then
  # 账号均未配置（研发自测/ 配置未填、credentials 文件不存在）
  if [ "$LOOP_UNATTENDED" = "1" ]; then
    # ★ 无人值守：无人可答 → 绝不 AskUserQuestion。记账/四件套/#4 一次做完（**配置类** account-missing：
    #   解冻看 研发自测/ 配置文件 mtime，补账号不产生新部署）。
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --freeze-now \
      --phase 0.4-account --reason account-missing \
      --why "需登录应用但未取到测试账号；在 研发自测/「四、测试账号」表补填后自动复探"
    exit 0   # 本版已冻结待人工 → 终止本次调用；⛔ 不用 exit 1（已记账 + 已告警）
  else
    # 交互式兜底（仅 Phase 0.0.6 Step 5「一次性收全」未收到账号时才到这里；已收则 TESTPLAN_CREDS_READY=1 走上方直接读、不二次弹窗）：
    # ⬇⬇ 由 Claude 执行（无对应 shell 命令）：用 AskUserQuestion 逐角色收「用户名 / 密码」，
    #    问题正文里带一句「建议改填 研发自测/ 配置的『四、测试账号』表，下次即可免询问」；
    #    收到后写 $CRED_FILE（按 deployment.mode 分段、按 role 分键），再置 CREDS_DONE=1。
    :
  fi
fi

# credentials 文件存在但缺当前 deployment.mode 段 → 仅补缺失 mode
# 缺某 role → 仅补该 role
```

### 0.4bis 账号登录冒烟预检（G1 — 跑用例【前】就断言账号真能登进去，而非等 Phase 2 白跑一轮才发现）

> 实测反馈：Phase 0.4 只校"账号是否已配置"，不验证能否**真正登录进应用**。两个企业管理员账号（主测 + 备用）都已失效（登录后被拦"您尚未关联任何企业"），却直到 Phase 2 跑用例才发现，首轮 32/42 阻塞、白跑一轮。故账号加载后、进 Phase 1 **之前**，用**主测账号实际走一次登录冒烟**——判据与 Phase 1.1 部署就绪同源（不只看登录页 200，要看**登录成功 + 自身鉴权接口能取到数据**）：

```bash
# 仅 REQUIRES_LOGIN=true 且非 --skip-login 时执行；static-only / mode=none 不涉及
# 判据复用部署就绪探针字段：cloud_ready_login_url（登录接口）+ cloud_ready_api_url（登录后自身鉴权接口，取到数据才算真进去）
for ROLE in 主测账号 备用账号; do
  # 1) curl POST cloud_ready_login_url 拿 token/cookie（失败=该账号登录不通）
  # 2) 带凭证请求 cloud_ready_api_url，断言返回 cloud_ready_api_expect / 数据非空
  #    ——★ 关键：能登录 ≠ 能用；"登录后被拦'未关联企业'/无数据"在此就暴露，不留到跑用例
  # 通过 → 记该 ROLE 为 SMOKE_OK、作为本轮主用账号，break
  # 失败 → 记失效现象（如"登录后被拦：您尚未关联任何企业"），换下一个 ROLE 重试
  :
done

# ★ 冒烟通过的账号写回 run-context 作主用；失效账号在报告「测试概况」标注，不计入产品缺陷（环境阻塞）
```

<!-- flowvar-check: allow SMOKE_OK 上方冒烟循环选出的主用账号 ROLE（为空 = 全部失败）-->
<!-- flowvar-check: allow SMOKE_FAILURES 上方冒烟循环逐个记下的失效现象 -->

**全部候选账号冒烟失败 → 不进 Phase 2 空跑。** ⛔ 下面这段**必须原样执行**，不得退化成注释：
注释态下执行体跑完围栏就穿过去了，既不冻结也不告警 —— 心跳照刷、开发链路读到「测试链路健康」
走暂缓，12 tick 后按 `unconverged` 误冻，而真因完全不可见（同 `flows/sprint-batch/rationale.md`
「散文承诺 ≠ 可执行落点」）。

```bash
# ⛔ shell state 不跨 Bash 调用：本围栏要用 tick 变量就必须自己 eval 一次读回。
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# SMOKE_OK 为空 = 所有候选账号都登录失败
if [ -z "${SMOKE_OK:-}" ]; then
  if [ "${LOOP_UNATTENDED:-0}" = 1 ]; then
    # 冻结四件套 + #4 **一次调用做完**（**配置类**，解冻看配置文件 mtime）。
    # ⛔ 别只写四件套不发 #4 —— 那是停得住但停不响，一条通知都没有。
    # ⛔ 别写 `UNATTENDED_YIELD`——它不是命令，逐字执行会 command not found 且不退出。
    # 解冻 = 在 研发自测/ 换有效账号（文件 mtime 更新）或人工 retry —— **不要等 last_deployed_at**：
    # 换账号不产生新部署，按部署解冻等于永不解冻。
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test \
      --version "$TARGET_VERSION" --freeze-now --phase 0.4-account --reason account-invalid \
      --why "配置的候选账号全部登录失败（现象：${SMOKE_FAILURES:-见上方逐个现象}），请在 研发自测/ 换有效账号"
    exit 0
  fi
  # 交互式 → #4 @用户「配置的账号均登录失败（现象:...），请换有效账号后重试」，暂停本轮
fi
```

- **落点**：本步在 0.4 账号加载**成功后**（`CREDS_DONE=1`）、**进入 Phase 1 之前**执行；`static-only` / `mode=none` / `--skip-login` 直接跳过。
- **与部署就绪的一致性**：账号冒烟与 Phase 1.1「部署就绪 = 登录成功后自身接口连续取数」用**同一判据**——部署就绪校"环境起没起"，账号冒烟校"这个账号进不进得去"，两者都不靠"登录页可达"这种假信号。
- **切备用**：主测账号冒烟失败自动切备用账号（若测试方案登记了多角色/备用），全部失败才降级/报阻塞。
- **配套**：「账号最近验证时间」字段与 7 天新鲜度口径单一信源 = `dev-manual-testcase/assets/test-plan-template.md` §3.2；本冒烟负责刷新该列。

**账号配置方式（推荐顺序）**：

| 优先级 | 方式 | 路径 | 是否 gitignore | 适用场景 |
|--------|------|------|---------------|---------|
| **P1（推荐）** | 研发自测/ 配置 | `docs/testing/{version}/研发自测/` 目录「四、测试账号」 | **否**（随代码一起入库）| 开发测试环境，账号不涉及安全 |
| P2（兼容） | credentials JSON | `memory/.sprint-autopilot-credentials.json` | 是（chmod 600）| 生产 / UAT 等敏感账号 |

> ★ 账号优先维护在 `研发自测/` 配置、敏感账号才用 credentials JSON 的总则见 Phase 0.0.5。

**credentials JSON 文件规范**（向后兼容，仍支持）：

- **位置**：`memory/.sprint-autopilot-credentials.json`（保留 sprint-autopilot 命名以维持向后兼容）
- **权限**：`chmod 600`（命令端创建后立即设）
- **gitignore**：`.gitignore` 必含该路径（验证 `git check-ignore`；未含则报错 + 发 #4 里程碑通知提醒用户）
- **历史扫描**：`git log --all -- "$CRED_FILE"` 检测是否曾被误 commit；若有 → 发 #4 里程碑通知提醒用户 + 退出，要求 `git filter-repo` 清理
- **禁止打印**：命令端日志 / 里程碑通知 / 测试报告中**绝不**打印明文密码；显示 `<password hidden>`
- **格式**：

```json
{
  "schema_version": "2",
  "collected_at": "2026-06-10T11:00:00+08:00",
  "users": {
    "alice": {
      "deployments": {
        "local": {
          "admin":       {"username": "admin",     "password": "******"},
          "normal-user": {"username": "user1",     "password": "******"}
        },
        "cloud": {
          "admin":       {"username": "uat-admin", "password": "******"},
          "normal-user": {"username": "uat-user",  "password": "******"}
        }
      }
    }
  }
}
```

