# Go 设计落地细则

> 技术栈选定为 Go（或探测到 `go.mod`）时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`（选型期全量看）。

---

## 一、核心原则 16：HTTP 客户端配置驱动 —— Go 落地

| 场景 | 落地方式 |
| :- | :- |
| **Go-Zero（带服务发现）** | `zrpc` + `httpx`，与 etcd / consul 深度集成；服务名走注册中心，不写 IP |
| **Gin / Echo / Fiber** | `net/http`（标准库、零依赖）或 `go-resty/resty`，直连配置文件 base URL |

A.2「HTTP 客户端落地」须给出 client 初始化示例 + `config.yaml` 配置块，所有可变项走环境变量：

```yaml
thirdParty:
  alipay:
    baseUrl: ${ALIPAY_BASE_URL}
    connectTimeout: 3s
    readTimeout: 10s
```

**严禁**：`http.Get("http://192.0.2.100:8080/api")` 这类硬编码 base URL / IP / 端口 / 凭证。D.3 依赖列表须列出所选客户端（如 `github.com/go-resty/resty/v2`）。

### 失败返回契约（Critical）

同一调用链失败返回三选一并全链路统一。Go 惯用**显式返回 `error`**：

```go
// ❌ 吞错返零值：调用方以为"没数据"，实际是下游挂了
if err != nil { log.Error(err); return []Item{} }
// ✅ 向上返回 error，由调用方决定降级还是失败
if err != nil { return nil, fmt.Errorf("query alipay: %w", err) }
```

---

## 二、检查项 11：字典/枚举 —— Go 侧

| 项 | Go 取值 |
| :- | :- |
| 枚举定义方式 | 具名类型 + `const` 块（`type OrderStatus int` + `iota` 或显式 code） |
| 文件路径 | `internal/enums/order_status.go` 或 `pkg/enums/` |
| code/label/description | 用 `map[OrderStatus]EnumMeta` 或每个枚举一个 `Meta()` 方法承载三件套 |
| 数据库映射 | 实现 `driver.Valuer` / `sql.Scanner`（GORM 亦可用自定义类型） |

常量名 `UPPER_SNAKE_CASE` 或 Go 惯用 `PascalCase`（**须在设计中显式声明选哪种并全项目统一**）。code/label 必须与前端一致。

**不允许例外**：即便只有 2 个候选值也必须定义具名类型，严禁裸字符串/裸数字散落业务代码。

---

## 三、配置文件位置

`etc/*.yaml`（Go-Zero 约定）或 `config/config.yaml`；对既有项目沿用历史目录。

---

## 四、后端第三方 mock 的运行时可控

```go
// ❌ 构建期隔离：build tag 在编译期决定，部署后不可切换
//go:build dev

// ✅ 运行时配置开关
if cfg.ThirdParty.MockEnabled { return mockData, nil }
```

---

## 核心原则 24：并发加锁选型 —— Go 落地

- **P0 进程内锁（首选）**：`sync.Mutex` / `sync.RWMutex`（读多写少）；`sync.Once`（一次性初始化）；`golang.org/x/sync/singleflight`（并发同 key 请求合并，防缓存击穿）。⚠️ Go 惯例优先用 **channel 传递所有权**替代共享内存加锁，能用 channel 表达的不必上锁。
- **P1 Redis 分布式锁**：`go-redis` 执行 `SET key val NX PX ttl`（`client.SetNX(ctx, k, v, ttl)` **单次原子**），释放走 Lua 校验 owner；长任务用独立 goroutine 定期续期（自建看门狗，Go 侧无 Redisson 等价物）。
- **P2 数据库级锁**：`SELECT ... FOR UPDATE`（`sqlx`/`GORM` `Clauses(clause.Locking{Strength: "UPDATE"})`）、`GET_LOCK()`。⚠️ **默认不可用，必须人为确认**（见检查项 32）。
- **锁与 `defer`**：`mu.Lock(); defer mu.Unlock()` 是标准写法；分布式锁**不要**照搬 `defer` 直接删 key，必须先校验 owner。

---

## 五、本栈不适用

`@Profile` / `@RefreshScope` / MyBatis TypeHandler 等为 Spring 生态概念；包组织规范见 Go 社区惯例（`internal/` + `pkg/`），设计须在 A.1 明确。前端侧见 `stack-vue.md` / `stack-react.md`。
