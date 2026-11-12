# /version · 版本发布流程详情 — 分片 7/10

> 本片：**Step 3.4 打 tag / 建分支 / 提交推送（3.4.1–3.4.4）**；3.3.12bis / 3.3.13 见 `release-6.md`。
> **Step 3.5 更新记忆与 3.6 发布报告**：进入前 Read `release-7b.md`。
> 分片清单见 `{{AIDP_HOME}}/commands/version.md`，按 Step 读取执行。

<!-- BODY-BELOW -->
### Step 3.4：打 Git 标签 + 创建版本分支并自动提交推送（自动 push）

> `--no-tag`（仅 autopilot 准发布）：跳过 3.3.11/3.4.2，其余提交、终态门、推送和失败处置照常。3.3/3.5 标「已准发布（未打 tag）」，3.6 报告说明可正式 `/version {version}` 补打。

#### Step 3.4.1：提交本轮发布产物

**登记实际产物**：先执行下方终态门，再核对本轮文档、版本记忆及 `agent_env.py memory-file` 返回的真实项目记忆，经 `baseline_edit.py --version {version} set release_artifact_paths '<路径JSON数组>'` 登记具体文件（含新增、删除、全量 sidecar、欠账）。原有修改须先确认归属，不能以目录或全部 dirty 代替。下方合并 3.3.13 的版本修正写集逐文件暂存；重用清单前核对本轮内容。

```bash
# ★ 自取版本号（见 rationale）
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version);; esac
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
BUILD=$($BE --version "$VERSION" get current_build --default "")
set -e
# commit 前保存实际远端 HEAD，含已提交未推代码；远端/对象不可用或首推留空，保守监听，禁用提交后 HEAD。
PUSH_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || true)
PUSH_REMOTE=origin; PUSH_REF="refs/heads/$PUSH_BRANCH"   # 与 3.4.3 的实际 push 目标相同
REMOTE_LINE=$(git ls-remote --refs "$PUSH_REMOTE" "$PUSH_REF" 2>/dev/null || true)
BASE_REF=${REMOTE_LINE%%[[:space:]]*}
[ -n "$BASE_REF" ] && git cat-file -e "${BASE_REF}^{commit}" 2>/dev/null || BASE_REF=""
$BE --version "$VERSION" set release_push_base_ref "$BASE_REF" || exit 1
if [ -n "$BUILD" ]; then
  $BE --version "$VERSION" --build "$BUILD" set push_base_ref "$BASE_REF" || exit 1
fi
# 终态门：关键产物缺失且无台账时补登记，随发布提交入库。
NO_TAG_FLAG=""   # ← 带 --no-tag 时执行体就地改为 --no-tag
python3 {{AIDP_HOME}}/scripts/release_debt.py gate --version "$VERSION" $NO_TAG_FLAG --register-missing
# 发布写集：只提交明确登记的文件；未知/混杂/残留均阻断，不能 || true 吞错。
python3 - "$VERSION" "{{AIDP_HOME}}" <<'PY'
import json, os, subprocess, sys
from pathlib import Path
version, home = sys.argv[1:]
be = [sys.executable, home + '/scripts/baseline_edit.py', '--version', version]
def output(args):
    return subprocess.check_output(args)
def read(key, default='null'):
    return json.loads(output([*be, 'get', key, '--default', default]))
def git(*args):
    return output(['git', '--literal-pathspecs', *args])
def names(raw):
    return {os.fsdecode(p) for p in raw.split(b'\0') if p}
artifacts = read('release_artifact_paths')
fix = read('release_version_fix', '{"files":{},"blocked":[]}')
if (not isinstance(artifacts, list) or any(not isinstance(p, str) or not p for p in artifacts)
        or not isinstance(fix, dict) or not isinstance(fix.get('files'), dict)
        or fix.get('blocked')):
    raise SystemExit('发布写集缺失或含原有混杂修改，先核对归属并重新登记')
paths = sorted(set(artifacts) | set(fix['files']))
memory = json.loads(output([sys.executable, home + '/scripts/agent_env.py', 'memory-file']))['memory_file']
for required in (memory, 'docs/audit/' + version + '/发布欠账.md'):
    if git('status', '--porcelain', '--', required) and required not in paths:
        raise SystemExit('发布记忆或终态欠账尚未核对登记：' + required)
for path in paths:
    p = Path(path)
    if p.is_absolute() or '..' in p.parts or '.git' in p.parts or p.is_dir():
        raise SystemExit('发布写集必须逐文件指定仓内路径：' + path)
    if not p.exists():
        git('ls-files', '--error-unmatch', '--', path)  # 允许已跟踪文件的删除，不忽略未知路径。
for path, expected in fix['files'].items():
    if git('hash-object', '--', path).decode().strip() != expected:
        raise SystemExit('版本修正后又有未核对变更：' + path)
if names(git('diff', '--cached', '--name-only', '-z')) - set(paths):
    raise SystemExit('暂存区含写集外修改；先保留并分离，禁止夹带发布')
subprocess.run([*be, 'set', 'release_write_paths', json.dumps(paths)], check=True)
for path in paths:
    git('add', '--', path)
if git('diff', '--cached', '--name-only', '-z'):
    subprocess.run(['git', 'commit', '-m', 'release(' + version + '): {milestone}'], check=True)
# 全写集断言覆盖 code/、真实记忆及文档，不依赖顶层目录布局。
for path in paths:
    if git('status', '--porcelain', '--untracked-files=all', '--', path):
        raise SystemExit('发布写集未全部入库，禁止打 tag：' + path)
PY
```

> **约定 24**：提交前运行 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet`；rc 3/4 不禁 commit，台账异常修正复核、CICD 欠账补监听，实际级联仅由阶段入口或显式要求触发。

#### Step 3.4.2：打 tag（tag 命名用小写 v SemVer 风格）

**命名**：新 tag 统一小写 `v` + SemVer（`V0.1.0` → `v0.1.0`）；历史 `V*` / `release-V*` 不改，前版识别仍覆盖三种风格。

**Step 3.4.2.1–3：检测 → 授权 → 建 tag/分支须在同一 Bash 块**。撞名保持同名、移动到本次发布提交，不加后缀；移动已有远端 tag 须明确授权。`REPUBLISH` 仅表示撞名，`FORCE_AUTHORIZED` 才是强推授权，两者不得合并。跨围栏变量经 baseline 落盘，由 3.4.3 读回（理据见 `rationale.md`）。

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
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version);; esac
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
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
  python3 {{AIDP_HOME}}/scripts/release_debt.py add --version "$VERSION" --step 3.4.2 \
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

> 版本分支用大写 `V`（`V0.1.0`），与小写 `v` tag 区分；`--no-tag` 整段跳过 3.4.2，不生成 tag/分支。

#### Step 3.4.3：自动推送 commit + tag + 版本分支

```bash
# ★ 自取版本号（见 rationale）
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version);; esac
[ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
BUILD=$($BE --version "$VERSION" get current_build --default "")
if [ -n "$BUILD" ]; then
  BASE_REF=$($BE --version "$VERSION" --build "$BUILD" get push_base_ref --default "")
else
  BASE_REF=$($BE --version "$VERSION" get release_push_base_ref --default "")
fi
# 三处 push 分别捕获失败；落盘并阻断后续探针/发布完成声明。
PUSH_FAILED=""
# baseline 读回推送口径；仅撞名且本次明确授权时允许 -f。
TAG_NAME=$($BE --version "$VERSION" get release_tag_name --default "")
BRANCH_NAME=$($BE --version "$VERSION" get release_branch_name --default "")
REPUBLISH=$($BE --version "$VERSION" get release_republish --default 0)
# ★ 网络操作前原子消费授权：成功、失败或中途中断均不会把授权留给下一次发布。
FORCE_AUTHORIZED=$($BE --version "$VERSION" take release_force_authorized --default 0) || exit 1
if [ "$REPUBLISH" = "1" ] && [ "$FORCE_AUTHORIZED" = "1" ]; then PUSH_F="-f"; else PUSH_F=""; fi
git push origin "$(git symbolic-ref --short HEAD)" || PUSH_FAILED="commit"
# 用 if 区分未创建与推送失败，不能用 &&/|| 混判。
if [ -n "$TAG_NAME" ]; then
  # 保护策略拒绝强推时的降级仍在本围栏内，沿用已消费的本次授权；不跨 tick 持久化。
  if ! git push $PUSH_F origin "$TAG_NAME" 2>memory/.aidp/release-tag-push.err; then
    cat memory/.aidp/release-tag-push.err >&2
    if [ "$PUSH_F" = "-f" ] && grep -Eq 'pre-receive hook declined|Access denied|remote rejected' memory/.aidp/release-tag-push.err; then
      git push origin ":refs/tags/$TAG_NAME" && git push origin "$TAG_NAME" \
        || PUSH_FAILED="${PUSH_FAILED:+$PUSH_FAILED,}tag"
    else
      PUSH_FAILED="${PUSH_FAILED:+$PUSH_FAILED,}tag"
    fi
  fi
fi
if [ -n "$BRANCH_NAME" ]; then
  git push $PUSH_F origin "$BRANCH_NAME" || PUSH_FAILED="${PUSH_FAILED:+$PUSH_FAILED,}branch"
fi
# 授权已在首次 push 前消费，后续失败处置不得凭历史位继续强推 / 删除远端 ref。
if [ -n "$PUSH_FAILED" ]; then
  $BE --version "$VERSION" set release_push_failed "$PUSH_FAILED" >/dev/null 2>&1 || true
  echo "⛔ 推送失败（$PUSH_FAILED）→ 转 Step 3.4.4 失败处置（release-7c.md）"
  exit 1
fi

PUSH_COMMIT=$(git rev-parse HEAD)
# 同一提交重入沿用首次 push 时刻，避免每次降级都重新等满。
PUSH_AT=$($BE --version "$VERSION" get release_push_at --default "")
if [ -z "$PUSH_AT" ] || [ "$($BE --version "$VERSION" get release_push_commit --default "")" != "$PUSH_COMMIT" ]; then
  PUSH_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  $BE --version "$VERSION" set release_push_commit "$PUSH_COMMIT" release_push_at "$PUSH_AT" || exit 1
fi
# 现场只读分类（classify_push.py 不落盘）；仅明确 skip 才免监听，失败/缺字段 fail-closed 按正式代码
DECISION=$(python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --base-ref "$BASE_REF" --head "$PUSH_COMMIT" --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision"))') || DECISION=watch
CICD_SKIPPED=false
[ "$DECISION" = "skip" ] && CICD_SKIPPED=true
if [ "$CICD_SKIPPED" = "true" ]; then
  echo "✅ 发布 push 判定为 docs-only → 不触发 CICD、不监听、不跑就绪探针"
else
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
  # --shell 仅输出 TARGET_VERSION，本块重取 VERSION。
  VERSION="{version}"
  [ -z "$VERSION" ] || case "$VERSION" in "{version}") VERSION="${TARGET_VERSION:-}";; esac
  [ -n "$VERSION" ] || { echo "⛔ 取不到版本号"; exit 1; }
  BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
  # 部署决策取 PRD frontmatter。
  PRD_FILE=$(find "docs/requirements/$VERSION/产品提供" -maxdepth 1 -name '*.md' 2>/dev/null | sort | head -1)
  yml() { [ -n "$PRD_FILE" ] && awk -v k="$1" '/^---$/{f=!f;next} f && $1==k":"{print $2;exit}' "$PRD_FILE"; }
  # local / none 无云端流水线，直接归档。
  DEP_MODE=$(yml mode); [ -n "$DEP_MODE" ] || DEP_MODE="none"
  if [ "$DEP_MODE" = "local" ] || [ "$DEP_MODE" = "none" ]; then
    echo "ℹ️ deployment.mode=$DEP_MODE（无云端流水线）→ 跳过 CICD 监听与就绪探针，直接进 Step 3.5"
  else
  CICD_ENV=$(yml cicd_env); [ -n "$CICD_ENV" ] || CICD_ENV="prod"
  CLOUD_HEALTH_URL=$(yml cloud_ready_api_url)
  CLOUD_AUTH_URL=$(yml cloud_ready_login_url)
  # 鉴权探针需同时提供 URL 与凭证。
  AUTH_HEADER=$(yml cloud_ready_auth_header)
  CLOUD_DEPLOY_TIMEOUT=$(yml cloud_deploy_check_timeout_seconds); [ -n "$CLOUD_DEPLOY_TIMEOUT" ] || CLOUD_DEPLOY_TIMEOUT=300
  [ -n "$CLOUD_HEALTH_URL" ] || { echo "⛔ 缺少部署就绪 health URL，fail-closed"; exit 1; }
  WATCH_RC=0
  WATCH_JSON=$(python3 {{AIDP_HOME}}/scripts/cicd_watch.py --commit "$PUSH_COMMIT" --env "$CICD_ENV" \
    --version "$VERSION" --push-at "$PUSH_AT") || WATCH_RC=$?
  while :; do
    ACTION=$(printf '%s' "$WATCH_JSON" | jq -er '.next_action') || exit 1
    CICD_STATUS=$(printf '%s' "$WATCH_JSON" | jq -r '.verdict // "unknown"')
    case "$WATCH_RC" in
      0|1|2) ;;
      3) ACTION=probe; CICD_STATUS=unknown ;; # 未接入/CLI 不可用，保留原原因
      4) [ "$ACTION" = probe ] && printf '%s' "$WATCH_JSON" | jq -e '.degraded == true' >/dev/null || exit 1
         CICD_STATUS=unknown ;; # 推送即自动部署：只放行探针，不冒充流水线成功
      *) echo "⛔ cicd_watch 异常 rc=$WATCH_RC，禁止宣告发布完成"; exit 1 ;;
    esac
    EVIDENCE=$(printf '%s' "$WATCH_JSON" | CICD_STATUS="$CICD_STATUS" PUSH_COMMIT="$PUSH_COMMIT" PUSH_AT="$PUSH_AT" jq -c '. + {status:env.CICD_STATUS, push_commit:env.PUSH_COMMIT, push_at:env.PUSH_AT}') || exit 1
    $BE --version "$VERSION" set release_cicd "$EVIDENCE" || exit 1
    [ "$CICD_STATUS" != unknown ] || echo "⚠️ CICD 未确认：$EVIDENCE；部署结果另由探针判定"
    case "$ACTION" in
      poll)
        # 继续 poll 同一运行与提交。
        RUN_ID=$(printf '%s' "$WATCH_JSON" | jq -r '.run_id // empty')
        [ -n "$RUN_ID" ] || { echo "⛔ cicd_watch 返回 poll 但缺 run_id"; exit 1; }
        WATCH_RC=0
        WATCH_JSON=$(python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode poll --run-id "$RUN_ID" \
          --commit "$PUSH_COMMIT" --env "$CICD_ENV" --version "$VERSION" --push-at "$PUSH_AT") || WATCH_RC=$? ;;
      probe)
        python3 {{AIDP_HOME}}/scripts/autopilot-deploy-watch.py \
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
        # prod 禁止自动重跑。
        case "$CICD_ENV" in
          prod|production)
            echo "⛔ 生产环境 CICD 失败：禁止自动重跑，请用户确认后手动重跑（commit=$RETRY_COMMIT）"; exit 1 ;;
        esac
        RUN_ID=$(printf '%s' "$WATCH_JSON" | jq -r '.run_id // empty')
        # 缺运行 ID 不得重试。
        [ -n "$RUN_ID" ] || { echo "⛔ cicd_watch retry 未返回 run_id —— 重试链中止"; exit 1; }
        RETRY_JSON=$(python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode retry --run-id "$RUN_ID" --env "$CICD_ENV" \
          --version "$VERSION") || { echo "⛔ 重试被拒：$RETRY_JSON"; exit 1; }
        $BE --version "$VERSION" bump cicd_run.cicd_retry_count
        NEW_RUN_ID=$(printf '%s' "$RETRY_JSON" | jq -r '.run_id // empty')
        # 监听返回统一交循环顶部按 rc + next_action 分流。
        WATCH_RC=0
        if [ -n "$NEW_RUN_ID" ]; then
          WATCH_JSON=$(python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode poll --run-id "$NEW_RUN_ID" \
            --commit "$RETRY_COMMIT" --env "$CICD_ENV" --version "$VERSION" --push-at "$PUSH_AT") || WATCH_RC=$?
        else
          # 不回显新 id → 按原 commit 重新锁定
          WATCH_JSON=$(python3 {{AIDP_HOME}}/scripts/cicd_watch.py --commit "$RETRY_COMMIT" --env "$CICD_ENV" \
            --version "$VERSION" --push-at "$PUSH_AT") || WATCH_RC=$?
        fi
        ;;
      trigger)
        echo "⛔ 发布 push 未触发 CICD；生产环境禁止自动 trigger，请用户确认后手动触发"; exit 1 ;;
      abort|*)
        echo "⛔ CICD 监听未完成（next_action=$ACTION）→ 禁止宣告发布完成"; exit 1 ;;
    esac
  done
  fi
fi
```

> ★ **推送分类与监听（约定 31.5）**：分类现场只读、不落盘，基准取 build 的 `push_base_ref`（无 build 取版本级 `release_push_base_ref`）。
> Step 3.6 读取版本级 `release_cicd`：`status=unknown` 时列出原原因与 `degraded`；探针通过不能写成「流水线已确认成功」。
> **发布期禁止自动 trigger**：仅用户主动要求时执行 `python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode trigger --env <env> --ref <branch>`；`cicd.provider=none` 或无 `cicd.pipelines` 时不适用。理据见 `rationale.md`。

#### Step 3.4.4：失败处置

> 📄 **本步全文见 `release-7c.md`**（push 被拒 / rebase 冲突 / tag 撞名 / 强推被保护策略拒 / CICD 失败重试 ≤3 等分支）。
> 进入本步第一动作 = Read 该文件。
