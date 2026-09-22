# /version · 版本规划流程详情 — 分片 4/8

> 本片覆盖：**Step 2.4.4 产物归一 + 00_索引.md 维护**。
> 完整分片清单见 `{{AIDP_HOME}}/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
#### Step 2.4.4：★ 产物归一 + `00_索引.md` 维护（fresh 与补充模式均执行，约定 15）

**目的**：让四类版本规划文档目录**恒有专职导航锚 + 内容文档从 `01_` 起 + 无裸名无重号**（约定 15）。**导航锚 = `00_索引.md`（唯一，⛔ 非二选一：里程碑拆分态同样用它；`00_研发执行计划-总览.md` 仅识别存量、新生成不产）**：研发需求 / 设计详情 / 研发执行计划（单文件态与里程碑拆分态同）/ **研发自测目录**（与 dev-manual-testcase 一致：`00_索引.md` 索引 + `01_研发自测方案.md` 方案 + 用例从 `02_` 起）。**补充产物保持 SKILL 干净的 `NN_<业务名>.md`（不带"补充"字眼），补充身份登记进导航锚/索引**。命令端在 SKILL 返回后做归一/去重/维护（沿用 `/sprint-requirements` 已有的 `00_PRD-总览 → 00_索引` 归一先例；`gen_index` 自带命名锚例外守卫，里程碑拆分总览锚不强铺 00_索引，旧锚 `00_研发自测方案.md` 目录 grandfather 跳过）；SKILL 原生达标时本步为**幂等兜底**。

**1. 内容主文档锚点归一**（fresh 与补充模式均跑；对每类目录）：★ **doc-SKILL（dev-logic-architect / dev-execution-planner / ux-logic-extractor）原生产出 `00_索引.md` + `01_` 序号态，本步为幂等兜底**——仅当检出历史/异常形态才归一，正常情形不动。把 SKILL 产出的历史形态——① `00_<语义名>.md`/`00_*-总览.md`（历史单主文档/多文件总览）② **裸中文名多文件**（如 `详细设计.md`/`接口设计.md`/`数据库设计.md`/`元转积分改造清单.md`，无任何两位前缀——**这是设计详情目录最易漂移的形态**）——统一归一为 `01_/02_/03_`+ 内容文档、`00_` 槽位让给专职索引。**设计详情目录延续 `/sprint-dev` Phase 0A 已按 glob 兼容的三态命名：拆分态固定 `01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md`、其余专题 `04_+` 续编。**

```bash
plan_move() {
  if [ -e "$2" ] || [ -L "$2" ]; then printf '❌ 目标已存在：%s\n' "$2" >&2; return 1; fi
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
     git ls-files --error-unmatch -- "$1" >/dev/null 2>&1; then
    git mv -- "$1" "$2" || return 1
  else
    mv -n -- "$1" "$2" || return 1
    [ ! -e "$1" ] || { printf '❌ 移动未完成：%s\n' "$1" >&2; return 1; }
  fi
}
next_seq() {
  local DIR="$1" MAX
  MAX=$(ls "$DIR" 2>/dev/null | grep -E "^[0-9]{2}_" | grep -vE "^(00|98|99)_" | sort | tail -1 | grep -oE "^[0-9]{2}")
  printf "%02d" $(( 10#${MAX:-00} + 1 ))
}
canonical_seq() {  # 设计专题 → 规范两位序号（与 sprint-dev glob 三态一致）；非固定专题返回空走续编
  case "$1" in
    # ⛔ 序号以 **A 序**为准：01 详细设计 / 02 数据库设计 / 03 接口设计。
    #   全仓 46 份文件（commands / agents / flows / reference / docs-init / daily 模板 / 两个上游 SKILL）
    #   都按 A 序写；本函数会**重命名文件**，取反序等于把 `数据库设计.md` 改成 `03_`、
    #   与 `sprint-design.md`「必读 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`」当场对撞。
    *详细设计*) echo "01" ;; *数据库设计*) echo "02" ;; *接口设计*) echo "03" ;;
    *对外开放接口*|*对外接口*) echo "04" ;; *) echo "" ;;
  esac
}
promote_content_main() {
  local DIR="$1"
  # ① 00_<语义名>.md（历史单主文档，★排除 00_索引 与 00_研发自测方案 两个方案/索引锚）/ 00_*-总览.md → 01_（或最小空位）
  local LEGACY=$(ls "$DIR" 2>/dev/null | grep -E "^00_" | grep -vE "^00_(索引|研发自测方案)\.md$" | head -1)
  if [ -n "$LEGACY" ]; then
    local NEWNAME=$(echo "$LEGACY" | sed -E 's/^00_//; s/-总览\.md$/.md/')
    local DST_N="01"; [ -e "${DIR}01_${NEWNAME}" ] && DST_N=$(next_seq "$DIR")
    plan_move "${DIR}${LEGACY}" "${DIR}${DST_N}_${NEWNAME}" || return 1
  fi
  # ② ★ 裸中文名多文件（无 NN_ 前缀、非管家/方案/索引文件）：≥2 份即按专题规范编号（下游 V0.9.1 症状根治）
  local BARE=$(ls "$DIR" 2>/dev/null | grep -E "\.md$" | grep -vE "^[0-9]{2}_|^README|^00_(索引|研发自测方案)|^输入变更|事实清单|待澄清")
  if [ "$(echo "$BARE" | grep -c "\.md$")" -ge 2 ]; then
    # 先固定专题（详设=01/接口=02/数据库=03/对外=04），再其余专题按现存最大序号续编
    for f in $BARE; do
      local sn=$(canonical_seq "${f%.md}")
      { [ -z "$sn" ] || [ -e "${DIR}${sn}_${f}" ]; } && sn=$(next_seq "$DIR")
      plan_move "${DIR}${f}" "${DIR}${sn}_${f}" || return 1
    done
  fi
}
for DIR in "docs/requirements/{version}/研发需求/" "docs/design/detail/{version}/" "docs/plans/{version}/"; do
  [ -d "$DIR" ] || continue
  promote_content_main "$DIR" || exit 1
done
```

**研发自测用例共享目录子目录化**（`docs/testing/{version}/` 是共享目录，先归位到 `研发自测/` 子目录再归一）：

```bash
plan_move() {
  if [ -e "$2" ] || [ -L "$2" ]; then printf '❌ 目标已存在：%s\n' "$2" >&2; return 1; fi
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
     git ls-files --error-unmatch -- "$1" >/dev/null 2>&1; then
    git mv -- "$1" "$2" || return 1
  else
    mv -n -- "$1" "$2" || return 1
    [ ! -e "$1" ] || { printf '❌ 移动未完成：%s\n' "$1" >&2; return 1; }
  fi
}
V_TEST="docs/testing/{version}"
# 历史扁平单文件 → 统一目录名 研发自测；新流程 /sprint-selftest 已直接产出 研发自测/ 子目录
if [ -f "$V_TEST/研发自测用例.md" ]; then
  plan_move "$V_TEST/研发自测用例.md" "$V_TEST/研发自测.md" || exit 1
fi
if [ -d "$V_TEST/研发自测用例" ]; then
  plan_move "$V_TEST/研发自测用例" "$V_TEST/研发自测" || exit 1
fi
if [ -f "$V_TEST/研发自测.md" ]; then
  mkdir -p "$V_TEST/研发自测" || exit 1
  plan_move "$V_TEST/研发自测.md" "$V_TEST/研发自测/02_全量自测用例.md" || exit 1
fi
for f in "$V_TEST"/研发自测用例-补充-*.md "$V_TEST"/研发自测-补充-*.md; do
  [ -f "$f" ] || continue
  mkdir -p "$V_TEST/研发自测" || exit 1
  plan_move "$f" "$V_TEST/研发自测/$(basename "$f")" || exit 1
done
TESTCASE_DIR="$V_TEST/研发自测/"
```

**2. 补充产物：保持 SKILL 干净命名 `NN_<业务名>.md`（不加"补充"字眼）**——补充模式 B-2 下，上游 SKILL 的增量产出本就是 `NN_<业务名>.md`（已禁"补充/追加"语义前缀，`check_doc_split.py` 亦禁）。⚠️ 两处易错：① 三个 SKILL 都明令「本 SKILL **没有** `mode=supplement` 之类的模式参数，严禁臆造」——`--supplement` 是**命令端**的 flag；② 三份同名 `check_doc_split.py` 的编号不同（ULE / DEP 是检查项 7，**DLA 是检查项 11**），设计详情用的正是 DLA 那份。命令端**只做序号续编校正**（若 SKILL 给的 NN 与目录现存最大序号冲突/不连续，按源文件跟踪状态归一到 `MAX+1`），**绝不再补回"补充"字眼**。业务主题 `${TOPIC}`：用户 `/version V0.X "<主题>"` 显式传入 > 口述文件名解析 > 兜底 `增量NN${NN}`。

```bash
# 独立 Bash 围栏：不能沿用上一围栏里的函数。
plan_move() {
  if [ -e "$2" ] || [ -L "$2" ]; then printf '❌ 目标已存在：%s\n' "$2" >&2; return 1; fi
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
     git ls-files --error-unmatch -- "$1" >/dev/null 2>&1; then
    git mv -- "$1" "$2" || return 1
  else
    mv -n -- "$1" "$2" || return 1
    [ ! -e "$1" ] || { printf '❌ 移动未完成：%s\n' "$1" >&2; return 1; }
  fi
}
# ⛔ `TESTCASE_DIR` 赋在上一围栏（另一次 Bash 调用），必须在本围栏重新派生：取空则下面所有
#    `"$TESTCASE_DIR"` 实参都是空路径，研发自测这一类的 `00_索引.md` 从不生成/刷新（约定 15 落空）。
TESTCASE_DIR="docs/testing/{version}/研发自测/"
next_seq() {  # 目录现存最大两位序号 +1（排除 00_/98_/99_ 保留位）
  local DIR="$1"
  local MAX=$(ls "$DIR" 2>/dev/null | grep -E "^[0-9]{2}_" | grep -vE "^(00|98|99)_" | sort | tail -1 | grep -oE "^[0-9]{2}")
  printf "%02d" $(( 10#${MAX:-00} + 1 ))
}
# 对本轮 SKILL 新产出（-newer /tmp/skill_start）的增量文档做序号续编校正，保留其业务名、不加"补充"
normalize_increment() {
  local DIR="$1"
  local SRC=$(find "$DIR" -maxdepth 1 -name "[0-9][0-9]_*.md" -newer /tmp/skill_start 2>/dev/null | grep -vE "/(00|98|99)_" | head -1)
  [ -z "$SRC" ] && return 0
  local CUR_N=$(basename "$SRC" | grep -oE "^[0-9]{2}")
  local NAME=$(basename "$SRC" | sed -E 's/^[0-9]{2}_//')
  # 序号冲突/不连续 → 续编到 MAX+1（保留业务名，去除任何历史"补充-"中缀）
  local WANT_N=$(next_seq "$DIR")
  local CLEAN_NAME=$(echo "$NAME" | sed -E 's/^补充-//')
  if [ "$CUR_N" != "$WANT_N" ] || [ "$NAME" != "$CLEAN_NAME" ]; then
    plan_move "$SRC" "${DIR}${WANT_N}_${CLEAN_NAME}" || return 1
  fi
}
for DIR in "docs/requirements/{version}/研发需求/" "docs/design/detail/{version}/" "docs/plans/{version}/" "$TESTCASE_DIR"; do
  normalize_increment "$DIR" || exit 1
done
```

**3. 去重号 + 生成/刷新 `00_索引.md`（专职索引，三项必载：文件清单 + 生成时间 + 主/补充标识）**——先**消除同目录两位前缀重号**（研发自测 `02_全量自测用例` 等用例分册间重号根治；`01_研发自测方案` + `01_测试环境与账号` 双 `01_` 是不同类别并存、均按名排除 dedup、不误判），再逐份登记内容文档（`01_`+，排除 `00_索引`/`98_`/`99_`）。**主/补充标识规则**：fresh 模式本轮产出 = `主`；`--supplement` 本轮新增 = `补充`；**再生时保留已有行的标识**（历史多分区主文档 `01_/02_` 仍为 `主`），只把本轮新文件按 `RUN_TYPE` 追加。生成时间取文件 mtime（`date -r <file> '+%F %H:%M'`）。

```bash
plan_move() {
  if [ -e "$2" ] || [ -L "$2" ]; then printf '❌ 目标已存在：%s\n' "$2" >&2; return 1; fi
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
     git ls-files --error-unmatch -- "$1" >/dev/null 2>&1; then
    git mv -- "$1" "$2" || return 1
  else
    mv -n -- "$1" "$2" || return 1
    [ ! -e "$1" ] || { printf '❌ 移动未完成：%s\n' "$1" >&2; return 1; }
  fi
}
TESTCASE_DIR="docs/testing/{version}/研发自测/"   # ⛔ 同上：跨围栏取空会让 gen_index 作用于空路径
next_seq() {
  local DIR="$1" MAX
  MAX=$(ls "$DIR" 2>/dev/null | grep -E "^[0-9]{2}_" | grep -vE "^(00|98|99)_" | sort | tail -1 | grep -oE "^[0-9]{2}")
  printf "%02d" $(( 10#${MAX:-00} + 1 ))
}
dedup_prefix() {  # 同目录两位前缀重号 → 保留 mtime 较早者、靠后者续编到 next-free（排除 00_/98_/99_ 与非用例分册文件：研发自测方案、测试环境与账号）
  # ★ 研发自测目录两个非用例分册文件走固定保留槽、均按名排除去重：
  #   ① 01_研发自测方案.md（dev-manual-testcase 方案，固定 01_）② 01_测试环境与账号.md（aiauto-test 配置，固定 01_、~20 处 reader 硬编码依赖）。
  #   二者同处 01_ 是不同类别文件并存（非用例分册内部重号）；用例分册从 02_ 起，其间重号才去重。
  local DIR="$1" seen=""
  for f in $(ls -tr "$DIR" 2>/dev/null | grep -E "^[0-9]{2}_.*\.md$" | grep -vE "^(00_|98_|99_)|研发自测方案|测试环境与账号"); do
    local n=$(echo "$f" | grep -oE "^[0-9]{2}")
    if echo " $seen " | grep -q " $n "; then
      local nn=$(next_seq "$DIR")
      plan_move "${DIR}${f}" "${DIR}${nn}_$(echo "$f" | sed -E 's/^[0-9]{2}_//')" || return 1
      seen="$seen $nn"
    else seen="$seen $n"; fi
  done
}
gen_index() {
  local DIR="$1" RUN_TYPE="$2" IDX="${DIR}00_索引.md"
  # ★ 历史 grandfather 锚例外（不铺 00_索引）：目录已有 00_*-总览.md ——★ 这是【存量历史布局】，不是 dev-execution-planner 的产物
  #   （该 SKILL 无"里程碑拆分"概念、其拆分维度是 Phase，且规定「无论是否拆分 00_索引.md 恒产出」；其 check_doc_split.py 对 00_*-总览.md 主锚只出 warn 放行）。
  #   新生成一律 00_索引.md + 01_M1研发执行计划.md/02_M2…；此处仅保护存量目录的子文档内部引用不被强铺打断。
  #   或 grandfather 旧锚 00_研发自测方案.md（历史研发自测目录：方案占 00_、无 00_索引）——留旧布局不动、不强铺 00_索引。
  #   ★ 当前规范研发自测目录（00_索引 + 01_研发自测方案 + 用例 02_）无 00_研发自测方案.md → 不命中本守卫 → gen_index 正常维护其 00_索引。
  if ls "$DIR"00_*-总览.md >/dev/null 2>&1 || [ -f "${DIR}00_研发自测方案.md" ]; then return 0; fi
  declare -A OLDTYPE   # 保留旧索引「文件→标识」映射，主/补充标识不因再生丢失
  if [ -f "$IDX" ]; then
    # ⛔ 读方必须与**写方的实际行形态**对齐：写出去的是
    #   `| NN | [file](./file) | mtime | 类型 | — |`（见下方 echo），
    #   故 ① grep 过滤 `^| NN |`（⛔ 不是 `NN_`，那样一行都匹配不上）
    #      ② IFS='|' 时行首 `|` 先产生一个空字段，字段要多跳一格（`_ _ f _ t _`）。
    #   任一处错 ⇒ OLDTYPE 恒空 ⇒ 类型列每次再生被 RUN_TYPE 覆盖，
    #   而 release-5 正是凭「类型=补充」判定增量身份、据此 git rm —— 会误删主文档。
    while IFS='|' read -r _ _ f _ t _; do
      f=$(echo "$f" | grep -oE "[0-9]{2}_[^]]+\.md" | head -1); t=$(echo "$t" | tr -d ' ')
      [ -n "$f" ] && OLDTYPE["$f"]="$t"
    done < <(grep -E "^\| *[0-9]{2} *\|" "$IDX")
  fi
  { echo "# 00_索引"; echo; echo "> 本目录文档索引。生成时间 = 各文件产出/最近修订时刻；类型 = 主（版本规划首产）/ 补充（后续增量，靠更晚生成时间 + 本列区分）。"; echo;
    echo "| 序号 | 文件 | 生成时间 | 类型 | 说明 |"; echo "|---|---|---|---|---|";
    for f in $(ls "$DIR" | grep -E "^[0-9]{2}_.*\.md$" | grep -vE "^(00_索引|98_|99_)" | sort); do
      local n=$(echo "$f" | grep -oE "^[0-9]{2}")
      local mt=$(date -r "${DIR}${f}" '+%F %H:%M' 2>/dev/null)
      local ty="${OLDTYPE[$f]}"; [ -z "$ty" ] && ty="$([ "$RUN_TYPE" = supplement ] && echo 补充 || echo 主)"
      echo "| ${n} | [${f}](./${f}) | ${mt} | ${ty} | — |"
    done
  } > "$IDX"
}

# ★ RUN_TYPE 显式赋值（由 Step 1 模式决议）：情况 A（fresh 全量）→ fresh；情况 B-2（补充模式）→ supplement
RUN_TYPE=fresh   # 补充模式（情况 B-2）分支下改赋 RUN_TYPE=supplement
# 研发需求 / 设计详情 / 研发执行计划：前一围栏已归一锚点/裸名；此处去重号并生成 00_索引。
for DIR in "docs/requirements/{version}/研发需求/" "docs/design/detail/{version}/" "docs/plans/{version}/"; do
  [ -d "$DIR" ] || continue
  dedup_prefix "$DIR" || exit 1
  gen_index "$DIR" "$RUN_TYPE" || exit 1
done
# 研发自测目录：已随上游对齐通用范式（00_索引 + 01_研发自测方案 + 用例 02_），与其他三类同样 dedup + gen_index。
# 用例分册从 02_ 起去重号；01_研发自测方案 与 01_测试环境与账号（aiauto-test 配置）均按名排除 dedup（dedup_prefix 排除项）。
# gen_index 自带守卫：当前规范目录（无 00_研发自测方案.md）正常维护 00_索引；grandfather 旧锚目录跳过、留旧布局不动。
dedup_prefix "$TESTCASE_DIR" || exit 1
gen_index "$TESTCASE_DIR" "$RUN_TYPE" || exit 1
```

> ★ **单一信源 = 约定 15**：`00_` 槽位给专职导航锚 `00_索引.md`（研发执行计划**里程碑拆分态同样如此**——分册从 `01_M1研发执行计划.md` 起，`00_` 不被总览占用；存量 `00_研发执行计划-总览.md` 属历史 grandfather，留旧不动、不新产）；补充文档文件名不带"补充"字眼、身份在导航锚登记；生成方 = 命令端归一 + 上游最终原生。**研发自测目录已对齐通用范式**——导航锚 = `00_索引.md`（SKILL 第八步收尾产出），`01_研发自测方案.md`（方案）+ 用例从 `02_` 起，命令端对该目录同样 `dedup_prefix` + `gen_index`（gen_index 守卫：grandfather 旧锚 `00_研发自测方案.md` 目录跳过、不强铺）。

**3bis. ★ 档位收敛兜底（配 Step 2.4.1.5 需求规模档位）**：读 baseline `versions.{V}.req_scale.tier`；若各 SKILL 未按传入档位收敛产出（典型：**S 档仍产出多册详细设计**）→ 归一时按档位做产物合并兜底（S 档把 `docs/design/detail/{version}/` 的多份内容文档合并为 1 册 `01_详细设计.md`，`98_`/`99_` 保留槽不并），合并后重跑 `dedup_prefix` + `gen_index`。**这是异常兜底、非常规路径**，触发时打印 `档位收敛异常（已兜底合并）` 并在本步小结列出被合并的文件名。档位只影响承载文件数，**不放松任何 Critical 硬门**。

**3ter. ★ 项目级事实索引刷新（跨版本增量基建的写入点 —— 归一之后、审计之前）**

产物落盘归一完成后、进入 Step 2.4.6/2.4.7 之前，刷新两份**项目级**索引，让本版结论对后续版本可检索：

```bash
python3 {{AIDP_HOME}}/scripts/code_inventory.py update                          # 代码事实增量刷新
python3 {{AIDP_HOME}}/scripts/code_inventory.py snapshot --version {version}    # 打快照，供下版算 Δ
```

- **顺序不可换**：必须在 2.4.7 审计**之前**——审计 H 要在台账里检索历史条目，本版没入台账不影响 H（H 查的是历史），但**下一个版本的 H 会因此漏掉本版**；快照同理，漏打会让下版的 `delta --since {version}` 无从算起、退回全量判断。
- **失败不阻断落盘**：脚本失败（如本版尚无 `研发需求/`）时打印告警并继续，但须在 Step 2.8 规划报告里列为待补项——**不要静默跳过**，否则索引出现空洞而无人知晓。
- **索引不是权威、只是索引**：权威永远是 `docs/` 下的原文与表 F；两者不一致时以原文为准并重跑 `index`。

**4. 历史文件不强制改名**：历史已有的 `NN_补充-<主题>.md` / `<主题>-补充-NN.md` / 裸 `00_<语义名>.md` **不重命名**，`gen_index` 仍会把它们（凡带 `NN_` 前缀者）登记进索引；`version-auditor` 审计 E 记录"历史命名漂移"不阻塞。下次同主题增量按当前规范落干净 `NN_<主题>.md`。

---

