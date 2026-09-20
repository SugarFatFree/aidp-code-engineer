# >>> AIDP-GITIGNORE-MANAGED:BEGIN >>>
# 本区间由 aidp-code-engineer 脚手架 init / upgrade 自动写入并维护——**勿手动编辑**。
# 升级时整块按当前模板覆盖：新增规则会进、过时规则会删、改动规则会更新。
# 需要项目自定义忽略规则，请写在本标记区间**之外**（上方或下方），脚手架永不触碰。
#
# === Java ===
*.class
*.jar
*.war
*.nar
*.ear
hs_err_pid*
target/
# JVM 编译上下文残留
*.ctxt
# Mobility Tools for Java 临时目录
.mtj.tmp/

# === Node / Frontend ===
node_modules/
dist/
.nuxt/
.next/
.output/

# === Python ===
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# === Logs ===
*.log
logs/

# === IDE ===
.idea/
.vscode/
*.swp
*.swo

# === OS ===
.DS_Store
Thumbs.db

# === Archives ===
*.zip
*.tar.gz
*.rar

# === Environment / Secrets ===
.env.local
.env.*.local

# === Agent 本地配置（个人设置，不入库）===
.claude/settings.local.json
.claude/scheduled_tasks.lock
.codex/*.local.*
.dsh/*.local.*

# === Skill 本地凭证变体（本机私有，禁止入库）===
# 其他含密钥的 skill 配置由项目团队自行在**本托管区之外**追加忽略行（区间内会被升级覆盖）。
.aidp/skills/*/*-config.json
.aidp/skills/*/.env
.aidp/skills/*/config.json
.aidp/skills/*/assets/config.json

# === AIDP 脚手架 ===
# 升级前备份（按保留策略自动清理）
.aidp-backup-*
# ⚠️ 语义改写待办清单 .aidp-rewrite-queue.txt 刻意不忽略、必须入库：它表示「本次脚手架交付尚未收口」，
#    入库后团队可见；收口（finalize_upgrade.py）时自动删除。

# === Build ===
build/

# === /sprint-autopilot 命令运行时文件 ===
# baseline 文件 memory/.sprint-autopilot-baseline.json 入库提交、团队共享：
#   只存可共享的项目级版本状态机（versions.{V}，不按用户分桶、不含任何 git 用户名）+ 项目级运行时记录 project_state，故不在此忽略。
# 测试账号文件（敏感 — username + password 明文；命令端会自动追加此条 + chmod 600）
memory/.sprint-autopilot-credentials.json
# 里程碑通知发送台账（完成核验门 autopilot-ceremony-gate.py 用；本地校验状态，不入库）
memory/.autopilot-ceremony-ledger.json
# 本地运行态目录（锁文件、提交前门禁台账等）
memory/.aidp/
# baseline 的 flock 锁载体：0 字节、每次加锁被重开，纯本地 churn，无共享价值
# ⛔ 必须两条：数据文件本身就是点开头的，而 `memory/*.lock` 的 `*` 不匹配前导点
memory/*.lock
memory/.*.lock

# 代码事实索引：100% 由 code_inventory.py 从 code/ 派生重建，入库只会带来无尽 diff 与合并冲突。
memory/_facts/code-inventory.json
# === Stop hook（autopilot-stop-guard.py）的三个本地运行态：纯本地、不入库 ===
# 熔断计数（按 version_build 分键；收尾门通过即清）
memory/.autopilot-stop-guard-count
# fail-open 台账：护栏「本可介入却放行」的留痕，事后复盘用（滚动保留最近 50 条）
memory/.autopilot-stop-guard-skips.jsonl
# 人工临时禁用护栏的逃生舱开关（存在即全程放行；⛔ 用完记得删）
memory/.autopilot-stop-guard-off
# === AI 报告临时输入草稿（emit-report.py 的 --data；写在对应报告目录、生成 HTML 后自动删除，不入库）===
docs/reports/*/*/.build-input-*.json
memory/.exec-report-*.json
memory/.aiauto-test-result-*.json
memory/.test-report-*.json
# === chrome-devtools-mcp 远程连接配置 ===
# 远程 Chrome 地址写项目根 .mcp.json 的 server 条目 chrome-{git_user}，入库提交、团队共享
# （按 git 用户名分键，每人各持一条不冲突）——故 .mcp.json 不忽略。写入/校验由
# .aidp/scripts/chrome-mcp-doctor.py 负责。
# === 环境变量文件（含数据库/中间件凭据，绝不入库）===
# ⚠️ 忽略 + `git rm --cached` 只是**停止继续跟踪**，并不能撤销已进入 git 历史的旧值。
env/.env
env/.env.*

# <<< AIDP-GITIGNORE-MANAGED:END <<<
