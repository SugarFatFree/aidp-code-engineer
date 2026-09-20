# sprint-selftest · Step 3 详情〔1/2〕— 职责隔离 + 跨版本继承 + 合并规则 + 预填逻辑

> 本文件是 `/sprint-selftest` 命令 **Step 3** 的完整详细步骤 **第 1 片（共 2 片）**，覆盖：与 SKILL「研发自测方案」的职责隔离表 / 跨版本环境·账号继承基线定位 bash / 合并规则 1–6（全量继承 + 加法式增量补充）/ 前置目录创建 / 首版 fresh 预填逻辑。**「输出」段引出的完整 Markdown 模板正文（测试工具 / chrome 启动 / 测试环境 / 账号 / DB / 关联文档六段，含远程连接铁律）+ 生成后提示见同目录 `step-3-2.md`**。命令主体在进入 Step 3 时按序 Read 本片与 `step-3-2.md`。
>
> ⚠️ **权威性**：进入 Step 3 后，以本片 + `step-3-2.md` 为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-selftest/step-3-1.md`。理据/根因见同目录 `rationale.md`。

---

### Step 3：★ 生成「测试环境与账号」配置文件（与 SKILL「研发自测方案」职责隔离）

> **职责隔离**（与 SKILL「研发自测方案」职责重新划分）：
> | 文件 | 职责 | 生成方 | 路径 |
> |------|------|--------|------|
> | **测试环境与账号**（本步骤生成） | chrome-devtools-mcp 连接 + 测试 URL + 测试账号（aiauto-test 专用配置入口） | `/sprint-selftest` | `docs/testing/{version}/研发自测/01_测试环境与账号.md` |
> | **研发自测方案**（dev-manual-testcase SKILL 第零步生成） | 范围/执行人/通过准则/缺陷跟踪 + 用例引用闭环 | dev-manual-testcase SKILL（命令端 Step 1 调用后归一） | `docs/testing/{version}/研发自测/01_研发自测方案.md` |
> | **专职索引**（dev-manual-testcase SKILL 第八步生成） | 文档族清单导航（本目录有哪些文件 + 生成时间 + 主/补充标识） | dev-manual-testcase SKILL（命令端 Step 1 调用后归一） | `docs/testing/{version}/研发自测/00_索引.md` |
>
> `/sprint-aiauto-test` Phase 0.0.5 从「测试环境与账号」文件读 chrome 地址、URL、账号，字段齐全时无需交互询问。

> ★ **可选段「六、WebMCP 带参浏览器」的产出规则是二值的**（模板正文见 `step-3-2.md`）：
> 先跑 `python3 .aidp/scripts/check_webmcp.py --detect --json`——`enabled: false`（默认、绝大多数项目）
> → **整段不写入生成的文件**（不留空壳、不留占位标题）；`enabled: true` → **本段即为必填**，
> 且须填**真实可复制执行**的启动命令（含两个浏览器开关 + 独立 `--user-data-dir`）+ 两行自检，
> ⛔ 不接受只留占位符。机器回检 = `check_webmcp.py` 的 `testenv-section` 项（**只判最新版本那一份**，
> 旧版本写于启用之前、没有该段属正常，不连坐）。

**跳过条件（append-only 感知，非整份跳过）**：`docs/testing/{version}/研发自测/01_测试环境与账号.md` 已存在时——**已填写的字段值一律不覆盖**（保护现场手工填写）；但仍按下方「合并规则 2」检测本版**新增**且文件中**确无**对应条目的系统/角色/URL/库并**追加补充**（append-only），无新增则等价跳过。**绝不改动、绝不删除已有条目**。

**★ 跨版本环境/账号继承 = 全量继承 + 加法式增量补充（默认补充、非覆盖；除非本版明确改/删）**：环境与账号跨版本通常稳定，故本版**默认全量继承上一版本已填的「环境 + 账号 + 系统 + DB」全部内容**，再把**本版新增**部分**追加**上去——**除非本版对上一版某条信息做了明确修改或删除，否则一律按"补充"处理：上版信息全部保留、不重填、不丢弃**。判定基线 = 上一版本 `01_测试环境与账号.md`（下方 bash 定位 `PREV_ENV_FILE`）+ 本版 PRD `autopilot_decisions.deployment` / 研发需求·详细设计（新增联动系统 / 新角色 / 新 URL / 新库的来源）。`PRD_ENV_EXPLICIT` 仅表征"PRD 是否显式给了本版环境字段"（供「合并规则 3 修改」用），**不再作为"整份复用 vs 整份覆盖"的开关**。

```bash
CUR_V="{version}"
CUR_ENV="docs/testing/$CUR_V/研发自测/01_测试环境与账号.md"
mkdir -p "docs/testing/$CUR_V/研发自测/"
# 取「严格小于当前版本」且已存在该配置文件的最近一个版本（SemVer 倒序取最大者）
PREV_ENV_FILE=""; PREV_V=""
for d in $(ls -d docs/testing/V*/ 2>/dev/null | sed -E 's#.*/(V[^/]+)/#\1#' | sort -V); do
  [ "$d" = "$CUR_V" ] && continue
  [ "$(printf '%s\n%s\n' "$d" "$CUR_V" | sort -V | head -1)" = "$d" ] || continue   # 只留 < 当前版本
  [ -f "docs/testing/$d/研发自测/01_测试环境与账号.md" ] && PREV_ENV_FILE="docs/testing/$d/研发自测/01_测试环境与账号.md" && PREV_V="$d"
done
# 本版本是否明确指定新环境（PRD deployment 显式给了 URL）
PRD_FILE=$(ls docs/requirements/$CUR_V/产品提供/*.md 2>/dev/null | head -1)
PRD_ENV_EXPLICIT=0
[ -n "$PRD_FILE" ] && awk '/^---$/{f=!f;next} f && /local_frontend_url:|cloud_deploy_url:/{print; exit}' "$PRD_FILE" | grep -q . && PRD_ENV_EXPLICIT=1
```

**合并规则（有上版配置 → 加法式补充；无上版 = 首版走 fresh 模板）**：
1. **全量继承基线**：`cp "$PREV_ENV_FILE" "$CUR_ENV"`（上版**所有段**——chrome 连接 / 测试环境 URL / 测试账号 / DB 连接，含各系统各角色——原样搬来），首行改为 `# 测试环境与账号 — {version}`。**这一步无条件做**（不再区分 `PRD_ENV_EXPLICIT`）。
2. **本版新增 → 追加**（绝不动上版已有条目）：从本版 PRD `deployment` + 研发需求 / 详细设计识别本版**新引入**的联动系统 / 角色 / URL / 库 → 在对应段（三、测试环境 / 四、测试账号 / 五、DB 连接，模板正文见 `step-3-2.md`）**追加新块/新行**（值用占位符，复用下方「预填逻辑」的 PRD 取值源填已知项）。上版已有的同名条目**不重复追加**。
3. **本版明确修改 → 只覆盖该字段**：仅当本版 PRD/设计**显式**改了某条已有信息（如某 URL 变更、某角色口令策略变更，`PRD_ENV_EXPLICIT=1` 且指向已有字段）→ **只覆盖该字段**，同段其余上版值保留。
4. **本版明确删除 → 删条目 + 留痕**：仅当本版 PRD/设计**显式声明**移除某系统/角色 → 删对应条目，并在文件头留一行 `> 🗑 {条目} 于 {version} 移除：{理由}`。
5. **默认（未显式改/删）→ 上版信息全部保留**：一律视为本版仍有效的补充基线，不重填、不删除、不"因为本版没提到就清空"。
6. **文件头继承标记**（替代旧单行标记）：`> ♻️ 继承自 {PREV_V} 全部环境/账号；本版补充：{新增系统/角色/URL 列表，无则"无"}｜修改：{或"无"}｜移除：{或"无"}（未列出项一律沿用上版、不重填不删除；如本版环境确有变更，就地更新对应段后再跑 /sprint-aiauto-test）`。**完成本步，跳过下方「预填逻辑」+ `step-3-2.md`「输出」的 fresh 模板生成**（预填逻辑仅在"追加新条目"与"首版 fresh"时按需取值）。
- **无上版配置（首版）** → 走下方「预填逻辑」+ `step-3-2.md`「输出」生成 fresh 模板（首版正常路径）。

**前置目录创建**：`mkdir -p docs/testing/{version}/研发自测/`（研发自测用例落 `研发自测/`；`正式用例/` 是测试人员领域，AIDP 不写）

**预填逻辑（★ 首版 fresh 生成路径执行整份；有上版继承时【仅供合并规则 2「追加新条目」取已知值】，不重生成整份文件）**（命令端 Bash，预填已知字段）：

```bash
# 从 PRD autopilot_decisions 预填 deployment URL（如有）
PRD_FILE=$(ls docs/requirements/{version}/产品提供/*.md 2>/dev/null | head -1)
DEPLOY_URL_PREFILL="<请填写，如 http://test.example.com/app/console>"
if [ -n "$PRD_FILE" ]; then
  URL_CAND=$(awk '/^---$/{f=!f;next} f && /local_frontend_url:|cloud_deploy_url:/{print $2;exit}' "$PRD_FILE" | tr -d '"' | xargs)
  [ -n "$URL_CAND" ] && DEPLOY_URL_PREFILL="$URL_CAND"
fi

# 从 PRD user_roles 预填角色行（如无，默认 admin + 普通用户两行）
ROLES_PREFILL=$(awk '/^---$/{f=!f;next} f && /user_roles:/{p=1;next} p && /^\s*-/{gsub(/^\s*-\s*/,""); print; next} p && !/^\s*-/{p=0}' "$PRD_FILE" 2>/dev/null)
```

