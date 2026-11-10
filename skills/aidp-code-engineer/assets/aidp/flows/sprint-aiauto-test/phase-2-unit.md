> ⚠️ **权威性**：本文件是 build 双路派发及全量单测执行协议唯一信源；命令主体和其它分片只引用本节，不复制实现步骤。
> ⚠️ **维护**：随脚手架下发；改动后由镜像脚本同步 bundle。理据见同目录 `rationale.md`。

<!-- 新增分片 · phase-2 全量单测子 Agent：与 2.0.5 实测子 Agent 并行，互不阻断 -->
# sprint-aiauto-test · 双路协调与全量单测（2.0.5u）

## Phase 2 · 2.0.5u.0 主协调入口：同一 build 的两路独立派发

**触发**：某个已部署 build 开测时执行，适用于用户手动、autopilot `--once`、`/loop` 和 `/sprint-batch`。先按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 继承父策略；只有真实显式命令/用户grant的支线才进入本节。主协调者先执行 Phase 0.0.0 的 tick begin/parse 并保管 token，再固定 `MAIN_ROOT`、`TARGET_VERSION`、`BUILD`、部署完整 `BUILD_COMMIT`，先冻结本次输入并核动作/预算，再在**同一批Agent调用中**派出所有已授权且尚需执行的worker。显式本命令的实测与全量单测两路仍并行，不等待一边完成才启动另一边；未请求支线NOT_REQUESTED，不派worker、不伪造PASS或pending。

1. 常规 build 从 baseline 的本版本 `builds[]` 中按 `build` 精确定位，读取该条 `push_commit`；不得用 `HEAD`、分支名、缩写 SHA 或相邻 build 代替。可用 `baseline_edit.py --version "$TARGET_VERSION" --build "$BUILD" get push_commit --default ""` 读取。standalone 由主协调者核验实际部署 commit，并把核验依据写进冻结计划的 `deployment`。
2. 主协调者在浏览器环境、账号、权限、用例清单、已测去重等实测分支前置门之前做双路派发。这些门只约束实测子 Agent；纯后端、无浏览器适用面、无实测用例、实测已完成、浏览器工具不可用、登录失败都不能取消单测子 Agent。
3. 两路均已授权且有部署baseline的build，派发前由主协调者运行 `python3 {{AIDP_HOME}}/scripts/aiauto_test_join.py begin --root . --version "{version}" --build "{BUILD}" --commit "{部署完整SHA}"`，声明两路在途；准发布等待此状态，不用旧的实测 PASS 提前放行。先轻量读取单测 `status`：同 build 的 `RUNNING` 只接续观察，不重复派 worker；已有终态可直接接收。尚未启动时派 unit worker。并发 tick 即使同时派 worker，执行器也只允许一个进入真实执行。
仅一路获授权时不调用声明双路pending的begin/settle；按父context记录实际支线证据与另一支NOT_REQUESTED，不伪装完整双路验收。

4. 子 Agent 不递归调用 `/sprint-aiauto-test`，不再各自启动双路协调，不调用 finalize，不发报告通知，不写共享 baseline。主协调者负责两路结果汇总、共享 baseline 串行更新、BUG 登记及 Phase 3 finalize。

**真实派发围栏**：先从route.authorized_actions与实际unit status得出本次需要新派发的 `DISPATCH_ACTIONS`（仅live-tests/full-regression；RUNNING/可信终态不再派；数组为空直接接收既有结果，不运行派发围栏）。各支线的真实inputs清单绑定部署来源、计划、适用配置及上下文；下面在Agent工具调用之前执行，任一预算失败不增加上限、不启动未预留worker。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?主仓父任务绝对路径}"
DISPATCH_INPUTS_JSON="${DISPATCH_INPUTS_JSON:?实际输入文件路径JSON数组}"
DISPATCH_ACTIONS=("${DISPATCH_ACTIONS[@]}")
INPUT_HASH=$(printf '%s' "$DISPATCH_INPUTS_JSON" | python3 -c '
import hashlib, json, sys
from pathlib import Path
paths = json.load(sys.stdin)
if not paths:
    raise SystemExit("UNVERIFIED: 缺少派发输入")
inputs = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}
print(hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest())
') || exit $?
for ACTION in "${DISPATCH_ACTIONS[@]}"; do
  python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
    --execution-context "$EXECUTION_CONTEXT" --action "$ACTION" || exit $?
  python3 {{AIDP_HOME}}/scripts/execution_policy.py reserve-budget --root . \
    --execution-context "$EXECUTION_CONTEXT" --action "$ACTION" \
    --resource agents --cost 1 --input-hash "$INPUT_HASH" || exit $?
done
```

派单额外带execution_context、当前revision、各自action、父剩余budget、INPUT_HASH；worker继承，不因进入aiauto重新grant。执行器内部扣进程/耗时等预算，主协调者不重复扣相同执行资源。

| 子 Agent | prompt 必须包含 | 独占写集与返回要求 |
|---|---|---|
| 实测分支 | 固定 version/build/commit；按原 Phase 0/1/2 做实测（跳过已由主协调者完成的 tick begin/parse）；读取固定上下文，不重新选取新 current_build；需要 baseline/通知写入时只回传主协调者串行处理，任一 `exit` 仅结束本子 Agent；禁止递归命令和 finalize | 仅本 build 实测执行 payload、截图、浏览器/接口证据；返回实测状态与证据路径。无适用面返回明确 `N/A`，环境/账号阻塞返回未核验；失败不能取消 unit worker |
| 单测分支 | 本文件路径、固定 root/version/build/commit、冻结 `UNIT_PLAN` 路径、`UNIT_TIMEOUT_SECONDS`（默认 3600）；自行 Read 本文件后调用下述执行器 | 仅 `memory/.aidp/build-unit/{version}/{build}/` 内执行状态、日志、账本与 worktree；返回执行器 JSON。不得接管实测资源、启动部署服务、生成占位测试命令或改共享 baseline |

浏览器提前结束、失败或超时后，主协调者继续读取单测状态直到终态或单测总预算结束；单测先失败也继续等待实测。单次 tick 不同步等待长测试：阻塞 `run` 在独立子 Agent 中执行，后续 tick 用 `status` 接续。没有常驻 cron/调度服务，也不能把测试 stdout 中的失败当作中止另一分支的控制指令。

## Phase 2 · 2.0.5u.1 冻结计划与部署来源校验

`UNIT_PLAN` 是已冻结的 UTF-8 JSON 文件；不在运行期间从当前工作区重新发现命令。其顶层字段为：

| 字段 | 约束 |
|---|---|
| `schema` | 整数 `1` |
| `version` / `build` / `commit` | 与 CLI 完全一致；commit 为本仓可解析的完整小写 SHA（40 或 64 位），必须为 commit 对象 |
| `source.path` | 部署 commit 内项目测试配置或契约卡的仓库相对路径 |
| `source.sha256` | `git show <commit>:<source.path>` 原始字节的 SHA256；不是当前工作区文件的摘要 |
| `suites` | 非空数组，每套真实完整单测命令一项，与该 commit 来源中的 `suites` **完全相等** |
| `standalone` | 只有没有 baseline 本 build 的手动已部署环境才可显式设 `true` |
| `deployment` | standalone 必填 `{commit, verified:true, evidence}`；commit 同 CLI，evidence 为主协调者核验实际部署 commit 的非空依据。仅填 true 不是脚本替调用方完成部署核验；已有 baseline build 时仍必须匹配其 `push_commit`，不能用 standalone 绕过 |

**支持的来源**：JSON 文件根 `suites` 或 `test_plan.suites`；Markdown 契约卡中**恰好一个**语言标记为 `aidp-test-plan` 的 fenced JSON 块，内容结构为 `schema:1`、`suites` 数组。现有契约的真实 `test_plan.full_argv/cwd/env_id/inputs` 应在部署前形成该可解析块；缺少已提交来源则记 `UNVERIFIED`，不得临时发明命令、读取脏工作区配置后冒充部署来源，也不为补来源而在本流程提交、打包或部署。

每个 suite 的字段为：

| 字段 | 约束 |
|---|---|
| `full_argv` | 非空字符串数组，原样 argv 执行，不通过 shell；真实全量测试命令，禁止 `true` / `echo` 等占位及安装、构建、启动或部署动作 |
| `cwd` | 部署 worktree 内实际存在的相对目录，可为 `.` |
| `env_id` | 非空、已冻结的测试工具链/依赖状态标识；不得冒充被测部署环境 |
| `inputs` | 必填字符串数组，可为空；显式文档/契约输入相对 worktree，必须存在，禁止逃出 worktree |
| `external_dependencies` | 必填 `none` 或 `isolated`；isolated 的数据库/服务须是专用测试资源，禁止指向实测的部署环境 |
| `env` | 可选显式字符串映射，必须来自冻结配置。只声明测试所需变量，不把凭据写进计划。预装外部工具链可在此指定 PATH；不得引用主工作区源码/依赖或覆盖 HOME/PWD/TMPDIR/Git 工作区位置 |
| `junit_xml` | 可选本次运行新生成的 XML 路径，相对 worktree 根；必须在命令执行前不存在。项目应把报告目录声明为忽略产物，否则账本会正确判定测试改动输入树。文件不存在/损坏时 `UNVERIFIED` |

执行器用 `git show` 读取来源，核对原始字节摘要和套件全集；主工作区同名配置、代码、未跟踪文件的后续改动不参与测试。只读已部署 commit，不复制主仓 `node_modules`、虚拟环境或未提交源码到 worktree。跟踪的向外符号链接和未装配 submodule 记未核验，不自动下载/安装。

执行环境只保留受控的系统工具 PATH、语言环境和独立 HOME/TMPDIR，禁用 Python 用户 site；不继承部署连接串、PYTHONPATH 等宿主变量。`external_dependencies` 是冻结项目配置的明确声明，执行器不是网络沙箱；项目测试配置必须真实隔离。未能满足时返回 `UNVERIFIED`，不安装、不全量构建、不启动部署服务。

## Phase 2 · 2.0.5u.2 确定性执行器 API

在已授权单测子Agent中运行。UNIT_TIMEOUT_SECONDS取父预算内批准上限（执行器原上限3600），所有套件共享，不能逐套重置。run围栏以 `bash -c <围栏正文> -- <冻结计划路径> <父execution_context绝对路径>` 调用；$1固定计划，$2指向主仓context，不能改指worktree。

```bash
UNIT_PLAN="${1:?须传本次派单冻结计划路径}"
EXECUTION_CONTEXT="${2:?须传主仓父execution_context绝对路径}"
MAIN_ROOT="$(pwd -P)"
UNIT_VERSION=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$UNIT_PLAN") || exit 2
UNIT_BUILD=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["build"])' "$UNIT_PLAN") || exit 2
UNIT_COMMIT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["commit"])' "$UNIT_PLAN") || exit 2
AIAUTO_UNIT_TIMEOUT_SECONDS="${AIAUTO_UNIT_TIMEOUT_SECONDS:?读取父预算内实际批准的执行上限}"
UNIT_TIMEOUT_SECONDS="$AIAUTO_UNIT_TIMEOUT_SECONDS"
python3 {{AIDP_HOME}}/scripts/build_unit_test.py run \
  --root "$MAIN_ROOT" --version "$UNIT_VERSION" --build "$UNIT_BUILD" \
  --commit "$UNIT_COMMIT" --plan "$UNIT_PLAN" --timeout "$UNIT_TIMEOUT_SECONDS" \
  --execution-context "$EXECUTION_CONTEXT"
```

后续tick只读status，不消费执行预算，不要求新增grant：

```bash
UNIT_PLAN="${1:?须传本次派单冻结计划路径}"
UNIT_VERSION=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$UNIT_PLAN") || exit 2
UNIT_BUILD=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["build"])' "$UNIT_PLAN") || exit 2
python3 {{AIDP_HOME}}/scripts/build_unit_test.py status \
  --root . --version "$UNIT_VERSION" --build "$UNIT_BUILD"
```

工具或隔离依赖恢复后，在父full-regression授权、根因/输入已改变且retry预算允许时，主协调者才可选择同计划重试 `UNVERIFIED` / `TIMEOUT`，在原 `run` 调用上加 `--retry`。默认不重跑终态；`PASS` 即使传 `--retry` 也不执行，真实 `FAIL` 进入修复/新 build，不以同 build 重试掩盖。commit/计划变更必须使用新 build。重试保留此前 attempt 的结果和日志。

Python API：`run_build(root, version, build, commit, plan, timeout=3600, retry=False, execution_context=None)`，execution_context仅指主仓策略；内部worktree账本不传该context，避免root身份冲突（plan 为 dict 或 JSON 文件路径）、`read_status(root, version, build)`。执行 API 修改本进程信号/环境/输出 fd，只能在专用执行器进程主线程调用，不嵌入多线程主 tick。

**生命周期保证**：

- 固定目录 `memory/.aidp/build-unit/{version}/{build}/`；其中 `worktree/` 是本 build detached worktree，`ledger/` 是专属本地账本根，`result.json` 是原子落盘结果，`plan.json` 是冻结计划副本，`suite-{attempt}-{index}.log` 保存完整 stdout/stderr。不同 build 不共享执行目录或缓存；即使 commit 相同也必须重跑。
- `lifecycle.lock` 覆盖校验、worktree 创建、各套执行、清理和结果落盘；并发同 build 的另一 `run` 立即返回 `RUNNING` 或已完成结果，不排队占住 tick。每套都调用 `test_ledger.run(scope='full', ledger_root=本build专属目录)`，保留各自 `run_id`。
- `RUNNING` 持久化 pid、started_at、deadline_at 与已经完成的 runs；`status` 以锁判活。执行器异常退出、锁已释放但文件停留 RUNNING 时返回 `UNVERIFIED / executor-interrupted`，不会永久假运行。
- 计时从执行器校验阶段开始，所有套件扣同一总预算；超时终止命令进程组，后续套件不再执行，最后清理本次创建的 worktree。清理 Git 命令另有有界退出保护；已有目录、既有 worktree 注册或中断遗留现场均不接管、不递归删除，不运行全局 `worktree prune`。
- 结果与日志留在本地目录，worktree 删除不丢证据。同 build 再唤起 PASS 不重新测试；本 build 专属账本不能给另一个 build 冒充通过。
- `run` / `status` 的业务状态通过单个 JSON 返回；包括 FAIL/TIMEOUT/UNVERIFIED 都正常退出 0，调用方必须读取 `status`。CLI 参数错误仍由 argparse 报错。执行器不写 freeze、不登记 BUG、不通知、不触发浏览器取消。
- 可独立验收 `python3 {{AIDP_HOME}}/scripts/build_unit_test.py --self-check`：使用真实临时 Git 和标准库 unittest，不联网，不跑全量回归。

## Phase 2 · 2.0.5u.3 结果契约与结论

返回 JSON：`schema:1`、`version`、`build`、`commit`、`status`、`reason`、`runs`、`counts`、`failed_cases`、`primary_error`、`reused`。每个 run 包含 `run_id`、`status`、`reason`、`command`（argv 数组）、`cwd`、`env_id`、`inputs`、`counts:{passed,failed,skipped}`、`failed_cases`、`primary_error`、`log`（绝对路径）、`exit_code`。本地结果另有完整性 checksum 和运行时间等元数据，不应手工修改。

计数优先读取本次 JUnit XML，否则解析标准库 unittest 汇总；无法解析的值为 JSON `null`，不得以 0 或猜测数字代替。expected failures 归跳过，unexpected successes 归失败。未跑出任何用例的已知空测试集为未核验；无法识别失败证据的异常退出也为未核验，保留日志供人工判断。多套汇总只有全部对应数值已知才相加，任一未知则该汇总值为 `null`。

| status / 条件 | 结论 | 主协调者处置 |
|---|---|---|
| `authorization_status=NOT_REQUESTED`、`executed=false` | 执行器二次授权拦截（外层status为UNVERIFIED） | 调用方按未请求处理，不建worktree、不派worker、不记欠账或PASS |
| `PASS` | 全部套件通过 | 保留所有 run_id，同 build 复用；不得用它代替实测结果 |
| `FAIL` | 已识别真实测试失败 | 与实测失败同等计入本 build 不通过；由下述 `aiauto_test_join.py settle` 幂等登记单测 BUG 并交 `/sprint-bugfix`，不得重复手工登记；新 build 两路重跑 |
| `UNVERIFIED` | 本项未核验 | 缺来源/输入/commit、非 Git、baseline 不匹配、退出 127、模块缺失、无用例、损坏报告等；记原因，不登记为产品 BUG，不计通过，不 freeze |
| `TIMEOUT` | 未完成（超时） | 保留已完成套件与超时日志；不挂起主 tick，不 freeze，不当作真实测试失败 |
| `RUNNING` | 正在执行 | 后续 tick 读 status；不得当通过或启动第二个同 build 执行器 |

若失败和未核验同时存在，报告仍逐套展示；整体 FAIL 表示至少发现真实失败，TIMEOUT 表示总预算尚未完成全部验证。浏览器结果独立保留，任何一路失败都不让另一边停止。

## Phase 2 · 2.0.5u.4 汇总与发布边界

- 以下build双路汇总只适用于两路均已授权；任一NOT_REQUESTED不进入要求双路证据的settle/finalize。主协调者在两路完成或分别超时后，把执行器结果保存/引用为 `memory/{version}/aiauto-unit-{BUILD}.json`。报告 `emit test` 带 `--unit-result <结果路径> --commit <部署完整SHA>` 合并两路结果；纯后端没有浏览器适用面时再带 `--browser-na-reason <明确原因>`，可输出空实测 cases 报告，但单测不可省略。unit worker 只维护其本地独占目录。
- 主协调者先按 Phase 3.3 的 `failureTriage` 契约完成实测缺陷/产品澄清/环境未核验分类，写 `memory/.aidp/test-triage-${BUILD}.json`；`emit test` 带 `--failure-triage <该文件>`，`REPORT_DATA` 指向该 build 的 `data.js`。主协调者执行 `python3 {{AIDP_HOME}}/scripts/aiauto_test_join.py settle --root "$MAIN_ROOT" --version "$TARGET_VERSION" --build "$BUILD" --report "$REPORT_DATA" --triage "memory/.aidp/test-triage-${BUILD}.json"`（无待分流问题可省略分类文件与参数），由它验证 `unitTests` / `build.commit`，合并 baseline 的 `result` / `overall_status` / `unit_failed`，并幂等登记单测 FAIL 到 `docs/bugfix/{version}/bugfix-unit-{BUILD}.md`。不得再手工分配或登记同一批单测 BUG。
- 主协调者校验结果的 version/build/commit 与本轮部署一致，再 finalize。尚无结果、RUNNING 或残留异常不能伪装通过；未核验不 freeze、不写 `aiauto_tested_at`。后续发布链路读取 join 的 `release-state`（pending/pass/failed/legacy）处理门禁，不能只看浏览器 PASS。允许跨 tick 接续，无须让一次 tick 等满 3600 秒。
- 报告 HTML 中「全量实测」与「全量单测」分别列出适用状态；纯后端无浏览器适用面明确 N/A，单测仍展示实际结论。单测列出命令、各 run_id、已知计数/未知标记、失败用例、首要错误和日志证据。通知仅由主协调者一次发出。
- `/sprint-test` 的开发期 Sprint 单测由 `test_scope.py` 推导并经 `run-scope` 记为 `scope=sprint`；它服务工作区验收与部署前门。本文件只服务已部署 build 的 `scope=full`，二者账本范围不可互相冒充。
