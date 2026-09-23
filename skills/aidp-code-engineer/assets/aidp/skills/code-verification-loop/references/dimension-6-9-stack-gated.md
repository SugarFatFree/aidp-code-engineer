# code-verification-loop · 维度 6（DI 依赖可解析性）· 维度 7（CSS 预处理器）· 维度 8（请求通道 URL）· 维度 9（WebMCP）

> 本文件是 `SKILL.md` 的按需加载分片：执行到对应维度 / 步骤时 Read。通用判据（严重度定义、三方冲突裁决、最高约束「全程静态」、基线对照有效性铁律）以 `SKILL.md` 为准，本文件不重复。

#### 维度 6: DI 依赖可解析性（技术栈门控·Java/Spring）

> 🎯 **补的是一个结构性盲区**：维度 1~5 没有任何一项覆盖**「编译期完全无感、只在容器启动期才解析」**的错误。最典型：`@Autowired private RestTemplate restTemplate;` 但全项目没有任何 `RestTemplate` 的 `@Bean`——`mvn compile` **必过**，容器启动直接 `APPLICATION FAILED TO START`。反馈周期是「提交 → 推送 → CICD → 部署 → 启动失败」**十几分钟起**，还污染部署记录；无人值守批量场景下**一个 DI 错误让整批 Sprint 部署验证空转**。而它本可被一条 grep 静态拦下。

**跨栈通用口径（此处只写这些，细则按栈加载）**：

| 项 | 口径 |
| :- | :- |
| **分析方式** | 纯文本静态分析（grep 级）——**不编译、不打包、不起服务、不起容器**，成本与维度 4 现有 grep 类检查同量级 |
| **判定主线** | 对注入点提取注入类型 T，**三源命中任一即判可解析**：① 项目内组件注册 ② 显式工厂声明 ③ 框架自动装配白名单 |
| **severity** | **精度优先、零误阻断**——Critical 只给「近乎确定不可解析」的少数几类；「多候选无消歧」「接口无实现」「全仓无来源」一律 **Warn 不阻断**（框架多有兜底解析路径，静态不能判死）。**把这些判 Critical 会误报一片、噪音淹没真问题** |
| **提示语要求** | 命中不可解析时**必须一并给出「本项目同类型现有怎么用」**（grep `new T(` 等），把一次告警直接变成一次修复 |
| **技术栈门控** | **扫不到该栈源码即整维度跳过**（不计入通过/不通过），不影响其它技术栈的验收结论 |

**⚠️ 按需加载技术栈细则**（判定表、severity 分档、脚本命令、问题模式与修复，全在对应文件内）：

| 被测技术栈 | 加载 | 落地状态 |
| :- | :- | :-: |
| Java / Spring | `references/stack-java-spring.md` §一 | ✅ 有硬门脚本 `check_di_resolvability.py` |
| Node.js / NestJS | `references/stack-nodejs.md` §五 | ⏭️ **门控上跳过、不阻断**；但同类缺口真实存在，见该文件的非阻断提醒 |
| Python / FastAPI·Django | `references/stack-python.md` §三 | ⏭️ **门控上跳过、不阻断**；同上 |
| Go / 前端 Vue·React | 各自 `stack-*.md` | ⏭️ 不适用，整维度跳过 |

> ⚠️ **「跳过」与「人工核对」不是两种口径，别读成矛盾**：本维度的**门控判据是「扫不到该栈源码」**——`check_di_resolvability.py` 只扫 `.java`，故 Node/Python 项目一律**整维度跳过、不计入通过/不通过、不阻断验收**。各栈文件里写的「须人工核对」是**非阻断提醒**（NestJS 的 `@Module.providers`、FastAPI 的 `Depends()` 确有同类启动期错误，只是本 SKILL 尚未落地对应脚本），**不构成该维度的通过条件**，也不因未做而判不通过。

**与其它维度的边界（不重复登记）**：本维度只管**「容器能否装配起来」**这一启动期语义；维度 4「新增依赖/import 越界基线」管依赖清单登记、维度 4「配置中心热刷新漏标」管热刷新注解、维度 5 管技术债，三者与本维度正交。同一处问题只在本维度登记。

#### 维度 7: CSS 预处理器一致性（技术栈门控·Vue）

> 🎯 **与维度 6 同类的另一个结构性盲区，只是炸在构建期而非启动期**：`vue-tsc --noEmit` 与 `eslint` **都不编译 `.vue` 的 `<style>` 块**。于是新增 SFC 写了 `<style scoped lang="scss">`、而项目只装了 `less`，开发期轻量验证**全绿**，推送后 CI `vite build` 才报 `loadSassPackage` 失败。
>
> **注意这里不主张把完整构建塞进开发期**——「开发期只做轻量验证、不做完整构建」这条规定是对的，不该为了这类问题去推翻它。本维度是纯静态比对，零构建、零安装，成本与一次 grep 同量级，正好补上那条规定留下的这道缝。

**判定口径**：

| 项 | 口径 |
| :- | :- |
| **扫描范围** | 本次改动涉及的 `.vue`（全量扫目录也支持，用于首次接管存量项目） |
| **判定主线** | 逐个 `<style ... lang="X">` 取 X → 查所需 npm 包是否在**就近向上**的 `package.json`（`dependencies`/`devDependencies` 等）已声明。`scss`·`sass` → `sass`\|`sass-embedded`\|`node-sass`；`less` → `less`；`styl`·`stylus` → `stylus`；无 `lang` 或 `lang="css"` 不参与判定 |
| **monorepo** | **必须一路向上合并到 git 根**——依赖常被提到根 `package.json`（依赖提升），只看最近那份会误报一片 |
| **severity** | 未声明 = **🔴 Critical**（CI 构建**必**失败，阻塞级，回 `/sprint-bugfix`）；已声明但与**全库众数 lang** 不一致（孤例）= **🟡 Warn**（疑似写错，不阻断——项目有意混用两种预处理器是合法的） |
| **技术栈门控** | **扫不到 `.vue` 即整维度跳过**（不计入通过/不通过），不影响其它技术栈的验收结论 |

**硬门脚本**（零依赖纯标准库，`--json` 供 Agent 解析，退出码 `1` = **闸门未通过**——默认即「有阻塞级 ERROR」，`--strict` 下 WARN 同样计入）：

```bash
# 只查本次改动的文件（推荐）
python3 <SKILL_DIR>/scripts/check_vue_style_preprocessor.py <改动的 .vue 列表> --json
# 首次接管存量项目时全量扫
python3 <SKILL_DIR>/scripts/check_vue_style_preprocessor.py <前端目录>
```

退出码 `0`（闸门通过）/ `1`（未通过）/ `2`（输入错误：目标路径不存在、`--baseline-root` 不是目录）。

输出含 `{passed, gate_passed, strict, skipped, scanned_files, checked_style_blocks, majority_lang, lang_distribution, baseline_root, errors, warns}`（11 个，与脚本 `result` 一一对应）——**判「过没过」读 `gate_passed`**（`--strict` 下 WARN 也计入），`passed` 恒只看 ERROR；`skipped=true` 表示未扫到 `.vue`、整维度跳过。**实测**（一个实际 Vue 前端项目的 `src/`）：48 个 `.vue` / 41 个 `<style>` 块 → 0 ERROR、2 WARN（39 处 scss 中的 2 处 less 孤例，`less` 确已声明），零误阻断。

> 📌 **本维度的脚本接口事实**（上面这段：JSON 字段清单、`passed`/`gate_passed` 语义、退出码、实测数字）**以本节为单一信源**，`references/stack-vue.md` 不再复制一份——与维度 8 同一条规则（脚本一改，抄件必漂移）。

**覆盖边界（别当已查）**：本维度只查「`<style lang>` 声明的预处理器有没有在 `package.json` 声明」。`@import`/`@use` **路径是否存在不在覆盖内**（别名 `@/`、`~`、sass partial 省略规则叠加后静态解析误报率高），改动新增 `@import`/`@use` 时须由验收 Agent 人工核对被引文件存在；`lang` 拼错（如 `sccs`）落在「未知值 = 🟡 Warn」一档、**不阻断**，需人工看一眼。误报控制见 `references/stack-vue.md` §4.3。

**⚠️ 按需加载技术栈细则**：

| 被测技术栈 | 加载 | 落地状态 |
| :- | :- | :-: |
| Vue | `references/stack-vue.md` §CSS 预处理器一致性 | ✅ 有硬门脚本 `check_vue_style_preprocessor.py` |
| React / 其它前端 | `references/stack-react.md` | ⏭️ 不适用（无 SFC `<style lang>` 机制），整维度跳过 |
| 纯后端（Java·Go·Python·Node） | — | ⏭️ 不适用，整维度跳过 |

**与其它维度的边界（不重复登记）**：本维度只管**「`<style lang>` 声明的预处理器有没有装」**这一构建期语义。维度 4 的「新增依赖/import 越界基线」管的是**依赖被引入却未登记**（方向相反：那边是装了没登记，这边是用了没装），维度 4 的样式一致性支柱管**视觉还原**、不看预处理器。同一处问题只在本维度登记。

#### 维度 8: 请求通道 URL 拼装单一信源（技术栈门控·前端）

> 🎯 **与维度 6/7 同类的第三个盲区，炸在运行期**：类型检查与 lint 全绿，**只有真实发出请求才暴露**。实际项目中曾出现——新增的 SSE 封装 `runSseTask` 无条件拼了 `import.meta.env.VITE_API_BASE_URL`，而接口常量 `/demo-app/ai/...` **本就含 context-path**，再拼一次 base → 请求打到 `/demo-app/demo-app/ai/...` → **404**。
>
> 关键在于**根因是结构缺陷、不是手误**：同项目 `http.ts` 的 `resolveConfig`、`ssePost` **早已有两处正确判断**，注释白纸黑字写着 `must bypass baseURL to avoid doubling`——但写第三处的人**没有任何机制被提醒「这里有坑、且已有答案」**。同一 URL 判据散落多份、各写各的，第 N 份重踩同坑只是时间问题。所以本维度查的不是「这一处拼对没拼对」（静态拿不到 env 值，判不了），而是**「这条判据是不是只有一处实现」**。

**判定口径**：

| 项 | 口径 |
| :- | :- |
| **扫描范围** | 前端源码 `.ts/.js/.mjs/.cjs/.mts/.cts/.tsx/.jsx/.vue`（`.vue` 只看 `<script>` 块）；默认排除 `node_modules`/`dist`、`*.min.js`/`*.d.ts`、`*.config.ts\|js`（vite proxy 里拼 base 是正常的） |
| **计入的「自拼点」** | 须**同时**满足两条：① 出现 base 拼装形态（`` `${base}${url}` `` 模板 / `base + url` 加号，base 含 `import.meta.env.*_BASE_URL`、`process.env.*_BASE_URL`、`baseUrl`/`baseURL`/`apiBase` 等标识符，以及**本文件内由这些赋值而来的局部别名**）② **所在文件里有请求发起点**（`fetch(`/`new EventSource(`/`new WebSocket(`/`axios.*(`/`.getReader()` 等） |
| **为什么要条件 ②** | 自拼 base 有大量**合法非请求**用法：页面跳转 `location.href = \`${base}/logout\``、`new HttpClient(config.baseUrl)` 传参、`resolvePath(base, url)` 函数式传参。逐点命中即报会误报一片（实测 aidp-code-engineer 里正是这几种形态） |
| **判定主线（结构信号）** | 自拼 base 在项目里有**唯一合法位置** = URL 解析单一信源本身（`resolveApiUrl` 之类）。故**不是逐点命中即报**：计入自拼点散落在 **≥2 个不同文件 = 平行实现 → 🔴 Critical**；**只有 1 个文件 → 放行**，并把它报为「认定的单一信源」 |
| **severity 与存量** | 传 `--changed <本次改动文件>` 时，≥2 文件的前提下**只有落在改动文件里的自拼点判 Critical**，其余降 🟡 Warn（存量技术债不该卡本轮验收）。传 `--allow <单一信源 glob>` 时口径反转：**信源之外只要有一处就是 Critical**（哪怕全项目仅此一处），因为它就是平行于已声明信源的第二份 |
| **技术栈门控** | **扫不到任何前端源码即整维度跳过**（不计入通过/不通过）。与维度 7 不同，本维度**不限 Vue**——React / 原生 TS 前端同样适用 |

**硬门脚本**（零依赖纯标准库，`--json` 供 Agent 解析，退出码 `1` = **闸门未通过**——默认即「有阻塞级 ERROR」，`--strict` 下 WARN 同样计入）：

```bash
# 验收本次改动（推荐）：存量平行实现降为 Warn，只有本次碰的那份判 Critical
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --changed <本次改动的文件...> --json
# 项目已明确 URL 解析单一信源时，口径收紧为「信源之外一处都不许有」
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --allow 'src/utils/apiUrl.ts'
# 首次接管存量项目：全量看结构分布
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录>
```

退出码 `0`/`1`/`2`。**安全失败**（宁可报参数错，也不给假绿灯）有两条：① `--changed` 的路径**全部不存在** → exit 2，而不是把所有平行实现降级为 Warn（参数写错导致闸门静默放行，是最危险的方向）；部分写错则只告警、继续跑。② `--max-file-bytes` ≤ 0 → exit 2，否则每个文件都被判超限跳过 = 整道闸门被静默关掉。`--allow` 的 glob 一个都没匹配上时告警；**`--allow` 与 `--changed` 同传时 `--allow` 口径优先、`--changed` 的存量降级不生效**（会打一条 stderr 提示）。

输出为 `{passed, gate_passed, strict, skipped, repo_root, scanned_files, concat_sites, distinct_files, distinct_file_list, single_source, changed_unresolved, allow_matched_files, allow_unmatched_globs, ignored_no_request_call, skipped_large, unreadable_files, errors, warns}`（18 个字段，与脚本 `result` 一一对应）——**判「过没过」读 `gate_passed`**；`single_source` 非空表示自拼点全部集中在这一个文件、已认定为单一信源（⚠️ **传了 `--allow` 时 `single_source` 恒为 `null`**——此口径下信源由参数声明而非脚本推断，命中的信源文件落在 `allow_matched_files`，别把 `null` 读成「没找到单一信源」）；`ignored_no_request_call` 是「有 base 拼装但所在文件无请求发起点」的非请求通道用法，**列出来供人扫一眼但不计入**；`unreadable_files` 是权限不足/断链符号链接等**未能参与检查**的文件，**不等于干净**，需人工确认。**实测**（一个实际 Vue 前端项目的 `src/`）：124 个前端文件 → 0 自拼点、0 ERROR，另有 1 处 `ignored_no_request_call`（`location.href` 登出跳转），零误阻断；上游翻车场景的复刻 fixture（`http.ts` 两处 + 新增 `sse.ts` 一处）→ 3 ERROR、exit 1，`--changed src/api/sse.ts` 时精确只把新增那处判 Critical、另两处降 Warn。

**覆盖边界（别当已查）**：

- **不判断拼出来的 URL 对不对**——静态拿不到 env 值，「到底重没重复 context-path」判不了，只判「判据有没有平行实现」。
- **只认两种拼装形态**：`` `${base}...` `` 模板与 `base + url` 加号（`+` 两侧可跨行）。`[base, url].join('')`、`base.concat(url)`、`new URL(url, base)`、`full += url` **一律不认**。
- **base 别名解析是单跳、不传递**：`const base = env.X; const b2 = base;` 里 `b2` 不算 base（除非中间那个名字本身就在 base 词表内）；`const { VITE_API_BASE_URL } = import.meta.env` 这类**解构不认**，裸的 `VITE_*` 常量名也不在词表内。
- **不跟踪跨文件变量传递**，且**条件 ② 同样是文件级、能被跨文件击穿**：`const u = ...拼装...; request(u)` 里 `request` 从别处 import、本文件没有请求发起点 → 落入 `ignored_no_request_call` 不计入。这是为去噪付出的代价，请扫一眼该清单。
- **只看文件级分布**：同一个文件里写了 N 份平行判据**不判**（`distinct_files` 仍是 1、照样放行）——注意上游翻车案例里 `http.ts` 内部本就有 `resolveConfig` + `ssePost` 两份，这一半靠人工看。
- **正则字面量按启发式识别**（值位置的 `/` + 同行闭合 + **体内确含引号/反引号/`/`**）并整体跳过，避免正则里的引号或**反引号**让词法状态机串味。第三条约束不可省：只在候选体内真的含有会串味的字符时才抹白，否则「除法 / JSX 被误判成正则」会把中间真代码整段吃掉 → 真自拼点漏检 → **假绿灯**。另对 JSX/TSX 专门排除 `/>`（自闭合）与 `</`（闭合标签）——`.tsx/.jsx` 同样在扫描范围内，`<Foo a={b} /> … <Bar />` 这类同行两处会让中间整段被抹白。该启发式不是完整 JS 词法分析，除法与正则的极端歧义写法（如 `if (x) /re/.test(y)` 这种 `)` 之后的正则）仍可能判错。
- 超过 `--max-file-bytes`（默认 2MB）的文件跳过不扫，跳过项明列在 `skipped_large`、不静默丢弃。

**⚠️ 按需加载技术栈细则**：

| 被测技术栈 | 加载 | 落地状态 |
| :- | :- | :-: |
| Vue | `references/stack-vue.md` §五 | ✅ 有硬门脚本 `check_request_channel_url.py` |
| React / 其它前端 | `references/stack-react.md` §四 | ✅ 同一脚本，判据与 Vue 一致（本维度不依赖 SFC 机制） |
| **Node 服务端**（Express·Koa·NestJS） | `references/stack-nodejs.md` §五 | ✅ **不跳过**——源码本身就是 `.ts/.js`，调下游服务同样会「多处各自拼 base」，同一脚本同一判据 |
| 纯后端（Java·Go·Python） | — | ⏭️ 无前端源码可扫，整维度跳过 |

**与其它维度的边界（不重复登记）**：

- **维度 3 / `stack-vue.md` §三「baseURL 与 context-path 拼接」** 管**配置侧一次性设定**——base 里**该不该**含 context-path。**本维度管结构侧**——那条判据**有几份实现**。二者正是这个 bug 的两半：base 含 context-path、接口常量也含，谁拼谁不拼**必须由单一信源统一决定**；只要有第二份实现，两边迟早各自表述。同一处问题按「配置值错」记维度 3、按「判据被复制」记维度 8，不重复登记。
- **维度 4「HTTP 客户端配置硬编码」** 管的是**端点/凭证被写死进源码**（该走配置驱动），与「拼装判据有几份」正交。
- **维度 5** 只收非阻断技术债，本维度命中的平行实现属结构性缺陷，**不降级到维度 5**。

#### 维度 9: WebMCP 前端能力实现合规（**条件启用**·`webmcp_enabled` 门控）

> 🎯 **与维度 6/7/8 同一类的门控型维度，只是门控信号不同**：那三个由**技术栈**门控（扫不到该栈
> 源码即整维度跳过），本维度由**调用方入参**门控。判据同样是**纯静态分析**——符合本 SKILL
> 「不用跑起来」的立论，不启动浏览器、不发请求、不装任何东西。

**门控（先判这一条，再决定要不要往下看）：**

| 项 | 口径 |
| :- | :- |
| **启用条件** | 调用方显式传入 `webmcp_enabled: true`。**为 `false` 或未传 → 整维度跳过**：不计入通过/不通过、不影响其它维度结论、**不产生任何告警**、**不在验收报告里留行** |
| **⛔ 严禁自行探测** | 不 grep PRD、不扫代码找相关标识符。**Why：判定散落多处必然漂移，而一处判错就会给未启用的项目凭空长出 Critical。** 判定权归调用方，本 SKILL 只消费该输入 |
| **入口标识符** | 由 `webmcp_entry_symbols`（数组）传入。⚠️ **挂载位置已迁移过一次、规范仍在演进，脚本与文档都不得写死任何一个名字**——写死后的失效方向是「扫不到 → 0 命中 → **假绿**」。缺该入参时**报入参错而不是猜默认值** |

**六项检查（判据全文见 [`references/flow-webmcp.md`](./references/flow-webmcp.md)）：**

| # | 检查 | 判据要点 | severity |
| :-: | :- | :- | :-: |
| 9.1 | **单一适配层** | 入口标识符在前端源码里的**命中文件数必须 == 1**。⚠️ **注释里写了也算命中**——否则 grep 形同虚设（下游实际触发过这条） | 🔴 Critical |
| 9.2 | **无「先登记后撤销」时序** | 登记调用不得早于配置就绪；且**代码里出现 `unregisterTool` 即 Critical**（实测该 API 不存在，据草案臆想它存在会让撤销**静默失效**——下游曾用可选链做防御，撤销悄悄没生效、代码零报错、文档与实际不符） | 🔴 Critical |
| 9.3 | **错误契约无死文案** | 每个错误契约常量都有实际使用面。⚠️ 新增一条错误文案时须 grep **旧文案的全部使用点**逐一判断该不该改——只改「发现问题的那一处」会留下**姊妹路径**（下游真实踩过） | 🟡 Important |
| 9.4 | **写操作未绕开业务既有执行通道** | 工具的写操作必须复用业务既有执行通道，绝不另写一条。否则会出现「**手工操作能通、让助手做就不通**」，且两条链路的日志形态、参数校验、变量替换各不相同 | 🔴 Critical |
| 9.5 | **敏感字段未经工具通道外泄** | 凭据 / 密钥 / 令牌类的值一律不经工具通道返回，**包括脱敏片段**；只返回名称、位置、作用域这类元信息 | 🔴 Critical |
| 9.6 | **可调用对象用白名单而非黑名单** | 业务对象有多种类型时，工具暴露的集合必须**白名单列举**可调用类型。⛔ 黑名单会随类型增加而失效，把不可调用的对象放进去、助手拿它执行会产生意外副作用。**列表、详情、执行三处须共用同一判据，任一处放行即构成绕过** | 🔴 Critical |

**硬门脚本**（零依赖纯标准库，`--json` 供 Agent 解析）：

```bash
# 前两项是纯词法、零主观，已脚本化
python3 <SKILL_DIR>/scripts/check_webmcp_adapter.py <前端源码目录> \
    --entry-symbols <符号1> <符号2> ... --json
# 已声明单一适配层文件时，口径反转为「信源之外一处都不许有」
# ⚠️ --allow 的 glob 基准是**仓库根**、不是扫描目录：前端嵌在子路径下时必须写全路径，
#    写错会把「全项目唯一那处合法信源」判成平行实现（纯假红），故一个都没匹配上时直接 exit 2
python3 <SKILL_DIR>/scripts/check_webmcp_adapter.py <前端目录> \
    --entry-symbols <符号1> --allow 'code/frontend/web/src/webmcp/adapter.ts'
# 让「超限 / 不可读」这类未参与检查的缺口也卡住闸门（推荐验收时带上）
python3 <SKILL_DIR>/scripts/check_webmcp_adapter.py <前端目录> \
    --entry-symbols <符号1> --strict
```

退出码 `0`（闸门通过，含「扫不到前端源码 → 跳过」）/ `1`（未通过）/ `2`（入参或环境错：路径不存在、
缺位置参数、**未传 `--entry-symbols`**、`--max-file-bytes` 非正、显式传的文件全不在可扫类型内、
**`--allow` 一个 glob 都没匹配上**）。输出 19 个字段（清单与语义以 [`references/flow-webmcp.md`](./references/flow-webmcp.md) 为单一信源，本节不复述——脚本一改、抄件必漂移）——**判「过没过」读 `gate_passed`**；`skipped=true`
表示未扫到前端源码、整维度跳过，**不等于通过**，报告里须如实标「跳过（原因）」。

> ⚠️ **脚本只做 9.1 与 9.2 的 `unregisterTool` 两项。** 9.2 的时序、9.3~9.6 四项须由验收 Agent
> 静态读代码人工核对——**脚本全绿 ≠ 维度 9 通过**。

**⚠️ 概念前提（写错会让整维度查偏）：** WebMCP **不是网络协议、没有传输层**，消费方必须先能进入
该页面的 JS 上下文。故安全三项（9.4/9.5/9.6）的判据是「**对任意调用方都成立**」——能力入口是页面
JS 上下文里的普通对象，任何能在本页执行 JS 的主体都能调它，**不是**「助手会守规矩」。

**与其它维度的边界（不重复登记）：** 9.1 与**维度 8**是同一类结构判据的两个实例——都不判「这一处
写对没写对」，而判「**这条判据有几份实现**」；扫描对象不同（8 管 base 拼装、9.1 管能力入口适配），
各自登记。9.3 与**维度 3.7「出参字段变更消费点穷举」**形态同源（漏改姊妹路径），但对象不同，
同一处问题只登记一次。
