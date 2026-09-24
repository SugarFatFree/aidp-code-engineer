# AIDP 项目配置（**人维护**，团队共享、随 git 提交）
#
# 这是你可以直接改的那一份。程序写的运行时状态在
# memory/.sprint-autopilot-baseline.json —— 那份别手动动，会被下一轮覆盖。
#
# 改完无需重启任何东西，下一次命令运行即生效。

project:
  # 项目标识。name = 英文应用编码（默认 git 仓库目录名）；name_cn = 对外中文名称，
  # 里程碑通知标题、OpenAPI 文档标题、子项目默认命名取它（缺省回退 name → git 仓库名）。
  name: {{project}}
  name_cn: "{{project_cn}}"

commit_gate:
  # 提交前门禁总开关（约定 24：每次 git commit 前跑 {{AIDP_HOME}}/scripts/commit_gate.py）。
  # 关掉之后：不再检查台账积压 / CICD 推送欠账。
  enabled: true

notify:
  # 里程碑通知总开关（约定 32：{{AIDP_HOME}}/scripts/notify.py）。
  # 未开启或未配置任何渠道时，播报节点静默跳过，不阻断链路。
  enabled: false
  # 一个渠道失败时是否尝试下一个
  fallback: true
  # autopilot 启动时是否发 #0a「渠道已连通」通知（默认不发，避免噪音）
  channel_ready_card: false
  # 渠道按顺序尝试，成功即停。⛔ webhook 地址 / 密钥只经环境变量引用，不明文入库。
  channels: []
  # 例：
  #   - {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK, secret_env: AIDP_FEISHU_SECRET}
  #   - {type: dingtalk, webhook_env: AIDP_DINGTALK_WEBHOOK, secret_env: AIDP_DINGTALK_SECRET}
  #   - {type: wecom, webhook_env: AIDP_WECOM_WEBHOOK}
  #   - {type: lark-cli, chat_id: "<chat id>"}
  #   - {type: command, command: "<读 stdin JSON 的发送命令>"}

cicd:
  # CICD 提供方（约定 31.5）：github-actions（默认）/ gitlab-ci / jenkins / command / none。
  provider: github-actions
  # 无人值守下是否允许自动触发 / 重试流水线。
  auto_trigger: true
  max_retries: 3
  # 部署环境 → 流水线标识。github-actions = workflow 文件名；gitlab-ci = 分支名（可留空）；
  # jenkins = Job 路径；command = 原样代入命令模板的 {pipeline}。例：{test: deploy-test.yml}
  pipelines: {}
  # 各提供方专属参数（只填所选那个）。⛔ 令牌 / 密码只写环境变量名。
  # gitlab-ci: {url: https://gitlab.com, project: group/name, token_env: AIDP_GITLAB_TOKEN}
  # jenkins:   {url: https://jenkins.example.com, user_env: AIDP_JENKINS_USER, token_env: AIDP_JENKINS_TOKEN}
  # command:   {list: "...", view: "...", trigger: "...", retry: "...", check: "..."}
  # ★ 本项目「推送即自动部署」吗（约定 31.5）：true = 推送本身就是触发，⛔ 不再主动触发流水线。
  # 只记事实、不改 CICD 配置。由 `{{AIDP_HOME}}/scripts/aidp_state.py cicd-push-autodeploy-yes|-no` 写。
  push_auto_deploy: false
  # 推送即自动部署时，推送后最短等待秒数：等满仍取不到流水线状态 → cicd_watch.py 返回 rc=4
  # （降级放行就绪探针），⛔ 不冻结。防的是「流水线无法被单独触发 + 平台取不到状态」时链路被误冻
  # 且无恢复路径 —— 那种项目里主动触发恒失败，按失败熔断等于永不放行。
  push_deploy_min_wait_seconds: 300

stop_guard:
  # autopilot Stop 护栏（防止无人值守链路在未收口时静默停下）。
  # 关掉 = 临时逃生舱：护栏误报把你挡住时用，⛔ 排除故障后记得改回 true。
  enabled: true

scheduler:
  # 7×24 操作系统调度（python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install）：
  # 开发、测试链路各一个用户级定时任务，另装独立 watchdog 巡检（默认 5m）；两链路互不阻塞。
  dev_interval: 10m
  test_interval: 5m
  # 执行 Agent：auto（按 agent_env.py detect）/ claude / codex / dsh
  agent: auto
  # 任一链路连续多少个周期无心跳即本地告警（memory/.aidp/alerts.jsonl）+ 里程碑通知
  stale_cycles: 3
  # 单轮 tick 的硬上限（秒）。⛔ 它防的是最安静的一种故障：Agent 进程挂死 → 互斥锁被永久
  # 持有 → 之后每次调度都「上一轮仍在运行，跳过」→ watchdog 永远判 running → 零告警停摆。
  # agent_loop.sh 用它给 tick 套 timeout（环境变量 AIDP_TICK_MAX_SECONDS 优先，默认 7200）；
  # watchdog 用 max(stale 阈值, 本值, 1h) 作「持锁超期 = 挂死」的判据。0 = 不设上限（不推荐）。
  tick_max_seconds: 7200
  # 各 Agent 的非交互执行命令模板（{prompt} 为占位符）；留空用内置默认。
  # ⛔ 内置默认之外的 CLI 写法请按所用 Agent 当前版本的官方文档自行确认。
  exec: {}
  # 例：exec: {codex: "codex exec --sandbox workspace-write {prompt}"}

scaffold:
  # 本项目上次同步到的脚手架版本号。**由 aidp-code-engineer 脚手架写入，人别改**——
  # 改小会触发不必要的全量覆盖，改大会让真正的升级被跳过。
  version: null
  # 升级中途留下的待消费语义改写队列；非 null 表示**上一轮升级尚未真正交付**。
  pending: null

# autopilot 决策兜底（★ 权威是本版 PRD frontmatter 的 autopilot_decisions 段，
# 本段仅在 PRD 未声明时生效；全项目一份、无版本维度）。
autopilot_decisions: {}
