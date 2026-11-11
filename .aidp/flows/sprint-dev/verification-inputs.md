# 项目验证与输入证据

本片是 `light-context.md` 的工具选择、范围、取证与结果摘要细则；按本轮授权消费，不增加检查、报告或任务身份。

## 先选项目工具，再执行检查

先读受影响模块的配置、开发说明和 CI 入口，确认真实命令及副作用。不要按文件后缀统一生成语法扫描脚本，也不要把未修改的 SKILL、Agent 脚本或运行包当成本次业务验收对象。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?继承当前任务}"
python3 {{AIDP_HOME}}/scripts/entry_context.py plan-validation --root . \
  --execution-context "$EXECUTION_CONTEXT" --json
```

消费候选的命令来源、类别、对象数量、配置依赖、范围扩大理由和预算预估；规划输出不是执行结果。只读规划也会读取配置、说明或依赖，`selection_read_cost` 如实记录并计入原任务预算，不能当成零成本。选择本任务适用的检查，不机械执行全部候选。配置、命令与实际范围未变时复用已有选择，不在每个收尾阶段重新规划。

| 项目已有工具链 | 本次使用方式 |
|---|---|
| Python | 优先已有 Ruff/Pylint、已配置的 mypy/Pyright；相关单测使用 pytest/unittest |
| JavaScript/TypeScript | 优先既有 ESLint、项目或模块类型检查及相关单测 |
| Java | 按既有 Maven/Gradle 配置选择明确目标及关联模块，核对生命周期中的附加任务 |
| 其他语言 | 消费项目已经采用的命令和模块边界 |

- 静态检查不自动修复、格式化写回、安装新工具或修改依赖与配置。编译器必要输出与工具缓存不等于源码修改，但不能因此附带完整打包、前端构建、部署或服务启动。
- 项目脚本、bash/docker 外壳按实际内层命令和配置判断，不仅看名字。已声明且可核对的纯静态命令可执行；未知包装或副作用不明则报告未核验。容器不得自动拉取缺失工具，真实镜像身份及环境探测也进入本次证据和成本。
- 没有对应项目工具时可做基础语法兜底，明确 `syntax-only`。工具不可用时保留未执行原因；语法兜底不能把未运行的 lint、类型检查或单测改成 PASS，也不能替失败的检查求绿。
- 普通开发/修复默认运行当前task/单Sprint相关单测，无需另问。真实只分析/只修改/skip才限制动作；缺测试/工具为未核验。日常不增加版本全量门；仅真实autopilot委派且基线与完整清单齐备才当前版本全量。

## 三类范围分开

执行授权范围约束能改什么；当前工作写集表示本轮处理什么；验证输入只包含该检查的实际对象与必要依赖。不要将最宽授权目录直接展开为每次验证输入。

已明确具体文件时，主流程可在原任务上真正替换工作写集：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?原任务路径}"
CURRENT_WRITE_SET=("{本轮真实文件路径}")  # 按实际改动替换，可列多项；不从旧目录机械展开。
WRITE_SET_ARGS=()
for P in "${CURRENT_WRITE_SET[@]}"; do WRITE_SET_ARGS+=(--write-set "$P"); done
python3 {{AIDP_HOME}}/scripts/entry_context.py revise --root . \
  --execution-context "$EXECUTION_CONTEXT" --replace-write-set \
  "${WRITE_SET_ARGS[@]}" --json
```

`CURRENT_WRITE_SET` 来自本轮真实工作；保留已修改、新增、删除、重命名和必要依赖的追踪。原授权、历史与已用预算不能被清掉，失败项和越界写入不能靠细化隐藏。不得另建任务规避限制。

默认排除无关 `__pycache__`、`.pyc`、node_modules、构建输出、日志、覆盖率和临时证据；实际消费的必要输入必须显式登记，不能仅按目录名丢掉真实依赖。目录成员增删、链接及目标变化、配置和共享依赖仍须识别。类型检查需要全模块、编译需要关联模块时允许扩大，但说明依据。

## 执行与闭环成本

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?继承当前任务}"
python3 {{AIDP_HOME}}/scripts/entry_context.py static --root . \
  --execution-context "$EXECUTION_CONTEXT" --input "{实际必要输入}" --timeout 30 \
  -- {已选项目静态命令及真实参数}
```

`--input` 可重复，按实际工具输入声明；不要为了覆盖旧目录登记而加整包。消费 `evidence_file`、`checked_file_count`、`fingerprint_input_count`、`read_cost`、`verification_kind/syntax_only`；`executed/process_status` 保留原执行事实，`status/finalization_status` 表示证据是否足够消费。`reused=true` 表示本轮复用该事实、没有重新启动命令，不得写成本轮实跑。对象计数须结合退出状态与工具实际输出；工具跳过、提前失败或覆盖未知时，不能按计划对象数报全部通过。不能自行写 PASS，`unit_tests_executed=false` 不能因输入含测试文件改成 true。相关测试继续按 `light-context.md` 的 `run-scope` 配方。

- 真实命令验证代码；内容指纹只证明命令、环境、配置和输入状态相符。两者不可替代。
- `scanned_files` 是本工具取证的累计内容读取操作预算，不是单次允许的不同文件数。不同输入路径、元数据复核、缓存命中、工具检查对象分别说明；外部工具 I/O 未测时记未知。
- 执行器先预估并预留前取证、命令、后取证、必需收尾核验的完整成本。包装器已管理预算时，外层不得再扣同一份费用。未使用预留可返，实际发生的费用不可清掉。
- 额度不足先检查粗目录、误纳入缓存与可避免的重复取证。确需扩大时展示已用、剩余、闭环各段预计量、缺口和余量依据，不默认建议倍数扩容，也不自行修改额度。
- 命令已结束但后置取证中断时，保留是否执行、真实退出码和输出，以及哪部分证据未完成；该结果不能作为可信 PASS。不得因保存证据失败让执行事实消失。
- `static/check/complete` 与交付回执消费共享可信输入快照。仅授权、预算、提交 SHA 或部署日志变化，不使同内容代码证据整体失效；真正相关输入或环境变化仍失效。免读限定可信 Linux 本地纳秒 ctime 条件；网络、FUSE、overlay、未知文件系统回退实际读取并计费，不能只靠 mtime 或旧 PASS 文本。

## 回执与简短摘要

提交、推送、部署只执行本次已授权且尚未完成的必要动作。完成门读取现有工具的真实回执和证据位置，不重放动作，不将日志再翻译成部署 Markdown。

回执保留 `schema=1`、`action/status/execution_context` 和 `checks[{kind,status,evidence}]`；`inputs_ref={evidence_file,checksum}` 可引用已验证静态证据，不重抄整份输入映射（旧 `inputs` 仍兼容）。引用 checksum 从真实证据读取，不自造。使用真实 `argv` 与 `result{returncode,stdout,stderr}`，或提供方 `receipt{status,id/url/sha/run_id之一}`；AUTHORIZED 不是已执行。完成摘要的 `delivery_facts` 保留实际交付，`finalization_status` 另表收尾状态；真实质量 FAIL 仍失败，机器收尾未核验不能改报未部署或重放已完成动作。

终端默认只汇报实际改动范围、工具及命令、检查对象与结果、单测是否执行、未执行/未核验事项和证据位置；发生预算问题时附具体计算。例如“29 个 Python 文件语法可解析，未执行单元测试”，不能写成“1595 个文件静态检查通过”。完整上下文、文件哈希和原始输出留在既有机器证据中，不倾倒到终端，不新增强制 Markdown 报告。
