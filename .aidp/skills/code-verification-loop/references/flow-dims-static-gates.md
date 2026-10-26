# 静态门控维度 6 / 7 / 8 / 14 判据全文（DI 可解析性 · CSS 预处理器 · 请求通道 URL · 样式编译等价）

> 文中「核心原则 N」「最高约束」「输入要求」「Step N」「分片索引」均指 [`../SKILL.md`](../SKILL.md) 的同名章节；各维度的**强制结论**（档位、门控、机器门命令）在骨架里，本文件是它们的「怎么做」全文，**外置的是方法、不是强制度**。

#### 维度 6: DI 依赖可解析性（技术栈门控·Java/Spring）

> 🎯 **补的是一个结构性盲区**：维度 1~5 没有任何一项覆盖**「编译期完全无感、只在容器启动期才解析」**的错误。最典型：`@Autowired private RestTemplate restTemplate;` 但全项目没有任何 `RestTemplate` 的 `@Bean`——`mvn compile` **必过**，容器启动直接 `APPLICATION FAILED TO START`。反馈周期是「提交 → 推送 → CICD → 部署 → 启动失败」**十几分钟起**，还污染部署记录；无人值守批量场景下**一个 DI 错误让整批 Sprint 部署验证空转**。而它本可被一条 grep 静态拦下。

**跨栈通用口径（[`../SKILL.md`](../SKILL.md) 只写这些，细则按栈加载）**：

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

输出含 `{passed, gate_passed, strict, skipped, scanned_files, checked_style_blocks, majority_lang, lang_distribution, baseline_root, errors, warns, read_errors}`（12 个，与脚本 `result` 一一对应）——**判「过没过」读 `gate_passed`**（`--strict` 下 WARN 也计入；**有 `read_errors` 时恒为 false、exit 2**——读不出的 `.vue`/`package.json` 不等于没问题），`passed` 恒只看 ERROR；`skipped=true` 表示未扫到 `.vue`、整维度跳过。**实测**（某示例项目前端 `src/`）：48 个 `.vue` / 41 个 `<style>` 块 → 0 ERROR、2 WARN（39 处 scss 中的 2 处 less 孤例，`less` 确已声明），零误阻断。

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

> 🎯 **与维度 6/7 同类的第三个盲区，炸在运行期**：类型检查与 lint 全绿，**只有真实发出请求才暴露**。实测——新增的 SSE 封装 `runSseTask` 无条件拼了 `import.meta.env.VITE_API_BASE_URL`，而接口常量 `/demo-app/ai/...` **本就含 context-path**，再拼一次 base → 请求打到 `/demo-app/demo-app/ai/...` → **404**。
>
> 关键在于**根因是结构缺陷、不是手误**：同项目 `http.ts` 的 `resolveConfig`、`ssePost` **早已有两处正确判断**，注释白纸黑字写着 `must bypass baseURL to avoid doubling`——但写第三处的人**没有任何机制被提醒「这里有坑、且已有答案」**。同一 URL 判据散落多份、各写各的，第 N 份重踩同坑只是时间问题。所以本维度查的不是「这一处拼对没拼对」（静态拿不到 env 值，判不了），而是**「这条判据是不是只有一处实现」**。

**判定口径**：

| 项 | 口径 |
| :- | :- |
| **扫描范围** | 前端源码 `.ts/.js/.mjs/.cjs/.mts/.cts/.tsx/.jsx/.vue`（`.vue` 只看 `<script>` 块）；默认排除 `node_modules`/`dist`、`*.min.js`/`*.d.ts`、`*.config.ts\|js`（vite proxy 里拼 base 是正常的） |
| **计入的「自拼点」** | 须**同时**满足两条：① 出现 base 拼装形态（`` `${base}${url}` `` 模板 / `base + url` 加号，base 含 `import.meta.env.*_BASE_URL`、`process.env.*_BASE_URL`、`baseUrl`/`baseURL`/`apiBase` 等标识符，以及**本文件内由这些赋值而来的局部别名**）② **所在文件里有请求发起点**（`fetch(`/`new EventSource(`/`new WebSocket(`/`axios.*(`/`.getReader()` 等） |
| **为什么要条件 ②** | 自拼 base 有大量**合法非请求**用法：页面跳转 `location.href = \`${base}/logout\``、`new HttpClient(config.baseUrl)` 传参、`resolvePath(base, url)` 函数式传参。逐点命中即报会误报一片（实测示例项目里正是这几种形态） |
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

输出为 `{passed, gate_passed, strict, skipped, repo_root, scanned_files, concat_sites, distinct_files, distinct_file_list, single_source, changed_unresolved, allow_matched_files, allow_unmatched_globs, ignored_no_request_call, skipped_large, unreadable_files, errors, warns}`（18 个字段，与脚本 `result` 一一对应）——**判「过没过」读 `gate_passed`**；`single_source` 非空表示自拼点全部集中在这一个文件、已认定为单一信源（⚠️ **传了 `--allow` 时 `single_source` 恒为 `null`**——此口径下信源由参数声明而非脚本推断，命中的信源文件落在 `allow_matched_files`，别把 `null` 读成「没找到单一信源」）；`ignored_no_request_call` 是「有 base 拼装但所在文件无请求发起点」的非请求通道用法，**列出来供人扫一眼但不计入**；`unreadable_files` 是权限不足/断链符号链接等**未能参与检查**的文件，**不等于干净**，需人工确认。**实测**（某示例项目前端 `src/`）：124 个前端文件 → 0 自拼点、0 ERROR，另有 1 处 `ignored_no_request_call`（`location.href` 登出跳转），零误阻断；上游翻车场景的复刻 fixture（`http.ts` 两处 + 新增 `sse.ts` 一处）→ 3 ERROR、exit 1，`--changed src/api/sse.ts` 时精确只把新增那处判 Critical、另两处降 Warn。

**覆盖边界（别当已查）**：

- **不判断拼出来的 URL 对不对**——静态拿不到 env 值，「到底重没重复 context-path」判不了，只判「判据有没有平行实现」。
- **只认两种拼装形态**：`` `${base}...` `` 模板与 `base + url` 加号（`+` 两侧可跨行）。`[base, url].join('')`、`base.concat(url)`、`new URL(url, base)`、`full += url` **一律不认**。
- **base 别名解析是单跳、不传递**：`const base = env.X; const b2 = base;` 里 `b2` 不算 base（除非中间那个名字本身就在 base 词表内）；`const { VITE_API_BASE_URL } = import.meta.env` 这类**解构不认**，裸的 `VITE_*` 常量名也不在词表内。
- **不跟踪跨文件变量传递**，且**条件 ② 同样是文件级、能被跨文件击穿**：`const u = ...拼装...; request(u)` 里 `request` 从别处 import、本文件没有请求发起点 → 落入 `ignored_no_request_call` 不计入。这是为去噪付出的代价，请扫一眼该清单。
- **只看文件级分布**：同一个文件里写了 N 份平行判据**不判**（`distinct_files` 仍是 1、照样放行）——注意上游翻车案例里 `http.ts` 内部本就有 `resolveConfig` + `ssePost` 两份，这一半靠人工看。
- **正则字面量按启发式识别**（值位置的 `/` + 同行闭合 + **体内确含引号/反引号/`/`**）并整体跳过，避免正则里的引号或**反引号**让词法状态机串味。第三条约束不可省：只在候选体内真的含有会串味的字符时才抹白，否则「除法 / JSX 被误判成正则」会把中间真代码整段吃掉 → 真自拼点漏检 → **假绿灯**。另对 JSX/TSX 专门排除 `/>`（自闭合）与 `</`（闭合标签）——`.tsx/.jsx` 同样在扫描范围内，`<Foo a={b} /> … <Bar />` 这类同行两处曾让中间整段被抹白。该启发式不是完整 JS 词法分析，除法与正则的极端歧义写法（如 `if (x) /re/.test(y)` 这种 `)` 之后的正则）仍可能判错。
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

---

#### 维度 14: 样式重构编译等价性对照（技术栈门控·改动了样式时才触发）

> 🎯 **维度 7 的 🎯 已经点明「`vue-tsc` 与 `eslint` 都不编译 `<style>` 块」，但它只回答一件事：
> 预处理器有没有在 `package.json` 声明。** 样式**重构**（抽公共 / 参数化 / 移动位置）的正确性
> 目前**零覆盖**——而「类型检查过了」对样式**毫无意义**，这是使用者最容易误采信的一句话。
>
> **本维度仍是纯静态、零构建**：只编译**改动的样式段**、不打包、不起任何服务，
> 成本与维度 7 同量级，与最高约束第 0 条不冲突。

**方法（三步，改动前后各编译一次）：**

```
改动前的样式段 → 预处理器编译 → old.css
改动后的样式段 → 预处理器编译 → new.css
归一（压空白 / 单位等价形式统一）+ 排序 + diff  ⇒ 要求【零差异】
```

**这是样式重构目前唯一可行的静态正确性证明**——重构的定义就是「产物不变」，
产物一致即证明重构没有改变行为；产物有差异，那个差异要么是本次有意的、要么就是缺陷。

**实证价值（实际项目首轮对照就抓到两个会静默进产物的真问题，两者在 `vue-tsc` + `eslint` 下全绿）：**

| # | 问题 | 后果 |
| :- | :- | :- |
| ① | 作者写的**文档块注释**被编译进 CSS | 污染产物 29 行 |
| ② | 公共 mixin **无条件输出一条 `margin` 声明** | 给原本没有该声明的调用方**凭空加上** |

**判定口径：**

| 项 | 口径 |
| :- | :- |
| **触发条件** | 本次改动**涉及样式文件或 `<style>` 块**（`.scss` / `.less` / `.styl` / `.css` / `.vue` 的 `<style>`）。没动样式 = 整维度跳过 |
| **技术栈门控** | 扫不到前端样式源码 = 整维度跳过（不计入通过/不通过） |
| **编译器** | 用**被测项目自己的** `sass` / `lessc` / `stylus`（`./node_modules/.bin/…`），⛔ 不联网装、不全局装 |
| **判定** | 归一后仍有差异 = 🔴 **Critical**，除非差异**逐条被本次改动的意图解释**并写进报告 |
| **编译器缺失** | 标「不适用（预处理器未安装）」跳过，**报告仍留行**（与维度 10 / 12 / 13 同款：留行才能让阅读者知道这一档没跑过） |

**硬门脚本**（纯标准库，只做**归一 + 比较 + 基线有效性判定**这一段；两次编译由上面的命令产生）：

```bash
# 1) 取基线样式段并编译（示例，命令随项目而定）
git show HEAD:src/styles/card.scss > /tmp/old.scss && ./node_modules/.bin/sass --no-source-map /tmp/old.scss /tmp/old.css
./node_modules/.bin/sass --no-source-map src/styles/card.scss /tmp/new.css
# 2) 归一 + 比较
python3 <SKILL_DIR>/scripts/check_css_equivalence.py /tmp/old.css /tmp/new.css --json
```

退出码 `0`（等价且未新增注释块）/ `1`（有差异，含「仅顺序变化」「产物注释块增多」两类 Important）/ `2`（入参或环境错，含**基线无效**）。⚠️ **脚本本身没有 N/A 跳过分支**（两侧都空 = 两次编译都没跑起来，按 `2` 返回）；「没动样式 / 扫不到样式源码 / 编译器缺失」的跳过由调用方在**调用脚本之前**判定并在报告留行，⛔ 不要指望脚本返回 `0` 来表达跳过。`--json` 的 `comments_added: true` 即配套判据 1（块注释进产物）的机器信号。

**⚠️ 两条配套判据（并入本维度）：**

1. **公共样式文件的文档注释必须用行注释 `//`，⛔ 不用块注释 `/* */`。**
   预处理器会把 `/* */` **编译进产物**，`//` 不会。写给人看的说明进了 CSS 产物既没用又占体积
   （实测污染 29 行）。
2. **前端最低静态验证组合 = 类型检查（带阳性对照）+ lint（同文件集基线对照）+ 预处理器编译（改样式时）**，
   三者各有盲区、**缺一不可**：

   | 手段 | 能抓什么 | ⛔ 抓不到什么 |
   | :- | :- | :- |
   | **类型检查** | 类型错、未定义符号 | **不编译 `<style>`**；**模板语法错误零报错**（把注释写进标签的属性列表中间会导致整模板解析失败，而 `vue-tsc` 一声不吭） |
   | **lint** | 模板语法错、代码风格 | 不编译样式；不保证类型正确 |
   | **预处理器编译** | 样式语法错、产物差异 | 与逻辑正确性无关 |

   ⚠️ **「类型检查带阳性对照」不是废话**：`vue-tsc` 会因 `tsconfig` 的 `types` 指向未安装的包而
   **提前中止**，此时**源码零检查却报「0 错误」**——与本 SKILL 反复强调的「失效形态是 0 命中假绿」
   完全同源。跑之前先故意注入一个类型错误，确认它**能红**。

**与维度 7 的边界（不重复登记）：** 7 管**预处理器有没有装**（`<style lang>` 声明的包在不在
`package.json`），14 管**样式重构后产物变没变**。7 是「能不能编译」，14 是「编译出来一不一样」。

---
