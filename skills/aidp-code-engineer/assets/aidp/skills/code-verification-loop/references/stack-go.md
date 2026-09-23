# Go 审计细则（Gin / Go-Zero / Echo / Fiber）

> 探测命中 `go.mod` 时加载本文件。跨技术栈的通用判据见 `../SKILL.md`。

---

## 一、维度 3：context-path（路由分组前缀）检测

| 框架 | 前缀配置位置 |
| :- | :- |
| Gin | `router.Group("/prefix")` |
| Echo | `e.Group("/prefix")` |
| Fiber | `app.Group("/prefix")` |
| Go-Zero | `.api` 文件的 `@server(prefix: /prefix)` 或 `rest.WithPrefix` |

检出前缀后，须核对前端 `baseURL` 是否包含它——否则按接口文档直调 404。前端侧判据见 `stack-vue.md` / `stack-react.md`。

> ⚠️ **嵌套 Group 陷阱**：`v1 := router.Group("/api"); v1.Group("/v1")` 的**实际前缀是 `/api/v1`**。核对时须沿 Group 链累加，只看最外层会漏掉后半段。

---

## 二、维度 4：Go 专有检查项

### 2.1 金额字段类型守恒（🔴 Critical）

设计 A.3 金额字段为 `BIGINT` 时，struct 字段必须用 `int64`，**严禁 `float64`**（浮点累加误差直接造成对账不平）。JSON 序列化若可能超过前端 JS Number 安全上限（2^53），须用 `string`：

```go
Amount int64 `json:"amount,string"`   // 序列化为字符串，避免前端丢精度
```

### 2.2 依赖越界基线（`go.mod`·需人工核对）

```bash
python3 <SKILL_DIR>/scripts/scan_code_conventions.py <代码目录> --checks dep-baseline [--base <ref>]
```

⚠️ **Go 的 `import` ↔ `go.mod` module 映射无法离线可靠完成，脚本不覆盖**——须 Agent 据 `go.mod` 人工核对新增 import 的 module 路径是否已声明。命中即越界 → 补进清单（经评估）或移除 → 🟡 Important（引入未评估的第三方/重型依赖升 🔴 Critical）。

> 📌 `go mod tidy` 会自动把新 import 写进 `go.mod`，所以「未声明」在 Go 里较少见；本项真正要拦的是**未经评估就引入重型/低维护度依赖**，须看 `go.mod` diff 而非只看能否编译。

### 2.3 单文件行数阈值

Go ≤ 500 行（不含 import + 注释），超阈值告警、2 倍升 Critical；单函数 ≤ 50 行硬阈值。

```bash
python3 <SKILL_DIR>/scripts/check_file_complexity.py <代码目录>
```

### 2.4 错误处理（Go 惯用法）

`err` 被 `_` 丢弃、或只 `log` 不返回导致调用方拿不到失败信号 → 🟡 Important；**对外 HTTP 调用的 err 被吞掉后返回零值**（调用方无法区分「业务真空」与「系统故障」）→ 🔴 Critical，对应 dev-logic-architect 核心原则 16「失败返回契约 ⟷ 调用方失败判定对齐」。

```bash
grep -rn "_ = .*Err\|_, _ =" --include="*.go" <代码目录>
```

---

## 三、本栈不适用的检查项

- 维度 7「CSS 预处理器一致性」为 Vue 专属，**Go 项目整维度跳过**
- 维度 8「请求通道 URL 拼装」扫的是前端源码（`.ts`/`.js`/`.vue`/`.tsx` 等，完整清单见 `dimension-6-9-stack-gated.md` 维度 8「扫描范围」），**纯 Go 后端整维度跳过**；若同仓含前端目录，该维度对那部分仍生效
- 维度 6「DI 依赖可解析性」为 Java/Spring 专属，**Go 项目整维度跳过**（Go 主流是显式构造注入，无运行期容器解析这一环，不存在「编译过但启动期找不到 bean」的类别）。
- 后端专有的 `@RefreshScope` 热刷新、DB 约束校验注解为 Spring 生态概念；Go 侧对应检查是「配置热加载是否生效」与「入参校验（`validator` tag）是否覆盖设计 A.3 约束」，判据同 `dimension-4-5-quality-debt.md` 维度 4 对应行，此处不重复。
- 前端专有项见 `stack-vue.md` / `stack-react.md`。
