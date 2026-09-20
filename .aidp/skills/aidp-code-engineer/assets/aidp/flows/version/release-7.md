# /version · 版本发布流程详情 — 分片 7/9

> 本片覆盖：**Step 3.4 打 tag + 建分支 + 提交推送（3.4.1–3.4.4）**（3.3.12bis / 3.3.13 在 `release-6.md`）。
> **Step 3.5（更新项目记忆文件「当前状态」）与 3.6（发布报告）全文见 `release-7b.md`**，进入该步第一动作 = Read 该文件。
> 完整分片清单见 `.aidp/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
### Step 3.4：打 Git 标签 + 创建版本分支并自动提交推送（自动 push）

> ★ `--no-tag`（仅 autopilot 准发布）：跳过 3.3.11 / 3.4.2；仍执行 3.4.1 提交（含终态落账门）、3.4.3 推送、3.4.4 失败处置。3.3 版本历史与 3.5 均标「🟡 已准发布（未打 tag）」，3.6 出准发布报告并说明可正式 `/version {version}` 补打。

#### Step 3.4.1：提交本轮发布产物

发布流程会改动 `memory/{version}/{user}/progress.md`、`AGENTS.md`、activeContext / sprints/ 等；工作区有未提交变更时先打一个发布提交：

```bash
# ★ 自取版本号（见 rationale）
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 .aidp/scripts/baseline_edit.py current-version);; esac
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
BE="python3 .aidp/scripts/baseline_edit.py"
BUILD=$($BE --version "$VERSION" get current_build --default "")
# push 基准在发布 commit 前保存；首次无 HEAD 保持空值并 fail-closed
BASE_REF=$(git rev-parse HEAD 2>/dev/null || true)
[ -n "$BUILD" ] && $BE --version "$VERSION" --build "$BUILD" set push_base_ref "$BASE_REF"
# ★ 终态落账门：关键产物缺失且台账无对应条目 = 静默跳过 → 当场补登记（随本提交入库）
NO_TAG_FLAG=""   # ← 带 --no-tag 时执行体就地改为 --no-tag
python3 .aidp/scripts/release_debt.py gate --version "$VERSION" $NO_TAG_FLAG --register-missing
# 检查工作区
if [ -n "$(git status --porcelain)" ]; then
  git add memory/{version}/ AGENTS.md docs/reports/{version}/ 版本更新日志.md README.md 2>/dev/null || true
  git add plans/ dev/ tests/ release/ frontend/ backend/ packages/ 2>/dev/null || true
  git add docs/requirements/requirements-*.md 2>/dev/null || true
  git add docs/deployment/{version}/ 2>/dev/null || true
  git add docs/deployment/tools/ 2>/dev/null || true
  git add docs/reports/{version}/ 2>/dev/null || true
  # ★★ 四族规划主文档 + 全量设计 + 审计/欠账 ⛔ 绝不能省：3.3.9.5/3.3.10/3.3.11 只改工作区，落库全靠本步。
  git add docs/requirements/{version}/ docs/design/detail/{version}/ docs/design/detail/全量/ 2>/dev/null || true
  git add docs/plans/{version}/ docs/testing/{version}/ docs/audit/{version}/ 2>/dev/null || true
  git add docs/references/{version}/ 2>/dev/null || true
  git commit -m "release({version}): {milestone}"
fi
# ★ 提交后断言：发布产物必须全部入库（fail-closed）
if git -c core.quotepath=false status --porcelain docs/ | grep -q .; then
  echo "⛔ 发布产物未入库，`docs/` 仍有未提交改动："
  git -c core.quotepath=false status --porcelain docs/
  echo "   → 补 git add 后 `git commit --amend --no-edit`，⛔ 不得带着残余打 tag"
  exit 1
fi
```

> 🔗 **约定 24 提交前门禁（本路径同样适用）**：提交前跑 `python3 .aidp/scripts/commit_gate.py --quiet` 读 JSON；退出码 3/4 = 本轮结束前有义务未落地（约定 22 台账积压 → 派台账收口子 Agent；CICD 推送欠账 → 补监听），不是禁止 commit。

#### Step 3.4.2：打 tag（tag 命名用小写 v SemVer 风格）

**tag 命名约定（强制）**：

- 默认 tag 名 = **`v{version 去 V 前缀}`**（如 `V0.1.0` → tag = `v0.1.0`；`V1.2.3` → tag = `v1.2.3`）
- **历史 tag** 保持原样不动（`V*` / `release-V*` 等历史风格）；"前一已发布版本"的识别统一按「tag 风格识别约定」三种风格全覆盖取最新

**Step 3.4.2.1 ~ 3.4.2.3：冲突检测 + 授权分流 + 打 tag / 建版本分支（⛔ 必须同一个 Bash 块）**

打 tag 前把 `{version}` 转成 `v0.1.0` 形态，并验证不与已有 tag/分支重名。撞名时**保持同名、移动到本次发布提交**
（不加时间后缀、不改名）；但移动**远端已存在**的 tag 是 destructive、**须先授权**（理据见 `rationale.md`）。

> ⚠️⚠️ **两个变量、两件事，⛔ 严禁合并成一个**：`REPUBLISH` 只回答「撞名了吗」，
> `FORCE_AUTHORIZED` 才回答「可以强推吗」（理据见 `rationale.md`）。
> ⚠️ **检测 → 授权 → 建 tag/分支必须在同一个 Bash 块**：围栏之间 shell 变量不存活，
> 拆开则三个变量全部取空。跨块传递一律经 baseline（下方末尾已落盘，供 Step 3.4.3 读回）。

**授权分流（先做，结果就地写进下方 `FORCE_AUTHORIZED`）**：

- **交互式**（用户在场）→ **白名单第 4 处结构化门**：`AskUserQuestion` 二选一 ——
  ① **强制移动**（确认这是上次发布失败的重跑）→ `FORCE_AUTHORIZED=1`；
  ② **中止发布**，改用新补丁号 → 保持 `FORCE_AUTHORIZED=0`。
- **情况 C 已在 Step 1 入口过门**（`version.md`）→ 沿用其结果（baseline `release_force_authorized`），⛔ 不重复问。
- **无人值守**（`--unattended` / `--no-tag` / `LOOP_UNATTENDED`）→ **保持 `FORCE_AUTHORIZED=0`，⛔ 不得改**：
  跳过 tag/分支的创建与推送、其余步骤照常，登记 `docs/audit/{version}/发布欠账.md` + 终端 WARN。

```bash
set -e
# ★ 自取版本号（见 rationale）
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 .aidp/scripts/baseline_edit.py current-version);; esac
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
BE="python3 .aidp/scripts/baseline_edit.py"
TAG_NAME="v$(echo "$VERSION" | sed -E 's/^[Vv]//')"; BRANCH_NAME="V${TAG_NAME#v}"
EXISTING_TAG=$(git tag -l "$TAG_NAME")
# ★ tag 必须同时查远端（理据见 rationale.md）；远端不可达时退化为只按本地判、不中断发布
EXISTING_TAG_REMOTE=$(git ls-remote --tags origin "refs/tags/$TAG_NAME" 2>/dev/null | head -1 || true)
EXISTING_BRANCH_LOCAL=$(git branch --list "$BRANCH_NAME" | sed 's/^[* ] *//')
EXISTING_BRANCH_REMOTE=$(git branch -r --list "origin/$BRANCH_NAME" | sed 's/^[ ]*//')
REPUBLISH=0
if [ -n "$EXISTING_TAG" ] || [ -n "$EXISTING_TAG_REMOTE" ] \
   || [ -n "$EXISTING_BRANCH_LOCAL" ] || [ -n "$EXISTING_BRANCH_REMOTE" ]; then
  REPUBLISH=1
  echo "♻️ 撞名：tag 本地=${EXISTING_TAG:-无} 远端=${EXISTING_TAG_REMOTE:+有}" \
       "| 分支 本地=${EXISTING_BRANCH_LOCAL:-无} 远端=${EXISTING_BRANCH_REMOTE:-无}"
fi

# ★★ 授权位 —— **默认拒绝**（理据见 rationale.md）
FORCE_AUTHORIZED=$($BE --version "$VERSION" get release_force_authorized --default 0)   # 情况 C 入口已授权则为 1
# ← 交互式 B-3 撞名时执行体按授权结果就地改为 0 / 1；⛔ 无人值守不得改

if [ "$REPUBLISH" = "1" ] && [ "$FORCE_AUTHORIZED" != "1" ]; then
  # 撞名但未获授权（无人值守恒走此支）→ 整段跳过 tag 与版本分支，登记欠账，其余发布步骤照常
  python3 .aidp/scripts/release_debt.py add --version "$VERSION" --step 3.4.2 \
    --title "tag/版本分支未创建（撞名且未获强推授权）" \
    --locate "$TAG_NAME / $BRANCH_NAME 已被占用；发布提交 $(git rev-parse HEAD)" \
    --redo "交互式重跑 /version $VERSION 并在授权门选①，或改用新补丁号"
  # ★ 欠账必须落库（3.4.1 提交在本步之前，同 release-7c.md）
  if [ -n "$(git status --porcelain docs/audit/)" ]; then
    git add "docs/audit/$VERSION/" && git commit -m "docs($VERSION): 登记发布欠账（tag 撞名未授权）"
  fi
  TAG_NAME=""; BRANCH_NAME=""        # ★ 置空 = Step 3.4.3 push 段的跳过信号
elif [ "$REPUBLISH" = "1" ]; then
  git tag -f -a "$TAG_NAME" -m "Re-release $VERSION"
  git branch -f "$BRANCH_NAME" HEAD  # 不切换分支，HEAD 仍留主分支
  echo "♻️ 已获授权强制移动 tag $TAG_NAME + 版本分支 $BRANCH_NAME → 指向本次发布提交"
else
  git tag -a "$TAG_NAME" -m "Release $VERSION"
  git branch "$BRANCH_NAME"
  echo "🏷️ 已创建 tag $TAG_NAME + 版本分支 $BRANCH_NAME（指向本次发布提交）"
fi
# ★ 跨块落盘：Step 3.4.3 的 push 段据此判断推什么、要不要 -f（⛔ 别再靠 shell 变量跨围栏）
$BE --version "$VERSION" set release_republish "$REPUBLISH" \
  release_force_authorized "$FORCE_AUTHORIZED" release_tag_name "$TAG_NAME" release_branch_name "$BRANCH_NAME"
```

> **版本分支命名**：大写 `V{version}`（如 `V0.1.0`），与小写 tag `v0.1.0` 在 case-sensitive git ref
> 命名空间中天然隔离。**`--no-tag` 准发布模式整段跳过 Step 3.4.2**（`TAG_NAME`/`BRANCH_NAME` 都不生成）。

#### Step 3.4.3：自动推送 commit + tag + 版本分支

```bash
# ★ 自取版本号（见 rationale）
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 .aidp/scripts/baseline_edit.py current-version);; esac
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
BE="python3 .aidp/scripts/baseline_edit.py"
BUILD=$($BE --version "$VERSION" get current_build --default "")
if [ -n "$BUILD" ]; then
  BASE_REF=$($BE --version "$VERSION" --build "$BUILD" get push_base_ref --default "")
  python3 .aidp/scripts/classify_push.py --root . --version "$VERSION" --build "$BUILD" --base-ref "$BASE_REF" || CLASSIFY_ERROR=1
else
  BASE_REF=$(git rev-parse HEAD 2>/dev/null || true)
  python3 .aidp/scripts/classify_push.py --root . --version "$VERSION" --standalone --base-ref "$BASE_REF" || CLASSIFY_ERROR=1
fi
# ⛔ 三处 push 逐个捕获 rc，任一失败即落盘 + 阻断：本围栏无 `set -e`，不捕获就会带着
#   **从未推出去的 commit** 继续跑探针并宣告"发布完成"。见 `rationale.md`「push 失败为何必须显式分流」。
PUSH_FAILED=""
git push origin "$(git symbolic-ref --short HEAD)" || PUSH_FAILED="commit"
# ★ tag/分支推送口径从 baseline 读回（⛔ 不靠跨围栏 shell 变量）；`-f` 唯一通行条件 =
#   撞名 AND 已获显式授权。理据见 `rationale.md`「推送口径为何从 baseline 读回」。
TAG_NAME=$($BE --version "$VERSION" get release_tag_name --default "")
BRANCH_NAME=$($BE --version "$VERSION" get release_branch_name --default "")
REPUBLISH=$($BE --version "$VERSION" get release_republish --default 0)
FORCE_AUTHORIZED=$($BE --version "$VERSION" get release_force_authorized --default 0)
if [ "$REPUBLISH" = "1" ] && [ "$FORCE_AUTHORIZED" = "1" ]; then PUSH_F="-f"; else PUSH_F=""; fi
# ⛔ 用 if 而非 `[ -n ] && git push`：后者变量为空时整体 rc=1，接 `||` 会把"本轮不推 tag"误判成失败。
if [ -n "$TAG_NAME" ]; then
  git push $PUSH_F origin "$TAG_NAME" || PUSH_FAILED="${PUSH_FAILED:+$PUSH_FAILED,}tag"
fi
if [ -n "$BRANCH_NAME" ]; then
  git push $PUSH_F origin "$BRANCH_NAME" || PUSH_FAILED="${PUSH_FAILED:+$PUSH_FAILED,}branch"
fi
if [ -n "$PUSH_FAILED" ]; then
  $BE --version "$VERSION" set release_push_failed "$PUSH_FAILED" >/dev/null 2>&1 || true
  echo "⛔ 推送失败（$PUSH_FAILED）→ 转 Step 3.4.4 失败处置（release-7c.md）"
  exit 1
fi

PUSH_COMMIT=$(git rev-parse HEAD)
if [ "${CLASSIFY_ERROR:-0}" = "1" ]; then
  CICD_SKIPPED=false
  echo "⚠️ 发布 push 分类失败 → fail-closed，按正式代码进入 CICD 监听"
elif [ -n "$BUILD" ]; then
  CICD_SKIPPED=$($BE --version "$VERSION" --build "$BUILD" get cicd_skipped --default false)
else
  CICD_SKIPPED=$($BE --version "$VERSION" get release_change_classification.cicd_skipped --default false)
fi
if [ "$CICD_SKIPPED" = "true" ]; then
  echo "✅ 发布 push 判定为 docs-only → 不触发 CICD、不监听、不跑就绪探针"
else
  eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
  # ⛔ `--shell` 只输出 TARGET_VERSION、不输出 VERSION，故本块自取（见 rationale.md）
  VERSION="{version}"
  [ -z "$VERSION" ] || case "$VERSION" in "{version}") VERSION="${TARGET_VERSION:-}";; esac
  [ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
  BE="python3 .aidp/scripts/baseline_edit.py"
  # ⛔ `autopilot_decisions.*` 在 PRD frontmatter、不在 baseline（取必得空串 → 下方 fail-closed 恒成立）。
  PRD_FILE=$(find "docs/requirements/$VERSION/产品提供" -maxdepth 1 -name '*.md' 2>/dev/null | sort | head -1)
  yml() { [ -n "$PRD_FILE" ] && awk -v k="$1" '/^---$/{f=!f;next} f && $1==k":"{print $2;exit}' "$PRD_FILE"; }
  # ★ 先判部署形态：mode=local / none / 未接入 CICD 流水线的项目**没有云端流水线可等**。
  #   ⛔ 缺这道门 → 推 tag 后 fail-closed 退出、版本半截收口（见 rationale.md）。
  DEP_MODE=$(yml mode); [ -n "$DEP_MODE" ] || DEP_MODE="none"
  if [ "$DEP_MODE" = "local" ] || [ "$DEP_MODE" = "none" ]; then
    echo "ℹ️ deployment.mode=$DEP_MODE（无云端流水线）→ 跳过 CICD 监听与就绪探针，直接进 Step 3.5"
  else
  CICD_ENV=$(yml cicd_env); [ -n "$CICD_ENV" ] || CICD_ENV="prod"
  CLOUD_HEALTH_URL=$(yml cloud_ready_api_url)
  CLOUD_AUTH_URL=$(yml cloud_ready_login_url)
  # ⚠️ 传 --auth-url 必须同时给凭证，否则鉴权探针恒判未就绪。
  AUTH_HEADER=$(yml cloud_ready_auth_header)
  CLOUD_DEPLOY_TIMEOUT=$(yml cloud_deploy_check_timeout_seconds); [ -n "$CLOUD_DEPLOY_TIMEOUT" ] || CLOUD_DEPLOY_TIMEOUT=300
  [ -n "$CLOUD_HEALTH_URL" ] || { echo "⛔ 缺少部署就绪 health URL，fail-closed"; exit 1; }
  WATCH_JSON=$(python3 .aidp/scripts/cicd_watch.py --commit "$PUSH_COMMIT" --env "$CICD_ENV" \
    --version "$VERSION") || WATCH_RC=$?
  WATCH_RC=${WATCH_RC:-0}
  [ "$WATCH_RC" -eq 0 ] || [ "$WATCH_RC" -eq 1 ] || [ "$WATCH_RC" -eq 2 ] || [ "$WATCH_RC" -eq 3 ] || {
    echo "⛔ cicd_watch 异常 → 按正式代码 fail-closed，禁止宣告发布完成"; exit 1; }
  if [ "$WATCH_RC" -eq 3 ]; then
    # rc=3 = 未接入 CICD（disabled / not-configured）或提供方 CLI 不可用：不监听流水线，直接跑就绪探针确认部署结果
    echo "⚠️ cicd_watch 未监听（$(printf '%s' "$WATCH_JSON" | jq -r '.verdict // "?"')：$(printf '%s' "$WATCH_JSON" | jq -r '.reason // ""')）→ 仅按就绪探针判定部署"
    WATCH_JSON='{"next_action":"probe"}'
  fi
  while :; do
    ACTION=$(printf '%s' "$WATCH_JSON" | jq -r '.next_action // "abort"')
    case "$ACTION" in
      poll)
        # 单次调用到上限仍在运行（verdict=running）→ 继续 poll 同一运行
        RUN_ID=$(printf '%s' "$WATCH_JSON" | jq -r '.run_id // empty')
        [ -n "$RUN_ID" ] || { echo "⛔ cicd_watch 返回 poll 但缺 run_id"; exit 1; }
        WATCH_RC=0
        WATCH_JSON=$(python3 .aidp/scripts/cicd_watch.py --mode poll --run-id "$RUN_ID" \
          --env "$CICD_ENV" --version "$VERSION") || WATCH_RC=$?
        [ "$WATCH_RC" -le 3 ] || { echo "⛔ cicd_watch 异常 fail-closed"; exit 1; } ;;
      probe)
        python3 .aidp/scripts/autopilot-deploy-watch.py \
          --health-url "$CLOUD_HEALTH_URL" \
          ${CLOUD_AUTH_URL:+--auth-url "$CLOUD_AUTH_URL"} \
          ${AUTH_HEADER:+--auth-header "$AUTH_HEADER"} \
          --cold-start-seconds 55 --timeout "$CLOUD_DEPLOY_TIMEOUT" --version "$VERSION" || exit 1
        break ;;
      retry)
        RETRY_COMMIT=$(printf '%s' "$WATCH_JSON" | jq -r '.retry_commit // empty')
        [ -n "$RETRY_COMMIT" ] || { echo "⛔ cicd_watch retry 缺少 retry_commit，禁止漂移重跑"; exit 1; }
        RETRY_COUNT=$($BE --version "$VERSION" get cicd_run.cicd_retry_count --default 0)
        [ "$RETRY_COUNT" -lt 3 ] || { echo "⛔ CICD 重试已达 3 次 → 转人工"; exit 1; }
        # ⛔ prod 不自动重跑：自动重跑只对 dev/test 成立（同下方 trigger 分支口径）
        case "$CICD_ENV" in
          prod|production)
            echo "⛔ 生产环境 CICD 失败：禁止自动重跑，请用户确认后手动重跑（commit=$RETRY_COMMIT）"; exit 1 ;;
        esac
        # 重试 = cicd_watch.py --mode retry（平台由 cicd.provider 决定）
        RUN_ID=$(printf '%s' "$WATCH_JSON" | jq -r '.run_id // empty')
        # ★ 空值必须当场炸（否则 `--run-id ""` 让 ≤3 次重试第一次就撞死，且报错文案盖住真因）
        [ -n "$RUN_ID" ] || { echo "⛔ cicd_watch retry 未返回 run_id —— 重试链中止"; exit 1; }
        RETRY_JSON=$(python3 .aidp/scripts/cicd_watch.py --mode retry --run-id "$RUN_ID" --env "$CICD_ENV" \
          --version "$VERSION") || { echo "⛔ 重试被拒：$RETRY_JSON"; exit 1; }
        $BE --version "$VERSION" bump cicd_run.cicd_retry_count
        NEW_RUN_ID=$(printf '%s' "$RETRY_JSON" | jq -r '.run_id // empty')
        # ⛔ 不能 `|| exit 1`：exit 1 = 需调用方做写动作、非错误，用它会让 ≤3 次封顶成 1 次。
        WATCH_RC=0
        if [ -n "$NEW_RUN_ID" ]; then
          WATCH_JSON=$(python3 .aidp/scripts/cicd_watch.py --mode poll --run-id "$NEW_RUN_ID" \
            --commit "$RETRY_COMMIT" --env "$CICD_ENV" --version "$VERSION") || WATCH_RC=$?
        else
          # 不回显新 id → 按原 commit 重新锁定
          WATCH_JSON=$(python3 .aidp/scripts/cicd_watch.py --commit "$RETRY_COMMIT" --env "$CICD_ENV" \
            --version "$VERSION") || WATCH_RC=$?
        fi
        WATCH_RC=${WATCH_RC:-0}
        [ "$WATCH_RC" -le 3 ] || { echo "⛔ cicd_watch 异常 fail-closed"; exit 1; } ;;
      trigger)
        echo "⛔ 发布 push 未触发 CICD；生产环境禁止自动 trigger，请用户确认后手动触发"; exit 1 ;;
      abort|*)
        echo "⛔ CICD 监听未完成（next_action=$ACTION）→ 禁止宣告发布完成"; exit 1 ;;
    esac
  done
  fi
fi
```

> ★ **推送分类与监听（约定 31.5）**：有 `current_build` 写 build、无则 `--standalone` 写版本级，⛔ 禁空 build；分类用 `BASE_REF`。
> ⛔ **发布期边界**：`next_action=trigger` 时**绝不自动触发**——只终端提示，由用户主动要求才执行 `python3 .aidp/scripts/cicd_watch.py --mode trigger --env <env> --ref <branch>`；`memory/aidp-config.yaml` 的 `cicd.provider=none` 或未配置 `cicd.pipelines` 时不适用。（余下理据见 `rationale.md`）

#### Step 3.4.4：失败处置

> 📄 **本步全文见 `release-7c.md`**（push 被拒 / rebase 冲突 / tag 撞名 / 强推被保护策略拒 / CICD 失败重试 ≤3 等分支）。
> 进入本步第一动作 = Read 该文件。
