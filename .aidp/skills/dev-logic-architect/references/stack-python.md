# Python 设计落地细则

> 技术栈选定为 Python（或探测到 `requirements.txt`/`pyproject.toml` + `*.py`）时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`。

---

## 一、核心原则 16：HTTP 客户端配置驱动 —— Python 落地

| 场景 | 落地方式 |
| :- | :- |
| **FastAPI 异步项目** | 首选 `httpx`（同时支持同步/异步），用 `AsyncClient` 复用连接池 |
| **Django 同步项目** | `requests` 即可 |

A.2 须给出 client 初始化示例 + `.env` 配置块：

```python
# ❌ 严禁硬编码
client = httpx.AsyncClient(base_url="http://192.0.2.100:8080")
# ✅ 配置驱动
client = httpx.AsyncClient(base_url=settings.ALIPAY_BASE_URL, timeout=settings.ALIPAY_TIMEOUT)
```

D.3 依赖列表须列出所选客户端（`httpx` / `requests`）及版本约束。

### 失败返回契约（Critical）

同一调用链失败返回三选一并全链路统一。**严禁** `except Exception: return {}`——系统故障被静默降级为空数据，调用方无法区分于业务真空。推荐抛自定义异常交由 FastAPI `exception_handler` / Django middleware 统一转错误码。

---

## 二、检查项 11：字典/枚举 —— Python 侧

| 项 | Python 取值 |
| :- | :- |
| 枚举定义方式 | `enum.Enum` / `enum.IntEnum`（含 `code`/`label`/`description` 属性） |
| 文件路径 | `app/enums/order_status.py` |
| 数据库映射 | SQLAlchemy `Enum` 类型 或 `TypeDecorator`；Django `choices=` |

常量名 `UPPER_SNAKE_CASE`。code/label 必须与前端一致。**即便只有 2 个候选值也必须定义枚举类**，严禁裸字符串散落业务代码。

---

## 三、配置文件位置

`.env` + `pydantic-settings`（FastAPI）或 `settings.py`（Django）；密钥走环境变量，**严禁写进 `settings.py` 提交**。

---

## 四、后端第三方 mock 的运行时可控

```python
# ❌ 构建期/导入期常量隔离
if DEBUG: from .mocks import alipay_mock
# ✅ 运行时配置开关
if settings.THIRD_PARTY_MOCK_ENABLED: return mock_data
```

---

## 核心原则 24：并发加锁选型 —— Python 落地

- **P0 进程内锁（首选）**：同步代码用 `threading.Lock` / `RLock`；异步（FastAPI / asyncio）用 `asyncio.Lock`。⚠️ **两者不可互换**——`asyncio` 事件循环里用 `threading.Lock` 会阻塞整个循环。
- **⚠️ 多进程部署是 Python 的常态陷阱**：`gunicorn -w 4` / `uvicorn --workers N` 下各 worker 是**独立进程**，`threading.Lock` **跨 worker 完全无效**。故 Python 项目判"P0 是否够用"时，**必须先确认部署是单 worker 还是多 worker**，这一点比其它语言更容易踩空。多 worker → 直接升 P1。
- **P1 Redis 分布式锁**：`redis-py` 的 `Redis.lock(name, timeout=..., blocking_timeout=...)`（内置 owner 校验与释放安全）；或手写 `set(k, v, nx=True, px=ttl)` **单次原子** + Lua 释放。
- **P2 数据库级锁**：`SELECT ... FOR UPDATE`（SQLAlchemy `with_for_update()`、Django `select_for_update()`）。⚠️ **默认不可用，必须人为确认**（见检查项 32）。
- **GIL 不是锁**：GIL 只保证字节码级原子性，**不保证业务临界区原子**（`x += 1` 都不安全），不能拿它当免锁理由。

---

## 五、本栈不适用

`@Profile`/`@RefreshScope`/MyBatis TypeHandler 为 Spring 生态概念。前端侧见 `stack-vue.md` / `stack-react.md`。
