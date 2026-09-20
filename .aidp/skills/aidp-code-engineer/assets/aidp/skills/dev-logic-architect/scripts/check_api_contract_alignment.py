#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_api_contract_alignment.py — 接口字段级契约对齐核验

对照 dev-logic-architect SKILL 核心原则 18「代码事实采集深度铁律」
与质量检查清单检查项 25 字段级契约核对,验证标"✅ 沿用"的接口:
  1. 后端真实出参字段集合 ⊇ 前端消费字段集合
  2. B.2 接口契约字段说明以"已部署后端真实出参"为唯一信源
  3. 严禁直接抄原型代码的字段消费当成接口契约

用法:
    python check_api_contract_alignment.py <设计文档> <PRD文档> <后端base-url> [--auth-token <token>] [--prototype-dir <原型目录>] [--json]

仅依赖 Python 3.6+ 标准库。
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

# ============================================================
# 接口提取
# ============================================================

# B.2 接口定义 pattern
API_DEFINITION_PATTERN = re.compile(
    r"###\s+(?:B\.2\.\d+\s+)?(?P<method>GET|POST|PUT|DELETE|PATCH)\s+(?P<path>/[^\s\n]+)",
    re.IGNORECASE
)

# 接口标注状态 pattern (✅ 沿用 / 🔧 待实现 / 🆕 新增)
API_STATUS_PATTERN = re.compile(r"[✅🔧🆕]\s*(沿用|待实现|新增)", re.UNICODE)

# ============================================================
# 字段提取
# ============================================================

# PRD 字段规格表字段名提取
FIELD_SPEC_TABLE_PATTERN = re.compile(
    r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(\w+)\s*\|",
    re.MULTILINE
)

# 原型 HTML data binding pattern
HTML_DATA_BIND_PATTERNS = [
    re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}"),  # {{field}} / {{data.field}}
    re.compile(r"data-bind=['\"]([^'\"]+)['\"]"),  # data-bind="field"
    re.compile(r"v-model=['\"]([^'\"]+)['\"]"),  # v-model="field"
    re.compile(r"\{([a-zA-Z_][\w.]*)\}"),  # React {data.field}
]

# 原型 JS 字段消费 pattern
JS_FIELD_ACCESS_PATTERNS = [
    re.compile(r"response\.data\.([a-zA-Z_][\w.]*)"),  # response.data.field
    re.compile(r"data\.([a-zA-Z_][\w.]*)"),  # data.field
    re.compile(r"\.([a-zA-Z_]\w+)\s*[;,\)\]]"),  # general property access
]

# ============================================================
# JSON 字段路径提取
# ============================================================

def extract_json_field_paths(obj: Any, prefix: str = "") -> Set[str]:
    """
    递归提取 JSON 对象的所有字段路径。
    返回: {'field1', 'field2.subfield', 'field3[0].item', ...}
    """
    paths = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{prefix}.{key}" if prefix else key
            paths.add(current_path)
            paths.update(extract_json_field_paths(value, current_path))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            current_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            paths.update(extract_json_field_paths(item, current_path))
    return paths


def normalize_field_path(path: str) -> str:
    """
    规范化字段路径:去除数组索引(userStats[0].count → userStats.count)
    """
    return re.sub(r'\[\d+\]', '', path).strip('.')


# ============================================================
# 接口调用
# ============================================================

def call_api(base_url: str, method: str, path: str, auth_token: Optional[str] = None) -> Optional[Dict]:
    """
    使用 curl 调用接口,返回 JSON 响应。
    返回: {"data": {...}, "code": 200} 或 None(调用失败)
    """
    url = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    cmd = ["curl", "-X", method.upper(), url, "-s", "-w", "\n%{http_code}"]

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    for key, value in headers.items():
        cmd.extend(["-H", f"{key}: {value}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            return None

        http_code = lines[-1]
        body = '\n'.join(lines[:-1])

        if not http_code.isdigit() or int(http_code) >= 400:
            return None

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None
    except (subprocess.TimeoutExpired, Exception):
        return None


# ============================================================
# 设计文档解析
# ============================================================

def extract_reuse_apis(design_content: str) -> List[Dict]:
    """
    提取设计文档 B.2 中标注"✅ 沿用"的接口。
    返回: [{"method": "GET", "path": "/api/users", "section": "B.2.1 ...", "line": 123}, ...]
    """
    apis = []
    lines = design_content.split('\n')

    for i, line in enumerate(lines, 1):
        api_match = API_DEFINITION_PATTERN.search(line)
        if not api_match:
            continue

        method = api_match.group("method").upper()
        path = api_match.group("path")

        # 检查标题行本身 + 接下来 10 行内是否有"✅ 沿用"标注
        # (标注常写在同一标题行,如 "### GET /xxx ✅ 沿用已有",故从 i-1 起始)
        context_lines = lines[i-1:min(i+10, len(lines))]
        context = '\n'.join(context_lines)

        if API_STATUS_PATTERN.search(context) and "✅" in context and "沿用" in context:
            apis.append({
                "method": method,
                "path": path,
                "section": line.strip(),
                "line": i,
            })

    return apis


def extract_api_field_spec(design_content: str, api_path: str) -> Set[str]:
    """
    提取设计文档 B.2 接口定义中的字段说明(响应字段列表)。
    简化版:匹配"响应字段"/"出参"章节后的字段名。
    返回: {'field1', 'field2', ...}
    """
    fields = set()
    lines = design_content.split('\n')

    # 找到接口定义位置
    api_section_start = -1
    for i, line in enumerate(lines):
        if api_path in line:
            api_section_start = i
            break

    if api_section_start == -1:
        return fields

    # 扫描接下来 50 行,寻找"响应字段"/"出参"表格
    for i in range(api_section_start, min(api_section_start + 50, len(lines))):
        line = lines[i]
        if re.search(r"响应字段|出参|Response", line, re.IGNORECASE):
            # 扫描表格行
            for j in range(i+1, min(i+30, len(lines))):
                table_line = lines[j]
                if not table_line.strip().startswith('|'):
                    break
                # 提取第一列字段名(简化:取 | 之后第一个单词)
                match = re.search(r'\|\s*(\w+)\s*\|', table_line)
                if match:
                    field_name = match.group(1)
                    if field_name not in ['字段', '名称', 'Field', 'Name', '序号']:
                        fields.add(field_name)
            break

    return fields


# ============================================================
# PRD 前端消费字段提取
# ============================================================

def extract_frontend_fields_from_prd(prd_content: str) -> Set[str]:
    """
    从 PRD「六、字段规格表」提取前端消费字段(变量名列)。
    返回: {'count', 'userName', 'createdAt', ...}
    """
    fields = set()
    for match in FIELD_SPEC_TABLE_PATTERN.finditer(prd_content):
        variable_name = match.group(2).strip()
        if variable_name and variable_name not in ['变量名', 'name', 'Name']:
            fields.add(variable_name)
    return fields


def extract_frontend_fields_from_prototype(prototype_paths: List[Path]) -> Set[str]:
    """
    从原型 HTML / JS 文件提取前端消费字段。
    返回: {'userStats.totalCount', 'dashboardData.revenue', ...}
    """
    fields = set()
    for path in prototype_paths:
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")

            # HTML data binding
            for pattern in HTML_DATA_BIND_PATTERNS:
                for match in pattern.finditer(content):
                    field_path = match.group(1).strip()
                    if field_path and not field_path.startswith('$'):
                        fields.add(field_path)

            # JS field access
            if path.suffix in ['.js', '.ts', '.jsx', '.tsx']:
                for pattern in JS_FIELD_ACCESS_PATTERNS:
                    for match in pattern.finditer(content):
                        field_path = match.group(1).strip()
                        if field_path:
                            fields.add(field_path)
        except Exception:
            continue

    return fields


# ============================================================
# 契约对齐核验
# ============================================================

def check_contract_alignment(
    api: Dict,
    backend_response: Dict,
    frontend_fields: Set[str],
    design_fields: Set[str]
) -> Dict:
    """
    核验单个接口的字段级契约对齐。
    返回: {
        "api": {...},
        "backend_fields": [...],
        "frontend_fields": [...],
        "design_fields": [...],
        "missing_fields": [...],  # 前端要但后端无
        "extra_design_fields": [...],  # 设计有但后端无(抄原型代码)
        "passed": bool,
    }
    """
    backend_fields = extract_json_field_paths(backend_response)
    backend_fields_normalized = {normalize_field_path(f) for f in backend_fields}

    # 前端消费字段规范化
    frontend_fields_normalized = {normalize_field_path(f) for f in frontend_fields}

    # 缺失字段(前端要但后端无)
    missing_fields = []
    for ff in frontend_fields_normalized:
        # 支持前缀匹配(如前端要 userStats.totalCount,后端有 userStats → 通过)
        if not any(bf.startswith(ff) or ff.startswith(bf) for bf in backend_fields_normalized):
            missing_fields.append(ff)

    # 设计文档字段 vs 后端真实字段(检测"抄原型代码")
    extra_design_fields = []
    for df in design_fields:
        if df not in backend_fields_normalized and df not in ['code', 'message', 'data', 'success']:
            extra_design_fields.append(df)

    return {
        "api": api,
        "backend_fields": sorted(backend_fields_normalized),
        "frontend_fields": sorted(frontend_fields_normalized),
        "design_fields": sorted(design_fields),
        "missing_fields": missing_fields,
        "extra_design_fields": extra_design_fields,
        "passed": len(missing_fields) == 0 and len(extra_design_fields) == 0,
    }


# ============================================================
# 主流程
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="接口字段级契约对齐核验(对应核心原则 18 + QR 检查项 25)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("design_doc", type=Path, help="详细设计文档")
    ap.add_argument("prd_doc", type=Path, help="PRD 需求文档")
    ap.add_argument("backend_base_url", type=str, help="后端 base URL(如 http://localhost:8080)")
    ap.add_argument("--auth-token", type=str, help="认证 token(可选)")
    ap.add_argument("--prototype-dir", type=Path, help="原型文件目录(可选,扫描 HTML/JS)")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if not args.design_doc.exists():
        print(f"❌ 设计文档不存在: {args.design_doc}", file=sys.stderr)
        return 2

    if not args.prd_doc.exists():
        print(f"❌ PRD 文档不存在: {args.prd_doc}", file=sys.stderr)
        return 2

    design_content = args.design_doc.read_text(encoding="utf-8", errors="replace")
    prd_content = args.prd_doc.read_text(encoding="utf-8", errors="replace")

    # 提取前端消费字段
    frontend_fields = extract_frontend_fields_from_prd(prd_content)
    if args.prototype_dir and args.prototype_dir.exists():
        prototype_files = list(args.prototype_dir.rglob("*.html")) + list(args.prototype_dir.rglob("*.js"))
        frontend_fields.update(extract_frontend_fields_from_prototype(prototype_files))

    # 提取标"✅ 沿用"的接口
    reuse_apis = extract_reuse_apis(design_content)

    results = []
    for api in reuse_apis:
        # 调用后端接口
        backend_response = call_api(
            args.backend_base_url,
            api["method"],
            api["path"],
            args.auth_token
        )

        if backend_response is None:
            results.append({
                "api": api,
                "error": "BACKEND_CALL_FAILED",
                "detail": "后端未部署 / 接口调用失败 / 返回非 JSON",
                "passed": False,
            })
            continue

        # 提取设计文档字段说明
        design_fields = extract_api_field_spec(design_content, api["path"])

        # 字段级契约对齐核验
        result = check_contract_alignment(api, backend_response, frontend_fields, design_fields)
        results.append(result)

    aggregated = {
        "design_doc": str(args.design_doc),
        "prd_doc": str(args.prd_doc),
        "backend_base_url": args.backend_base_url,
        "reuse_api_count": len(reuse_apis),
        "contract_gap_count": sum(1 for r in results if not r.get("passed", False)),
        "passed": all(r.get("passed", False) for r in results),
        "results": results,
    }

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        return 0 if aggregated["passed"] else 1

    # 文本输出
    print(f"📊 接口字段级契约对齐核验\n")
    print(f"设计文档: {args.design_doc}")
    print(f"PRD 文档: {args.prd_doc}")
    print(f"后端 URL: {args.backend_base_url}")
    print(f"标'✅ 沿用'接口: {aggregated['reuse_api_count']} 个")
    print(f"契约缺口: {aggregated['contract_gap_count']} 个\n")

    if aggregated["passed"]:
        print("✅ 所有接口字段级契约对齐,通过核验")
        return 0

    print(f"❌ 发现 {aggregated['contract_gap_count']} 个契约缺口:\n")
    for r in results:
        if r.get("passed", False):
            continue

        if "error" in r:
            print(f"📄 {r['api']['method']} {r['api']['path']} (L{r['api']['line']})")
            print(f"  ❌ {r['error']}: {r['detail']}")
            print(f"  处置方案: 后端部署后重新核验,或改标'🔧 待实现'\n")
            continue

        print(f"📄 {r['api']['method']} {r['api']['path']} (L{r['api']['line']})")
        print(f"  后端出参字段: {len(r['backend_fields'])} 个")
        print(f"  前端消费字段: {len(r['frontend_fields'])} 个")
        print(f"  设计文档字段: {len(r['design_fields'])} 个")

        if r['missing_fields']:
            print(f"  ⚠️  前端要读但后端无的字段({len(r['missing_fields'])} 个):")
            for field in r['missing_fields'][:5]:
                print(f"    - {field}")
            if len(r['missing_fields']) > 5:
                print(f"    ... 还有 {len(r['missing_fields']) - 5} 个")

        if r['extra_design_fields']:
            print(f"  ⚠️  设计有但后端无的字段({len(r['extra_design_fields'])} 个,疑似抄原型代码):")
            for field in r['extra_design_fields'][:3]:
                print(f"    - {field}")

        print()

    print("📌 修复建议:")
    print("  1. 在 Module E 登记契约缺口条目(D-NNN),列出缺失字段清单 + 处置方案")
    print("  2. 后端补字段(推荐) / 前端改读其他字段 / 产品确认是否必须展示")
    print("  3. B.2 接口契约字段说明必须以'已部署后端真实出参'为唯一信源")
    print("  4. 严禁直接抄原型代码的字段消费(如 console.ts 里读 response.userStats)")
    print("  详见 dev-logic-architect SKILL 核心原则 18「代码事实采集深度铁律」")

    return 1


if __name__ == "__main__":
    sys.exit(main())
