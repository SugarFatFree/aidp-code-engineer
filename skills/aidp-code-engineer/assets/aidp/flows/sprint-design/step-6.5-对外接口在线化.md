# sprint-design · Step 6.5 详情（对外开放接口 OpenAPI 文档化）

> 本文件是 `/sprint-design` 命令 **Step 6.5** 的完整详细步骤，由命令主体（`{{AIDP_HOME}}/commands/sprint-design.md`）在**进入该段时用 Read 工具按需加载**——把状态判定 + 首次/增量子 Agent 派单 prompt 模板 + `openapi.yaml` 结构/SHA256 契约从"每次调用整体入上下文"改为"走到该段才载"。命令主体只保留该段的**骨架表 + Read 指针**。
>
> ⚠️ **权威性**：进入本段后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/step-6.5-对外接口在线化.md`。理据/根因见同目录 `rationale.md`。

---

### Step 6.5：★ 对外开放接口 OpenAPI 文档化（可选）

**核心契约**：**本地 `对外开放接口.md` 始终为权威版本**；`docs/design/detail/{version}/openapi.yaml`（OpenAPI 3.0.3）是由它派生的**机读副本**，随仓库入库，供 Swagger UI / Redoc / API 网关 / 对接方 SDK 生成等消费（如需在线浏览，由项目自己的 CI 发布到 GitHub Pages 等静态站点，本 Step 不负责）。首次生成后在 `openapi.yaml` 的 `info.x-aidp-source` 记录源 MD 的 SHA256；后续每次 /sprint-design 重跑都检测源 MD 变化并询问是否重新生成（覆盖式）。**不修改本地 MD、不反向同步**。

**触发条件**（任一不满足则跳过本 Step）：
- `HAS_OPEN_API = true`（来自 Step 0.4.5）
- `docs/design/detail/{version}/*对外开放接口*.md` 存在（拆分时含全部分册）
- 补充模式（`--supplement={NN}`）下默认 skip 本 Step（避免把补充文档当主版本生成）

#### Step 6.5.1：状态判定（副本存在性 × 错误标记）

**判定 1：`openapi.yaml` 是否已存在且含 `info.x-aidp-source.sha256`**

```bash
OAS=docs/design/detail/{version}/openapi.yaml
test -f "$OAS" && python3 -c "
import sys, yaml
try:
    d = yaml.safe_load(open('$OAS'))
    sys.exit(0 if ((d.get('info') or {}).get('x-aidp-source') or {}).get('sha256') else 1)
except Exception:
    sys.exit(1)
"
```

**判定 2：是否有未处理的生成失败标记**

```bash
test -f .aidp-openapi-sync-error.json
```

存在 → 上一轮子 Agent 失败遗留的报错文件。**输出 ERROR**：「上次对外接口 OpenAPI 文档生成失败，错误详情见 `.aidp-openapi-sync-error.json`（含失败时间 / 阶段 / 错误信息）。请人工排查后删除该文件再重跑 /sprint-design」。**暂停本 Step 直至文件删除**（不阻塞 Step 7 的状态更新，仅跳过本 Step）。

| 状态 | `openapi.yaml`（含 x-aidp-source） | 错误标记 | 行为 |
|------|------|---------|------|
| **D 残留错误** | 任意 | 存在 | 输出 ERROR + 暂停本 Step 直至 `.aidp-openapi-sync-error.json` 被人工处理删除 |
| **B 首次** | 不存在 / 无 x-aidp-source | 不存在 | 进入「首次生成」流程（6.5.2~4，**派单子 Agent**） |
| **C 增量** | 已存在 | 不存在 | 进入「增量重新生成」流程（6.5.5~6） |

> `.aidp-openapi-sync-error.json` 是运行时临时文件，应列入 `.gitignore`（不进 git）。
> `yaml` 模块不可用时（未装 PyYAML）→ 判定 1 用 `grep -q 'x-aidp-source' "$OAS"` 降级判断即可。

---

#### 状态 B：首次生成流程

#### Step 6.5.2：询问用户是否生成 OpenAPI 文档

- **交互式**：用 `AskUserQuestion` 工具（单选）：

  ```
  问题：本版本含对外开放接口。是否由「对外开放接口.md」生成 OpenAPI 3.0.3 文档（docs/design/detail/{version}/openapi.yaml，入库）？
    - 生成 openapi.yaml（本地 MD 保留为权威，yaml 为派生副本）
    - 保持仅 MD
  ```

- **无人值守（`--unattended`）**：不弹窗，默认「生成 openapi.yaml」。

选「保持仅 MD」→ 跳到 Step 7。

#### Step 6.5.3：派单子 Agent 执行首次生成

**★ 为什么派子 Agent**：一篇对外接口文档常含数十个接口、请求/响应表与示例，逐条转成 OpenAPI schema 需要完整读正文；放在主对话会把整份产物塞进主上下文。

**派单前主 Claude 必须先做的准备**：

1. **读 `memory/aidp-config.yaml`** 拿到 `project.name_cn`（缺省 `project.name`，再缺省 git 仓库名）（用于 `info.title`）
2. **替换占位符**：把下方 prompt 模板内**所有** `<...>` 形式的占位符（如 `<project_root>` `<version>` `<项目名称>` `<本地 MD 路径>`）替换为实参；模板内**直接嵌入** Step 6.5.4 的结构契约 + SHA256 Python 代码字符串（子 Agent 拿到的是孤立 prompt，不再 Read 本文件）
3. **调** `Agent(subagent_type="general-purpose", description="对外接口 OpenAPI 首次生成", prompt=<替换后的完整指令>)`（可 `run_in_background=true`，不阻塞 Step 7）

**任务指令模板**（粗体 `[占位待替换]` 标记的位置由主 Claude 派单前填实参）：

````
你是 /sprint-design 派单的"对外开放接口 OpenAPI 首次生成"子 Agent，独立执行，
不依赖主对话；完成 / 失败均需把状态写入本地文件让主对话或下次重跑能查到。

变量（主 Claude 派单前已替换为实参）：
- 项目根：[占位待替换：<project_root>]
- 本地 MD：[占位待替换：docs/design/detail/<version>/对外开放接口.md]（拆分时按 glob 读全部分册，按文件名排序合并）
- 输出：docs/design/detail/<version>/openapi.yaml
- 文档标题：[占位待替换：<项目名称> 对外开放接口]
- 版本：[占位待替换：<version>]

任务步骤：
1. Read 本地 MD 全文（含全部分册）
2. 按下方「结构契约」把每个接口转成 OpenAPI 3.0.3：路径前缀取 MD 声明的「对外开放接口 base」作 `servers[].url`；
   请求参数 / 请求体 / 响应体表格 → `components.schemas` + `$ref`；MD 声明的鉴权方式 → `components.securitySchemes`；
   幂等键请求头、限流响应（429）、错误码表 → 对应 `parameters` / `responses`。
   ⛔ 只转写 MD 已写明的内容，不补造字段 / 示例 / 错误码；MD 未写明处在对应节点加 `description: "TODO: 对外开放接口.md 未声明"`
3. 计算源 MD 的 SHA256（主 Claude 已嵌入）：
   ```python
   [占位待替换：完整嵌入 Step 6.5.4 契约 B 的 SHA256 Python 代码，且 '<本地 MD 路径>' 已替换为实参]
   ```
4. 在 `info.x-aidp-source` 写入 path / sha256 / generated_at（格式见契约 A），Write 输出文件
5. 校验：`python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <输出>` 必须通过；
   若本机可用 `npx`，再 best-effort 跑 `npx --yes @redocly/cli lint <输出>`（lint 告警写入完成报告，不视为失败）
6. **完成报告**：stdout 输出 输出路径 / 接口数 / sha256 / TODO 节点数 / lint 摘要

失败处置（任一步骤失败均 Write .aidp-openapi-sync-error.json 后退出，不再继续后续步骤）：
- 转换失败 → {"stage":"convert","mode":"fresh","time":"<ts>","error":"<msg>"}
- YAML 解析校验失败 → {"stage":"validate","mode":"fresh","time":"<ts>","error":"<msg>"}（删除本次写出的不合法 openapi.yaml，避免下次误判为状态 C）

执行约束：
- 仅可写 docs/design/detail/<version>/openapi.yaml 和项目根 .aidp-openapi-sync-error.json（失败时）；不修改本地 MD 及其他任何文件
- 日志只用 stdout
- 失败必写 .aidp-openapi-sync-error.json，让主对话有兜底信号
````

**主 Claude 派单后**：
1. 在 `memory/{version}/{user}/activeContext.md` 追加一行：`- {YYYY-MM-DD HH:MM:SS} 对外接口 OpenAPI 文档已派单子 Agent 生成（模式：首次）`
2. 终端打印：「已派单子 Agent 生成 `openapi.yaml`，完成后可在任务面板查看报告。」
3. 跳到 Step 7

---

#### Step 6.5.4：`openapi.yaml` 结构契约 + SHA256 算法（DRY 单一来源）

**本 Step 不在主流程上下文中"运行"**——它只是 Step 6.5.3 / 6.5.6 派单 prompt 的**嵌入素材源**。主 Claude 派单前必须把下列两份模板的占位符替换为实参后，**整段嵌入**到子 Agent prompt 的对应步骤里。

**契约 A：`openapi.yaml` 头部结构**（占位符：`<title>` `<version>` `<本地 MD 路径>` `<sha256>` `<generated_at>` `<base>`）：

```yaml
openapi: 3.0.3
info:
  title: <title>
  version: <version>
  description: 由 <本地 MD 路径> 派生生成；本地 MD 为权威版本，请勿直接手改本文件。
  x-aidp-source:
    path: <本地 MD 路径>        # 拆分时为逗号分隔的分册列表
    sha256: <sha256>
    generated_at: <generated_at>  # ISO 8601
servers:
  - url: <base>
paths: {}
components:
  schemas: {}
  securitySchemes: {}
```

格式约束：`x-aidp-source` 必须位于 `info` 下（OpenAPI 允许 `x-` 扩展字段，校验工具不会报错）；`paths` 按 MD 中接口出现顺序排列，便于 diff 审阅。

**契约 B：SHA256 计算 Python 代码**（占位符：`<本地 MD 路径>`，拆分时为分册 glob）：

```python
import glob, hashlib
files = sorted(glob.glob('<本地 MD 路径>'))
h = hashlib.sha256()
for f in files:
    h.update(open(f, 'rb').read())
print(h.hexdigest())
```

**关键**：分册必须**按文件名排序后**依次喂入，否则同一内容在不同文件系统上算出不同 SHA256，引发"假阳"重新生成。

---

#### 状态 C：增量重新生成流程

#### Step 6.5.5：主 Claude 自己检测源 MD 是否有变化（轻量动作，不派单）

1. **读** `openapi.yaml` 的 `info.x-aidp-source.sha256`（`python3 -c` 取值或 grep，不必读全文）
2. **Bash 跑** Step 6.5.4 契约 B 的 Python 代码（实参替换 `<本地 MD 路径>`），得到当前 SHA256
3. 对比：
   - **一致** → 终端 INFO：「对外接口 openapi.yaml 与本地 MD 一致（sha256 匹配），无需重新生成」；在 `activeContext.md` 追加 `- {ts} 对外开放接口 openapi.yaml 与 MD 一致（sha256 匹配，无需重新生成）`；跳到 Step 7
   - **不一致** → 进入 Step 6.5.6

#### Step 6.5.6：询问 + 派单子 Agent 覆盖式重新生成

- **交互式**：用 `AskUserQuestion` 工具（单选）：

  ```
  问题：检测到本地「对外开放接口.md」自上次生成 openapi.yaml 以来有变化。是否重新生成（覆盖 openapi.yaml）？
    - 重新生成（覆盖式；如有人手改过 openapi.yaml，改动将丢失）
    - 跳过（用户自负后续同步责任）
  ```

- **无人值守（`--unattended`）**：不弹窗，默认「重新生成」。

**选「跳过」**：
- 终端 WARN：「openapi.yaml 与本地 MD 不一致（当前 sha256 = X，上次生成 sha256 = Y），用户跳过本次重新生成；下次重跑 /sprint-design 仍会提示」
- 在 `activeContext.md` 追加 `- {ts} 对外开放接口 MD 已变更但用户选择跳过 openapi.yaml 重新生成`
- 跳到 Step 7

**选「重新生成」**：主 Claude 派单前同 Step 6.5.3 三步准备，调 `Agent`。**任务指令模板** = Step 6.5.3 模板，差异仅以下三处：
- 首行角色改为「对外开放接口 OpenAPI 增量重新生成」子 Agent
- 第 2 步前增加：Read 现有 `openapi.yaml`，**保留**其中与 MD 无冲突的 `x-` 扩展字段与 `tags` 描述，其余按 MD 全量重写（覆盖式）
- 失败处置 JSON 的 `mode` 取 `"increment"`；YAML 校验失败时**恢复**为重新生成前的原文件（先备份到内存再写），而非删除

**主 Claude 派单后**：
1. 在 `activeContext.md` 追加：`- {YYYY-MM-DD HH:MM:SS} 对外接口 OpenAPI 文档已派单子 Agent 生成（模式：增量）`
2. 终端打印「已派单子 Agent 重新生成 `openapi.yaml`。」
3. 跳到 Step 7

> **状态记录小结**：4 个分支（已派单首次 / 一致跳过 / 用户跳过 / 已派单增量）的 `activeContext.md` 记录指令已分散在各分支末尾；「保持仅 MD」分支不在 activeContext 留痕。最终成功/失败由子 Agent 写入 stdout + `.aidp-openapi-sync-error.json`。本步无独立 Step 6.5.7。
