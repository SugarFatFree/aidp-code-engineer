# Python 命令细则

> 探测命中 `requirements.txt`/`pyproject.toml` + `*.py` 时加载。跨技术栈通用规则见 `../SKILL.md`。

## 一、脚手架生成

```bash
django-admin startproject <name>         # Django
fastapi dev main.py                      # FastAPI 本地起服务（非验证用）
```

## 二、开发期轻量验证（⚠️ Task 验收标准写这个）

```bash
python -m compileall -q <包目录>          # ✅ 语法检查（最轻）
mypy <包目录> --ignore-missing-imports    # ✅ 类型检查（项目已配 mypy 时优先）
ruff check <包目录>                       # ✅ 静态检查，秒级
```

> Python 无「构建」概念，但**禁止**把 `docker build` / 打 wheel 包写进开发期 Task 验收标准。

## 三、单元测试

```bash
pytest tests/test_order_service.py -k "insufficient_balance"
pytest --cov=app                          # Phase 5 覆盖率
```

## 四、依赖安装

```bash
pip install -r requirements.txt
# 或 poetry install / uv sync
```

## 五、本栈 Task 拆分要点

- **依赖清单同步 Task**：新增依赖须同步写进 `requirements.txt`/`pyproject.toml` 作为验收标准（注意 import 名 ≠ 包名：`yaml`→`PyYAML`、`cv2`→`opencv-python`）。
- **枚举类 Task**：详细设计 A.4 每个字典/枚举要有 `enum.Enum` 定义 + ORM 映射（SQLAlchemy `TypeDecorator` / Django `choices`）。
