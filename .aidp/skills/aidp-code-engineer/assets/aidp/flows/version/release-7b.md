<!-- 二次切分 · release 片7b：覆盖 Step 3.5 更新项目记忆文件 / 3.6 输出发布报告-->
# /version · 执行分片（Step 3.5 更新项目记忆文件 / 3.6 输出发布报告）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/version/release-7b.md`。理据见同目录 `rationale.md`。

> 本文件由 `release-7.md` 超 20480B 上限二次切分而来（同 `phase-0-6b.md` 惯例）。
> 进入 Step 3.5 前先 Read 本片，逐项执行、不凭骨架或记忆略过。理据见同目录 `rationale.md`。

---

### Step 3.5：更新项目记忆文件「当前状态」

- 项目记忆文件（`agent_env.py memory-file` 取路径）「当前状态」增加一条发布记录：正式发布注明「✅ 已发布」；`--no-tag` 准发布注明「🟡 已准发布（未打 tag）」（⛔ 不得写已发布，否则正式 `/version` 会被误判为情况 C）。

### Step 3.5bis：★ baseline 历史版本归档（打完 tag 即搬，`--no-tag` 准发布不触发）

**触发时机 = 正式发布打完 tag 这一刻**——此刻这个版本不会再变，它之前那些版本的 `versions.<V>`
明细（`builds[]` 是大头）也就永不再写。不搬走的话，两条 `/loop` 每次 `baseline_edit.py`
都要持 flock 全量读写这份只增不减的文件，而其中绝大部分是历史。

**主文件留墓碑、不删节点**：`baseline_archive.py` 只把 bulk 搬进
`memory/.aidp-baseline-archive/baseline-<V>.json`，`internal_released_at` 等被状态机与选版
判据消费的标量原样留在主文件。⛔ **整段删 `versions.<V>` 是错的**：Phase 0.3.3 的 S2 判据是
「计划在 + Sprint 全 ✅ + `internal_released_at` **为空**」，取空会让一个早已发布的版本重新命中
S2 被选作准发布候选。保留键清单与读方回落以脚本为单一信源，命令端不复述、不另写搬运逻辑。

```bash
# ⛔ 跨围栏自取版本号（写法同 release-7c.md）
VERSION="{version}"; case "$VERSION" in "{version}"|"") VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version);; esac
TAG="v${VERSION#V}"
if [ -n "$VERSION" ] && [ -n "$(git tag -l "$TAG")" ]; then
  python3 {{AIDP_HOME}}/scripts/baseline_archive.py --dry-run   # 先看清要搬哪些（只报不写）
  python3 {{AIDP_HOME}}/scripts/baseline_archive.py             # 落盘：明细先写归档、再把主文件改成墓碑
  git add memory/.sprint-autopilot-baseline.json memory/.aidp-baseline-archive/ 2>/dev/null
  # ★ 归档文件必须入库：baseline 本体就是团队共享的，只在本机留归档 = 换台机器历史就没了
  git diff --cached --quiet || git commit -m "chore(baseline): 归档 $VERSION 之前已发布版本的明细"
else
  echo "⏭️ 本次未打 tag（--no-tag 准发布）→ 跳过 baseline 归档"
fi
```

- 归档失败 / 未归档**不阻断发布**：它是体积治理、不是发布正确性的一部分；失败时按
  「失败兜底可追溯铁律」`release_debt.py add --step 3.5bis`，下次发布自动重试（幂等）。

### Step 3.6：输出发布报告

> ⛔ **顶部欠账块（存在未决条目时必打，不得省）**：`python3 {{AIDP_HOME}}/scripts/release_debt.py list --version {version} --open --json` 的 `count > 0` 时，
> **在「🎉 发布成功」之前**先输出下面这段——否则一次攒下三条欠账的发布，终端仍打完整的成功话术、
> 一个字不提，而 `--finalize-docs` / `--rebuild-baseline` 都以「开始先读发布欠账.md」为驱动。
>
> ```
> ⚠️ 本次发布有 {N} 项未决欠账（已登记 docs/audit/{version}/发布欠账.md）：
>   · [{步骤}] {定位} —— {原因} → 补跑：{命令}
>   …
>   ⛔ 未决项不阻断发布，但**必须有人跟进**；补跑入口见每条末尾。
> ```

```
🎉 版本 {version} 发布成功！

发布时间：YYYY-MM-DD
里程碑：{里程碑}
包含 Sprint：{N} 个
参与开发者：{user 列表}
新增功能：{N} 个
修复 Bug：{N} 个

🏷️ Git 标签：{TAG_NAME}（小写 v 风格，命名规则见 Step 3.4.2）—— {TAG_STATE}
🌿 版本分支：{BRANCH_NAME}（大写 V 风格，与 tag 配套）—— {BRANCH_STATE}
📝 版本更新日志.md：已追加 [{version}] 条目（版本概览表 + 详情区块均倒叙置顶；新增 {N1} 条 / 修复 {N2} 条）
📦 部署产物整理（docs/deployment/{version}/ + 跨版本 docs/deployment/tools/）：
   • SQL 归档：原 {N1} 个文件整合为 {N2} 个文件（守恒校验 ✓），按 NN_ 前缀 + DDL/DML 拆分，99_回滚脚本.sql 保留
   • 部署流程.md：占位符已实值化 / 关键项表已核对 / SQL 引用已对齐整理后文件名
   • 配置项清单.md：敏感 checklist 已核对 · deployment-checklist：{已核对/已生成骨架/无} · 跨文档一致性 ✓
📊 版本测试报告：docs/reports/{version}/版本测试报告/{version}-测试报告.html（单文件，合并 {N} 个 build；per-build 历史见同级 AI测试报告/index.html；若未跑 /sprint-aiauto-test 则自动跳过）

📌 下一步：
/version V?.?.?              # 规划下一个版本（里程碑名由 Step 2.1.5 自动派生）
/version V?.?.? "M? ..."     # 或显式指定里程碑名称
```

> ⛔ **`{TAG_STATE}` / `{BRANCH_STATE}` 按实际状态渲染，禁止硬编码「已推送」**：
> 未授权强推的分支**本就不推**、推送失败的分支**根本没推出去**，而报告若恒写「已创建并自动推送」，
> 终端会同时出现「tag 未创建」欠账与「发布成功·已推送」两条互相矛盾的输出 —— 报告失真比不报告更糟。
> 三取一（判据都已落盘，纯确定性、无需新增采集）：
>
> ```bash
> BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="{version}"
> PF=$($BE --version "$V" get release_push_failed --default "")      # Step 3.4.3 推送失败时落
> TN=$($BE --version "$V" get release_tag_name --default "")         # 空 = 本轮未打 tag（--no-tag 或撞名未授权）
> BN=$($BE --version "$V" get release_branch_name --default "")
> state(){ # $1=名称 $2=失败标记里的关键字
>   [ -z "$1" ] && { echo "本轮未创建（--no-tag 准发布 / 撞名未获强推授权）"; return; }
>   case ",$PF," in *",$2,"*) echo "⛔ 已创建但**推送失败**，远端没有它；见 docs/audit/$V/发布欠账.md";;
>                   *) echo "本地已创建并已推送至 origin";; esac; }
> TAG_STATE=$(state "$TN" tag); BRANCH_STATE=$(state "$BN" branch)
> ```


> 若 Step 3.3.7 SQL 整理守恒校验失败（未中断），此处改为：
> `⚠️ SQL 整理已跳过（守恒校验失败），原文件保留；建议手工整理后下次发布合并入库`


---

