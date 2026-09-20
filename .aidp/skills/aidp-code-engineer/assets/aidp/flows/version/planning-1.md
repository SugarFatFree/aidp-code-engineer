# /version · 版本规划流程详情 — 分片 1/8

> 本片覆盖：**头部 + Step 2.0 输入快照 / 2.1 校验参数 / 2.1.5 派生里程碑名**。
> 完整分片清单见 `.aidp/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
> （原整段标题「/version · 版本规划流程详情（Step 2.0–2.8，情况 A 全量 / B-2 补充）」—— 该范围现由 1/8…8/8 全部分片共同承载，本片只覆盖上面「本片覆盖」列出的部分）

> 本文件是 `/version` 命令 **版本规划流程（情况 A 全量 / B-2 补充）** 详情的**第 1/8 片**（⛔ 本片不含 版本规划流程 全部子步——其余在 `-2`…`-8` 分片，按进度依次 Read，勿读完本片即认为已覆盖全段）（Step 2.0–2.8），由命令主体（`.aidp/commands/version.md`）在**进入版本规划流程时用 Read 工具按需加载**——把这 1000+ 行从"每次调用整体入上下文"改为"走到规划流程才载"，降低"lost in the middle"式漏步。命令主体只保留本段的**硬门提醒 + Step 2.0–2.8 骨架表 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入版本规划流程后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤（尤其 Step 2.4.7 版本规划产物全量审计的强制执行铁律）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/version/`。理据/根因见同目录 `rationale.md`。

---

### Step 2.0：★ 输入快照管理

**目的**：精确检测产品在版本开发中途修改了 **PRD 或原型**，触发"补充文档生成"而非"覆盖主文档"。

**快照文件**：`memory/{version}/.aidp-inputs-snapshot.json`（**进 git** — 不在 .gitignore 中；删除会让下次 /version 误判为 fresh）

**结构**：

```json
{
  "snapshot_at": "2026-05-10T10:15:00+08:00",
  "snapshot_run": "fresh",            // fresh / supplement-01 / supplement-02 / rescued-fresh
  "prd_files": [
    {
      "path": "docs/requirements/{version}/产品提供/PRD-XX系统.md",
      "sha256": "<完整 hash>",
      "mtime": "2026-05-09T15:30:00+08:00"
    }
  ],
  "prototype_files": [
    {
      "path": "docs/prototype/{version}/code/login.html",
      "kind": "code",                    // code / mockup
      "sha256": "<完整 hash>",
      "mtime": "2026-05-09T15:30:00+08:00"
    },
    {
      "path": "docs/prototype/{version}/mockup/列表页.png",
      "kind": "mockup",
      "sha256": "<完整 hash>",
      "mtime": "2026-05-09T15:30:00+08:00"
    }
  ],
  "code_files": [                          // 代码作为最终事实源
    {
      "path": "code/backend/{后端项目}/src/main/java/.../UserController.java",
      "kind": "backend-controller",        // backend-controller / backend-entity / backend-sql / frontend-router / frontend-page
      "sha256": "<完整 hash>",
      "mtime": "2026-05-12T10:15:00+08:00"
    },
    {
      "path": "docs/deployment/{version}/sql/增量/01_用户表DDL.sql",
      "kind": "backend-sql",
      "sha256": "<完整 hash>",
      "mtime": "2026-05-12T10:15:00+08:00"
    },
    {
      "path": "code/frontend/{前端项目}/src/router/index.ts",
      "kind": "frontend-router",
      "sha256": "<完整 hash>",
      "mtime": "2026-05-12T10:15:00+08:00"
    }
  ]
}
```

**三类输入的扫描范围**：

| 类 | glob | 备注 |
|---|------|------|
| PRD | `docs/requirements/{version}/产品提供/**/*.md` | 含子目录、docx→md 转换稿 + sprint-dev 累进时写的「口述补充-{ts}.md」「sprint-{NNN}-开发期补充-{ts}.md」 |
| 原型代码 | `docs/prototype/{version}/code/**/*.{html,vue,jsx,tsx,css,js,ts,wxml,wxss}` | HTML/Vue/React 等；二进制资源不计 |
| 高保真原型 | `docs/prototype/{version}/mockup/**/*.{png,jpg,jpeg,gif,svg,pdf,fig,sketch,xd}` | 图片 / PDF / 设计源文件 |
| **代码结构性文件**| 见下表 | 仅扫**结构性**文件（接口/实体/路由），不扫业务逻辑代码 — 避免每次代码改动都触发补充模式 |

**代码扫描的精确 glob**（避免噪音）：

| 子类 | glob |
|------|------|
| backend-controller | `code/backend/*/src/main/java/**/*{Controller,Resource,Handler,Endpoint}.java` / `code/backend/*/{src/,}**/{controllers,routes}/**/*.{js,ts,py}`（旧扁平 `code/server/` upgrade 兼容）|
| backend-entity | `code/backend/*/src/main/java/**/*{Entity,Domain,Model,DO}.java` / `code/backend/*/**/models/**/*.{js,ts,py}`（旧扁平 `code/server/` upgrade 兼容）|
| backend-sql | `docs/deployment/{version}/sql/增量/**/*.sql` + `docs/deployment/{prev-version}/sql/增量/**/*.sql` |
| frontend-router | `code/frontend/*/src/router/**/*.{ts,js}` / `code/frontend/*/{src/,}{app,pages}/**/page.{tsx,jsx}`（旧扁平 `code/web/` upgrade 兼容）|
| frontend-page | `code/frontend/*/src/{views,pages}/**/*.{vue,tsx,jsx}`（旧扁平 `code/web/` upgrade 兼容）|
| **backend-config** | `code/**/application*.{yml,yaml,properties}` / `code/**/bootstrap*.{yml,yaml,properties}` / `code/**/{config,settings}.{json,toml,ini,py}` |
| **frontend-config** | `code/**/.env*` / `code/**/vite.config.*` / `code/**/webpack.config.*` |
| **deployment-config** | `env/.env*` / `docs/deployment/{version}/**/*.{conf,yaml,yml}`（nginx / docker-compose / k8s 等） |

> **不扫**业务逻辑、工具函数、组件库、单元测试 — 这些日常修改不应触发整套补充流程。
>
> **三类 config 子类的特殊语义**：变化触发 B-2 补充模式时，sprint-design Step 0.3 四象限「③ 代码超前-补写」**额外触发** /sprint-dev Step X.7 流程更新 `docs/deployment/{version}/配置文件/增量/配置项清单*.md`——配置变化在两份文档同时记录：事实清单（设计/开发视角，精挑路径/端口）+ 配置项清单（运维视角，全量 key），互相在「说明」列引用对方。详见 memory `config-manifest-runtime-doc.md` 与事实清单关系矩阵。

**算法**：

1. **fresh 模式**（情况 A）：本步先跳过；待 Step 2.4.x 全部成功后，在 Step 2.7.5 生成 `.aidp-inputs-snapshot.json`（`snapshot_run: "fresh"`）
2. **补充模式**（情况 B-2）：
   - 读取 `.aidp-inputs-snapshot.json`（如不存在但当前已有输入 + 至少一份主文档 → 视为"补丁基线缺失"，把当前输入作为基线先写一份 `snapshot_run: "rescued-fresh"` 防止下次再误判）
   - 计算当前 PRD / 原型 / **代码结构性文件**三类的 sha256
   - 与快照逐项比对，生成**三份**"变更文件清单"（PRD 变更 / 原型变更 / **代码变更**）；每份内部再分新增 / 修改 / 删除
   - 记入临时变量 `{prd_diff_files}` + `{prototype_diff_files}` + `{code_diff_files}`，传给 Step 2.4.0
   - **代码变更触发的语义**：代码变化 = "/sprint-dev 累进或开发期回写漏了文档"，本轮 /version 通过 sprint-design Step 0.3 四象限「③ 代码超前-补写」自动追平设计文档；不需要用户提供新 PRD
   - Step 2.4.x 完成后，更新快照：`snapshot_run: "supplement-NN"`（NN 由本目录已有增量文档 `NN_*.md`（当前规范，`00_索引.md` 类型=补充；含历史 `NN_补充-*.md` / `*-补充-*.md`）数量 +1 决定）

**Bash 实现提示**：

```bash
# PRD 当前 sha256（按文件路径排序，便于稳定比对）
find docs/requirements/{version}/产品提供 -name '*.md' -type f | sort | xargs sha256sum

# 原型代码 sha256
find docs/prototype/{version}/code -type f \
  \( -name '*.html' -o -name '*.vue' -o -name '*.jsx' -o -name '*.tsx' \
     -o -name '*.css' -o -name '*.js' -o -name '*.ts' \
     -o -name '*.wxml' -o -name '*.wxss' \) \
  | sort | xargs sha256sum 2>/dev/null

# 高保真原型 sha256（二进制）
find docs/prototype/{version}/mockup -type f \
  \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.gif' \
     -o -name '*.svg' -o -name '*.pdf' -o -name '*.fig' -o -name '*.sketch' -o -name '*.xd' \) \
  | sort | xargs sha256sum 2>/dev/null

# 代码结构性事实 sha256（★ 取 code_inventory 的产物，⛔ 不逐文件 hash 整个 code/：
#   大仓会很慢，而清单本就已把「设计关心的事实」摘出来了，它变了即代表事实变了）
[ -f memory/_facts/code-inventory.json ] \
  && sha256sum memory/_facts/code-inventory.json \
  || echo "unavailable  memory/_facts/code-inventory.json"   # ⛔ 取不到 ≠ 代码没变
```

### Step 2.1：校验参数 + 第二参数分流

- {version} 必须提供（格式 `V{major}.{minor}.{patch}`）；缺失或格式不合法 → 停止并按 06 §6 重问
- 第二参数 `$2`（**可选自由文本**）的分流规则：

| `$2` 状态 | 命令端判定 | 后续路径 |
|----------|-----------|---------|
| 未提供 / 空字符串 | 占位 `{里程碑} = <AUTO_NO_HINT>` | Step 2.1.5 走 P1/P2/P3 派生 |
| 匹配 `^M\d+[\s:：]` 正则（如 `"M1 MVP"` / `"M2：用户中心"`） | 视为**已规范**的里程碑名 | 直接采用 `{里程碑} = $2`，跳过 Step 2.1.5 |
| 不匹配 `^M\d+` 正则（如 `"新增用户登录与权限"` / `"修复支付若干 bug"`） | 视为**版本描述**自由文本 | 占位 `{里程碑} = <AUTO_FROM_HINT:$2>`，Step 2.1.5 把 `$2` 作为 P0 最高优先级的派生依据 |

```bash
ARG2="$2"   # 第二参数原文
if [ -z "$ARG2" ]; then
  MILESTONE_MODE="AUTO_NO_HINT"
elif echo "$ARG2" | grep -qE '^M[0-9]+[[:space:]:：]'; then
  MILESTONE="$ARG2"
  MILESTONE_MODE="EXPLICIT"
else
  USER_HINT="$ARG2"
  MILESTONE_MODE="AUTO_FROM_HINT"
fi
```

### Step 2.1.5：★ 自动派生里程碑名称（仅当 Step 2.1 模式为 `AUTO_NO_HINT` 或 `AUTO_FROM_HINT` 时执行）

> 设计意图：让用户用最低负担启动版本规划。无论用户给的是规范里程碑名、版本描述自由文本，还是什么都不给，命令端都能产出符合 `M{N}：<摘要>` 格式的里程碑名。

**派生规则**（按优先级，先命中先用）：

```bash
# ⛔ `MILESTONE_MODE` / `USER_HINT` 赋在 Step 2.1 的围栏（另一次 Bash 调用），跨不过来。
#    取空 ⇒ 下面「优先级 0」分支**结构上不可达** ⇒ `/version V0.1.0 "新增用户登录"` 里那句
#    自由文本永远不会被当成里程碑摘要来源，静默回落到低优先级派生。故就地重解析一次。
ARG2="$2"
if [ -z "$ARG2" ]; then MILESTONE_MODE="AUTO_NO_HINT"
elif echo "$ARG2" | grep -qE '^M[0-9]+[[:space:]:：]'; then MILESTONE="$ARG2"; MILESTONE_MODE="EXPLICIT"
else USER_HINT="$ARG2"; MILESTONE_MODE="AUTO_FROM_HINT"; fi

# Step A：确定 M 编号 — 数已有版本目录的数量 + 1
M_NUM=$(ls -d memory/V*/ 2>/dev/null | wc -l)
M_NUM=$((M_NUM + 1))

# Step B：抽取一句话摘要（≤ 12 字中文），按优先级 0→1→2→3 取
SUMMARY=""
SOURCE=""

# 优先级 0（最高）：用户在第二参数提供了版本描述自由文本 → 直接抽取摘要
#   适用场景：MILESTONE_MODE == "AUTO_FROM_HINT"
if [ "$MILESTONE_MODE" = "AUTO_FROM_HINT" ] && [ -n "$USER_HINT" ]; then
  # 自由文本可能是一句话或一小段；剥离版本号 / 项目名等噪声后取前 12 字
  SUMMARY=$(echo "$USER_HINT" \
    | sed -E 's/[Vv][0-9]+(\.[0-9]+){0,2}(版本)?//g; s/^[[:space:]]+//; s/[[:space:]]+$//' \
    | head -c 36)
  SOURCE="用户在第二参数提供的版本描述"
fi

# 优先级 1：已有研发需求.md（情况 B-2 补充模式 / 同时再跑 fresh 模式）→ 取一级标题或首段第一句
if [ -z "$SUMMARY" ]; then
  REQ_FILE=""
  for cand in "docs/requirements/{version}/研发需求/01_研发需求.md" "docs/requirements/{version}/研发需求/00_研发需求.md" "docs/requirements/{version}/研发需求/研发需求.md" "docs/requirements/{version}/研发需求/00_索引.md"; do
    [ -f "$cand" ] && REQ_FILE="$cand" && break
  done
  if [ -n "$REQ_FILE" ]; then
    SUMMARY=$(head -30 "$REQ_FILE" | grep -m1 -E '^# [^#]' | sed -E 's/^# +//; s/研发需求[:：]?//; s/[Vv][0-9]+(\.[0-9]+){0,2}(版本)?//g; s/^[[:space:]]+//; s/[[:space:]]+$//' | head -c 36)
    [ -n "$SUMMARY" ] && SOURCE="研发需求.md 一级标题（$REQ_FILE）"
  fi
fi

# 优先级 2：fresh 模式下研发需求.md 还未生成，但 PRD 已存在 → 取首个 PRD 的一级标题
if [ -z "$SUMMARY" ]; then
  PRD_FIRST=$(find docs/requirements/{version}/产品提供 -maxdepth 3 -name '*.md' -type f 2>/dev/null | sort | head -1)
  if [ -n "$PRD_FIRST" ]; then
    SUMMARY=$(head -30 "$PRD_FIRST" | grep -m1 -E '^# [^#]' | sed -E 's/^# +//; s/PRD-?//; s/产品需求文档[:：]?//; s/[Vv][0-9]+(\.[0-9]+){0,2}(版本)?//g; s/^[[:space:]]+//; s/[[:space:]]+$//' | head -c 36)
    [ -n "$SUMMARY" ] && SOURCE="PRD 一级标题（$PRD_FIRST）"
  fi
fi

# 优先级 3：兜底 — 用版本号本身
if [ -z "$SUMMARY" ]; then
  SUMMARY="{version} 版本规划"
  SOURCE="兜底（无 PRD / 研发需求 / 用户描述）"
fi

MILESTONE="M${M_NUM}：${SUMMARY}"
```

**派生摘要的边界规则**：
- 长度上限 12 个中文字符（约 36 字节）；超过则用 `head -c 36` 截断
- **优先级 0**：用户传了版本描述自由文本 → 命令端把它作为最佳派生依据（用户最了解本版本要做什么）
- 优先级 1（已有研发需求.md）适用于情况 B-2 补充模式 + 部分情况 A 的二次重跑
- 优先级 2（PRD 一级标题）适用于情况 A fresh 模式 — 这时研发需求.md 还没生成
- 优先级 3 兜底永远命中（即使 PRD 也未提供，至少有版本号本身）
- M 编号是项目内自然递增；用 `memory/V*/` 目录数量推断，避免和已有版本里程碑冲突

**用户确认**（命令端必须执行）：

```
🏷️ 里程碑名称已自动派生：
   {MILESTONE}

派生依据：{SOURCE}
{若 MILESTONE_MODE == AUTO_FROM_HINT，额外追加一行：}
用户原始描述：{USER_HINT}

若希望使用其他里程碑名称，请输入 `abort` 终止后重跑命令并显式传入：
  /version {version} "M{N}：<规范名>"

任何其他输入即视为确认接受派生结果。
```

> ⚠️ **交互式**下命令端**必须**展示派生结果给用户，**不得**静默使用——设计意图是让用户在自动化与可控之间保有最低限度的可见性。
> **★ 无人值守（`--no-tag` / `--unattended`）例外**：不展示、不等输入——**打印派生结果到终端后自动接受**（autopilot Phase 3.1 已从 PRD `autopilot_decisions` 推里程碑参数，此处仅确定性落值），继续后续 Step，**绝不挂起等待用户 `abort`/确认**。

**派生后影响**：`{里程碑}` 变量在后续所有 Step（2.5 / 3.x）的版本表头 / git tag 备注 / 版本发布报告等处都使用此值；与用户显式提供规范里程碑名时行为完全一致。

