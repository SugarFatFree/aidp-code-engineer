# Python 审计细则（FastAPI / Django / Flask）

> 探测命中 `requirements.txt` / `pyproject.toml` + `*.py` 时加载本文件。跨技术栈的通用判据见 `../SKILL.md`。

---

## 一、维度 3：context-path（路由全局前缀）检测

| 框架 | 前缀配置位置 |
| :- | :- |
| FastAPI | `APIRouter(prefix="/prefix")`；或 `app.mount("/prefix", sub_app)` |
| Django | 根 `urls.py` 的 `path('prefix/', include(...))` |
| Flask | `Blueprint('bp', __name__, url_prefix='/prefix')` |

检出前缀后，须核对前端 `baseURL` 是否包含它——否则按接口文档直调 404。前端侧判据见 `stack-vue.md` / `stack-react.md`。

> ⚠️ **嵌套 router 陷阱**：FastAPI 的 `app.include_router(r, prefix="/api")` 与 `APIRouter(prefix="/v1")` 会**叠加成 `/api/v1`**；核对时须沿 include 链累加。

---

## 二、维度 4：Python 专有检查项

### 2.1 金额字段类型守恒（🔴 Critical）

设计 A.3 金额字段为 `BIGINT` 时用 `int`；**若业务确需小数金额，必须用 `decimal.Decimal`，严禁 `float`**（浮点误差直接造成对账不平）。Pydantic 模型同理：

```python
amount: int                      # ✅ 分为单位的整数金额
amount: Decimal                  # ✅ 需小数时
amount: float                    # ❌ 禁止
```

### 2.2 依赖越界基线（`requirements.txt` / `pyproject.toml`）

```bash
python3 <SKILL_DIR>/scripts/scan_code_conventions.py <代码目录> --checks dep-baseline [--base <ref>]
```

取 `git diff <base>` 新增 import **+ untracked 新文件的全部 import**，与 `requirements.txt` / `pyproject.toml` 比对顶层包。

- 脚本**已排除 Python 内置模块**，本栈脚本覆盖度较好。
- ⚠️ **import 名 ≠ 包名**的常见坑：`import yaml` 对应 `PyYAML`、`import cv2` 对应 `opencv-python`、`import sklearn` 对应 `scikit-learn`、`import PIL` 对应 `Pillow`。脚本按顶层 import 名比对，这几类会误报——**Agent 须复核后再判定**，不要直接采信。
- 命中即越界 → 补进清单（经评估）或移除 → 🟡 Important（引入未评估的第三方/重型依赖升 🔴 Critical）。

### 2.3 单文件行数阈值

Python ≤ 600 行（不含 import + 注释），超阈值告警、2 倍升 Critical；单函数 ≤ 50 行硬阈值。

```bash
python3 <SKILL_DIR>/scripts/check_file_complexity.py <代码目录>
```

### 2.4 注释完备性（本栈形态）

类/函数声明下方须有 **docstring**（非声明上方，与 Java/TS 相反），含用途 + 参数 + 返回值 + 异常语义；字段注释写业务含义而非字段名直译。判据同 `dimension-4-5-quality-debt.md` 维度 4「注释完备性」行。

---

## 三、本栈不适用的检查项

- 维度 7「CSS 预处理器一致性」为 Vue 专属，**Python 项目整维度跳过**。
- 维度 8「请求通道 URL 拼装」扫的是前端源码（`.ts`/`.js`/`.vue`/`.tsx` 等，完整清单见 `dimension-6-9-stack-gated.md` 维度 8「扫描范围」），**纯 Python 后端整维度跳过**；若同仓含前端目录，该维度对那部分仍生效。
- 维度 6「DI 依赖可解析性」为 Java/Spring 专属，**Python 项目整维度跳过**。

  > 📌 **注**：FastAPI 的 `Depends()` 依赖注入若指向未定义/未导入的 provider，会在**请求期**（非启动期）报错；Django 的 `INSTALLED_APPS` 漏注册 app 则在**启动期**报 `ModuleNotFoundError`。二者与维度 6 拦的是同类问题，但本 SKILL 当前只落地了 Java/Spring 的静态检查脚本（`check_di_resolvability.py` 仅扫 `.java`），Python 侧**暂无脚本覆盖**，建议验收 Agent 人工扫一眼。**这是非阻断提醒、不是该维度的通过条件**——维度 6 对 Python 项目在门控上已整维度跳过，不计入通过/不通过。此处显式记录该缺口，只为避免被误读为「Python 项目不存在这类问题」。

- `@RefreshScope` 热刷新、DB 约束校验注解为 Spring 生态概念；Python 侧对应检查是「配置热加载是否生效」与「Pydantic/Django Form 校验是否覆盖设计 A.3 约束」，判据同 `dimension-4-5-quality-debt.md` 维度 4 对应行。
- 前端专有项见 `stack-vue.md` / `stack-react.md`。
