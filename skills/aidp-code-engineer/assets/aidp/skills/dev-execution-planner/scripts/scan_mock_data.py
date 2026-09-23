#!/usr/bin/env python3
"""
Mock 数据残留扫描脚本

用法:
  python scan_mock_data.py [代码目录] [--json] [--strict] [--third-party-mode]

扫描代码中的 mock 数据残留,包括:
  1. 硬编码假数据 (mockData, fakeData, demoData 等)
  2. mock 目录 (mock/, mocks/, __mocks__/)
  3. mock 文件 (*mock*, *fake*)
  4. API 层假数据函数
  5. mock 工具引用 (Mock.js, MSW, json-server)
  6. TODO/FIXME 注释标记
  7. mock 兜底逻辑 (catch 块回退假数据)

第三方临时 mock 模式 (--third-party-mode):
  对照 SKILL.md「情况 0:第三方平台接口未交付」的 THIRD_PARTY_MOCK 协议,识别带 THIRD_PARTY_MOCK 标注的代码:
  - 标注合规且无真实 client 引用 → 合规但 Important (待对接)
  - 标注块缺必填字段 → Critical (协议违规)
  - 真实 client 已出现 (vendor SDK / base URL / 凭证 / new XxxClient) → Critical (并存,必须删除)
  - mock 在 catch / fallback 路径中调用 → Critical (mock 兜底)
  - expected_ready 已过期超过 14 天 → Critical (长期挂账)
  启用此模式后,带正确 THIRD_PARTY_MOCK 标注的 mock 文件/函数不再触发普通 mock 零容忍规则
  (但前提是无真实 client 引用且标注完整)。

参数:
  代码目录             默认为 src/
  --json              输出 JSON 格式结果
  --strict            严格模式,任何发现都返回非零退出码
  --third-party-mode  启用第三方临时 mock 协议核验

跨平台支持: Linux / macOS / Windows (Python 3.6+)
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# 前端文件扩展名
FRONTEND_EXTENSIONS = {'.vue', '.ts', '.js', '.tsx', '.jsx', '.svelte'}

# 第三方 mock 模式下额外覆盖的后端语言
BACKEND_EXTENSIONS = {'.java', '.kt', '.py', '.go', '.cs', '.rb', '.php'}

# 排除的目录(测试目录、构建产物、依赖目录)
EXCLUDE_DIRS = {
    'node_modules', '.git', 'dist', 'build', '.nuxt', '.next', '__pycache__',
    'target', 'out', '.idea', '.vscode', 'venv', '.venv', 'vendor',
    # 测试目录:测试合法使用 mock 工具,不应触发零容忍
    # 注意:不排除 __mocks__,它由 check_mock_dirs 单独检测(Jest 习惯放 src/)
    '__tests__', '__test__', 'tests', 'test',
}

# 测试文件名模式(.test./.spec./.e2e. 中缀的文件中合法使用 mock,豁免)
TEST_FILE_PATTERNS = [
    re.compile(r'\.test\.(ts|tsx|js|jsx|vue)$', re.IGNORECASE),
    re.compile(r'\.spec\.(ts|tsx|js|jsx|vue)$', re.IGNORECASE),
    re.compile(r'\.e2e\.(ts|tsx|js|jsx|vue)$', re.IGNORECASE),
    re.compile(r'\.test\.(java|py|go|kt|rb|php|cs)$', re.IGNORECASE),
    re.compile(r'_test\.(go|py)$', re.IGNORECASE),  # Go: xxx_test.go;Python: test_xxx.py
    re.compile(r'^test_.*\.py$', re.IGNORECASE),
    # Java: src/test/java/...(目录已经豁免,这里再补 Test 后缀类)
    re.compile(r'Test\.(java|kt)$'),
    re.compile(r'IT\.(java|kt)$'),  # 集成测试 *IT.java
]


def is_test_file(path: Path) -> bool:
    """判断是否为测试文件(应豁免 mock 检查)"""
    name = path.name
    for pattern in TEST_FILE_PATTERNS:
        if pattern.search(name):
            return True
    return False

# THIRD_PARTY_MOCK 协议必填字段(对照各 SKILL 中的协议规范)
THIRD_PARTY_REQUIRED_FIELDS = ['vendor', 'api', 'since', 'expected_ready', 'owner', 'REMOVE_WHEN']

# 默认过期容忍天数(可通过 --max-overdue-days 调整)
DEFAULT_MAX_OVERDUE_DAYS = 14

# 真实 vendor 客户端识别信号(任一命中视为已开始对接)
REAL_CLIENT_SIGNALS = [
    # 主流第三方 SDK 包/类
    (r"\bcom\.alipay\.api\.", "Alipay SDK 类引用"),
    (r"\bcom\.github\.binarywang\.wxpay\b", "WxPay SDK 引用"),
    (r"\bcom\.tencent\.wxcloud\b", "Wechat Cloud SDK 引用"),
    (r"\bcom\.unionpay\b", "UnionPay SDK 引用"),
    (r"@alipay/sdk", "Alipay JS SDK 引用"),
    (r"@wechat/sdk", "Wechat JS SDK 引用"),
    # 通用 vendor SDK 模式
    (r"new\s+(\w*Client)\s*\(\s*['\"]https?://[^'\"]+['\"]", "新建真实 HTTP Client (含真实 URL)"),
    (r"new\s+(Alipay|WxPay|Unionpay|Customs|Idp)\w*Client\s*\(", "新建真实 vendor Client"),
    # 真实 base URL(显式包含真实域名,排除 mock/test/example.com)
    (r"https?://(?!.*(mock|fake|example\.com|localhost|127\.0\.0\.1))[\w.-]*\.(alipay|weixin|qq|unionpay|tencentcloudapi|aliyuncs|aliapi|customs\.gov|aliexpress)\.com", "真实第三方 vendor 域名"),
]

# 真实凭证配置识别(配置文件中 ID/Key 被实际填值)
# 注:仅匹配扁平点号键(.properties 或扁平 YAML,如 `alipay.app.id=xxx`);
# 嵌套 YAML(`alipay:` → `  app:` → `    id:`)不命中 —— 后端凭证残留以人工 grep 为准(协议文档已声明)
REAL_CREDENTIAL_PATTERNS = [
    (r"alipay\.app\.id\s*[:=]\s*['\"]?(?!MOCK|TODO|YOUR_|XXXX|<|\$\{)\S+", "alipay.app.id 已配置真实值"),
    (r"alipay\.private\.key\s*[:=]\s*['\"]?(?!MOCK|TODO|YOUR_|XXXX|<|\$\{)\S+", "alipay.private.key 已配置真实值"),
    (r"wechat\.app\.id\s*[:=]\s*['\"]?(?!MOCK|TODO|YOUR_|XXXX|<|\$\{)\S+", "wechat.app.id 已配置真实值"),
    (r"unionpay\.merchant\.id\s*[:=]\s*['\"]?(?!MOCK|TODO|YOUR_|XXXX|<|\$\{)\S+", "unionpay.merchant.id 已配置真实值"),
]


def walk_files(root: Path, extensions=None, include_test_files=False):
    """递归遍历目录(或单个文件),跳过排除目录和测试文件"""
    # 支持直接传入单个文件路径(如 src/api/workOrder.ts)
    if root.is_file():
        if extensions is None or root.suffix in extensions:
            if include_test_files or not is_test_file(root):
                yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            fp = Path(dirpath) / f
            if extensions is None or fp.suffix in extensions:
                if not include_test_files and is_test_file(fp):
                    continue
                yield fp


def scan_file_content(filepath: Path, patterns: list) -> list:
    """扫描文件内容，返回匹配行"""
    hits = []
    try:
        text = filepath.read_text(encoding='utf-8', errors='ignore')
    except (OSError, PermissionError):
        return hits
    for i, line in enumerate(text.splitlines(), 1):
        for pattern, desc in patterns:
            if re.search(pattern, line):
                hits.append({
                    "file": str(filepath),
                    "line": i,
                    "content": line.strip()[:200],
                    "rule": desc
                })
    return hits


def check_hardcoded_data(root: Path) -> list:
    """检查项 1: 硬编码假数据"""
    patterns = [
        (r'\b(mockData|fakeData|mockList|fakeList|demoData|testData|sampleData|mockTableData|mockUserList)\b',
         "硬编码假数据变量"),
        (r'\bconst\s+\w*(mock|fake|demo|sample)\w*\s*=\s*\[', "硬编码假数据数组"),
    ]
    hits = []
    for fp in walk_files(root, FRONTEND_EXTENSIONS):
        hits.extend(scan_file_content(fp, patterns))
    return hits


def check_mock_dirs(root: Path) -> list:
    """检查项 2: mock 目录"""
    mock_dir_names = {'mock', 'mocks', '__mocks__', 'fake', 'fakes'}
    hits = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for d in dirnames:
            if d.lower() in mock_dir_names:
                hits.append({
                    "file": str(Path(dirpath) / d),
                    "line": 0,
                    "content": f"mock 目录: {d}/",
                    "rule": "mock 目录存在"
                })
    return hits


def check_mock_files(root: Path) -> list:
    """检查项 3: mock 文件"""
    hits = []
    for fp in walk_files(root):
        name_lower = fp.stem.lower()
        if ('mock' in name_lower or 'fake' in name_lower):
            # 排除测试文件
            if '.test.' in fp.name or '.spec.' in fp.name:
                continue
            if fp.suffix in FRONTEND_EXTENSIONS or fp.suffix == '.json':
                hits.append({
                    "file": str(fp),
                    "line": 0,
                    "content": f"mock 文件: {fp.name}",
                    "rule": "mock 文件存在"
                })
    return hits


def check_fake_api_functions(root: Path) -> list:
    """检查项 4: API 层假数据函数"""
    api_dirs = ['api', 'services', 'service', 'request']
    patterns = [
        (r'Promise\.resolve\s*\(.*\[', "API 层返回假数据 (Promise.resolve)"),
        (r'return\s+\{[^}]*data\s*:', "API 层返回硬编码对象"),
        (r'return\s+\[', "API 层返回硬编码数组"),
    ]
    hits = []
    for api_dir_name in api_dirs:
        api_dir = root / api_dir_name
        if api_dir.is_dir():
            for fp in walk_files(api_dir, FRONTEND_EXTENSIONS):
                # 排除测试文件
                if '.test.' in fp.name or '.spec.' in fp.name:
                    continue
                hits.extend(scan_file_content(fp, patterns))
    return hits


def check_mock_tools(root: Path) -> list:
    """检查项 5: mock 工具引用"""
    patterns = [
        (r'\bMock\.mock\b', "Mock.js 调用"),
        (r'\b(setupWorker|setupServer)\b', "MSW 工具调用"),
        (r'\bjson-server\b', "json-server 引用"),
        (r'\b(mockjs|better-mock)\b', "mock 工具库引用"),
    ]
    hits = []
    for fp in walk_files(root, FRONTEND_EXTENSIONS):
        hits.extend(scan_file_content(fp, patterns))

    # 检查 package.json
    pkg_json = root.parent / 'package.json' if root.name == 'src' else root / 'package.json'
    if not pkg_json.exists():
        pkg_json = root / 'package.json'
    if pkg_json.exists():
        pkg_patterns = [
            (r'"(mockjs|better-mock|json-server|msw|miragejs)"', "package.json 中的 mock 依赖"),
        ]
        hits.extend(scan_file_content(pkg_json, pkg_patterns))
    return hits


def check_todo_fixme(root: Path) -> list:
    """检查项 6: TODO/FIXME 注释"""
    patterns = [
        (r'(?i)(TODO|FIXME|HACK).*?(接口|mock|真实|fake|临时|替换)', "TODO/FIXME 标记"),
    ]
    hits = []
    for fp in walk_files(root, FRONTEND_EXTENSIONS):
        hits.extend(scan_file_content(fp, patterns))
    return hits


def check_mock_fallback(root: Path) -> list:
    """检查项 7: mock 兜底逻辑"""
    patterns = [
        (r'\.catch\s*\([^)]*\)\s*=>\s*\[', "catch 块回退到数组"),
        (r'catch\s*\([^)]*\)\s*\{[^}]*=\s*\[', "catch 块赋值数组"),
        (r'\|\|\s*\[\s*\{', "|| 运算符后接对象数组 (疑似 mock 兜底)"),
    ]
    hits = []
    for fp in walk_files(root, FRONTEND_EXTENSIONS):
        hits.extend(scan_file_content(fp, patterns))
    return hits


# ---------------------------------------------------------------------------
# 第三方临时 mock 协议核验 (THIRD_PARTY_MOCK)
# 对照 SKILL.md「情况 0」THIRD_PARTY_MOCK 协议
# ---------------------------------------------------------------------------

THIRD_PARTY_MARKER = re.compile(r'THIRD_PARTY_MOCK\s*[:：]\s*(.*)')
FIELD_LINE = re.compile(
    r'^\s*[#/*\s]*(' + '|'.join(THIRD_PARTY_REQUIRED_FIELDS) + r')\s*[:：]\s*(.+?)\s*$'
)
DATE_PATTERN = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def find_third_party_mock_blocks(filepath: Path, max_overdue_days: int = DEFAULT_MAX_OVERDUE_DAYS):
    """识别文件中所有 THIRD_PARTY_MOCK 标注块,返回每块的元数据。

    返回:
      [{ "file": str, "line": int, "summary": str, "fields": {field: value},
         "missing": [field], "expired": bool, "expected_ready": str|None }]
    """
    try:
        text = filepath.read_text(encoding='utf-8', errors='ignore')
    except (OSError, PermissionError):
        return []
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = THIRD_PARTY_MARKER.search(line)
        if not m:
            i += 1
            continue
        # 在标注首行后向下扫描最多 12 行,提取必填字段;遇到下一个标注块 marker 即停止,避免吞掉相邻块
        fields = {}
        last_j = i
        for j in range(i + 1, min(i + 13, len(lines))):
            if THIRD_PARTY_MARKER.search(lines[j]):
                break
            fm = FIELD_LINE.match(lines[j])
            if fm:
                fields[fm.group(1)] = fm.group(2).strip()
                last_j = j
        missing = [f for f in THIRD_PARTY_REQUIRED_FIELDS if f not in fields]
        expected_ready = fields.get('expected_ready')
        expired = False
        if expected_ready and expected_ready.upper() != 'UNKNOWN':
            dm = DATE_PATTERN.match(expected_ready)
            if dm:
                try:
                    target = datetime.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
                    today = datetime.date.today()
                    if (today - target).days > max_overdue_days:
                        expired = True
                except ValueError:
                    pass
        blocks.append({
            "file": str(filepath),
            "line": i + 1,
            "summary": m.group(1).strip()[:200],
            "fields": fields,
            "missing": missing,
            "expected_ready": expected_ready,
            "expired": expired,
        })
        i = last_j + 1  # 前进到本块最后字段行的下一行,而非固定 +13(否则跳过相邻块)
    return blocks


def find_real_client_signals(root: Path):
    """搜索整个代码仓中是否出现真实 vendor client / SDK / 凭证。"""
    signals = []
    extensions = FRONTEND_EXTENSIONS | BACKEND_EXTENSIONS
    for fp in walk_files(root, extensions):
        signals.extend(scan_file_content(fp, REAL_CLIENT_SIGNALS))
    # 凭证配置(单独看 .yml / .yaml / .properties / .env / .env.* / application*.yml)
    config_names = re.compile(r'(application.*\.(yml|yaml|properties)|\.env(\..*)?|config.*\.(yml|yaml|properties))$',
                              re.IGNORECASE)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if config_names.search(f):
                fp = Path(dirpath) / f
                signals.extend(scan_file_content(fp, REAL_CREDENTIAL_PATTERNS))
    return signals


def detect_mock_in_fallback_path(filepath: Path, mock_block_line: int) -> bool:
    """判定 mock 函数/常量是否在 catch / fallback 路径中被调用。

    简化策略:在 mock 标注块前后 50 行内搜索引用其名,且引用行位于 catch / `||` 路径中。
    若 mock 被任何 catch/`||` 行引用 → True。
    """
    try:
        text = filepath.read_text(encoding='utf-8', errors='ignore')
    except (OSError, PermissionError):
        return False
    lines = text.splitlines()
    # 提取 mock 函数/常量名:扫标注块下方紧邻的声明行
    name = None
    name_pattern = re.compile(
        r'(?:function|const|let|var|export\s+(?:async\s+)?function|public\s+\w+\s+|def|class)\s+(\w+)'
    )
    for j in range(mock_block_line, min(mock_block_line + 15, len(lines))):
        nm = name_pattern.search(lines[j])
        if nm:
            name = nm.group(1)
            break
    if not name:
        return False
    fallback_pattern = re.compile(
        r'(catch\s*\([^)]*\)|catch\s*\{|\|\|\s*' + re.escape(name) + r'|\.catch\s*\()'
    )
    name_call = re.compile(r'\b' + re.escape(name) + r'\s*\(')
    for line in lines:
        if name_call.search(line) and fallback_pattern.search(line):
            return True
    return False


def check_third_party_mock(root: Path, max_overdue_days: int = DEFAULT_MAX_OVERDUE_DAYS) -> dict:
    """第三方临时 mock 协议核验,返回结构化结果。"""
    extensions = FRONTEND_EXTENSIONS | BACKEND_EXTENSIONS
    all_blocks = []
    for fp in walk_files(root, extensions):
        all_blocks.extend(find_third_party_mock_blocks(fp, max_overdue_days))

    real_client_hits = find_real_client_signals(root) if all_blocks else []
    coexist = bool(real_client_hits)  # 全仓任一真实 client 信号存在即视为"已开始对接"

    issues = []
    compliant_pending = []
    for blk in all_blocks:
        # 1. 必填字段完整性
        if blk["missing"]:
            issues.append({
                **blk,
                "severity": "Critical",
                "rule": "THIRD_PARTY_MOCK 标注块必填字段缺失",
                "hint": f"缺失字段: {', '.join(blk['missing'])} (协议详见所属 SKILL 的 THIRD_PARTY_MOCK 标注协议章节)",
            })
            continue
        # 2. 与真实 client 并存(整仓信号,优先级最高)
        if coexist:
            issues.append({
                **blk,
                "severity": "Critical",
                "rule": "THIRD_PARTY_MOCK 与真实 vendor client 并存",
                "hint": f"代码仓已出现真实 vendor client/SDK/凭证 ({len(real_client_hits)} 处),mock 必须立即删除",
            })
            continue
        # 3. 过期未删除
        if blk["expired"]:
            issues.append({
                **blk,
                "severity": "Critical",
                "rule": f"THIRD_PARTY_MOCK 已过期 {max_overdue_days} 天以上",
                "hint": f"expected_ready={blk['expected_ready']} 已过期,催第三方或转 Module E 暂行方案",
            })
            continue
        # 4. mock 兜底路径
        fpath = Path(blk["file"])
        if detect_mock_in_fallback_path(fpath, blk["line"] - 1):
            issues.append({
                **blk,
                "severity": "Critical",
                "rule": "THIRD_PARTY_MOCK 被用作 catch/fallback 兜底",
                "hint": "禁止在 catch / `||` / fallback 中调用 mock,任何场景禁止 mock 兜底",
            })
            continue
        # 合规但 Important(待 follow-up)
        compliant_pending.append({
            **blk,
            "severity": "Important",
            "rule": "THIRD_PARTY_MOCK 待 follow-up",
            "hint": f"vendor={blk['fields'].get('vendor')} api={blk['fields'].get('api')} expected_ready={blk['expected_ready']},合规但下次 Review 必查",
        })

    return {
        "blocks_found": len(all_blocks),
        "real_client_signals": real_client_hits,
        "coexist_with_real": coexist,
        "violations": issues,
        "compliant_pending": compliant_pending,
    }


CHECKS = [
    ("硬编码假数据", check_hardcoded_data, "Critical"),
    ("mock 目录", check_mock_dirs, "Critical"),
    ("mock 文件", check_mock_files, "Critical"),
    ("API 层假数据函数", check_fake_api_functions, "Critical"),
    ("mock 工具引用", check_mock_tools, "Critical"),
    ("TODO/FIXME 注释", check_todo_fixme, "Important"),
    ("mock 兜底逻辑", check_mock_fallback, "Critical"),
]


def _merge_third_party(results):
    """合并多个扫描根的第三方 mock 核验结果。"""
    merged = {
        "blocks_found": 0,
        "real_client_signals": [],
        "coexist_with_real": False,
        "violations": [],
        "compliant_pending": [],
    }
    for r in results:
        merged["blocks_found"] += r["blocks_found"]
        merged["real_client_signals"].extend(r["real_client_signals"])
        merged["coexist_with_real"] = merged["coexist_with_real"] or r["coexist_with_real"]
        merged["violations"].extend(r["violations"])
        merged["compliant_pending"].extend(r["compliant_pending"])
    return merged


def run_scan(scan_dirs, output_json=False, strict=False, third_party_mode=False,
             max_overdue_days=DEFAULT_MAX_OVERDUE_DAYS):
    """执行全部扫描(scan_dirs 为一个或多个目录/文件路径)"""
    if isinstance(scan_dirs, (str, Path)):
        scan_dirs = [scan_dirs]
    scan_dirs = [Path(d) for d in scan_dirs]
    results = []
    total_issues = 0
    third_party_result = None

    # 第三方 mock 模式:先识别 THIRD_PARTY_MOCK 标注块
    if third_party_mode:
        third_party_result = _merge_third_party(
            [check_third_party_mock(d, max_overdue_days) for d in scan_dirs]
        )
        # 把第三方 mock 违规计入 total_issues
        total_issues += len(third_party_result["violations"])
        # 合规但待 follow-up 的也计入(Important)
        total_issues += len(third_party_result["compliant_pending"])

    # 普通 mock 零容忍检查
    for name, check_fn, severity in CHECKS:
        hits = []
        for d in scan_dirs:
            hits.extend(check_fn(d))
        results.append({
            "check": name,
            "severity": severity,
            "issues": hits,
            "count": len(hits),
            "passed": len(hits) == 0
        })
        total_issues += len(hits)

    if output_json:
        output = {
            "scan_dir": ", ".join(str(d) for d in scan_dirs),
            "third_party_mode": third_party_mode,
            "total_issues": total_issues,
            "passed": total_issues == 0,
            "checks": results
        }
        if third_party_mode and third_party_result:
            output["third_party_mock"] = third_party_result
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("Mock 数据残留扫描" + (" (第三方临时 mock 模式)" if third_party_mode else ""))
        print("=" * 72)
        print(f"扫描目录: {', '.join(str(d) for d in scan_dirs)}")
        print()

        # 第三方 mock 报告(优先显示)
        if third_party_mode and third_party_result:
            print("【第三方临时 mock 协议核验】")
            print(f"  识别 THIRD_PARTY_MOCK 标注块: {third_party_result['blocks_found']} 个")
            print(f"  真实 vendor client 信号: {len(third_party_result['real_client_signals'])} 处")
            if third_party_result["coexist_with_real"]:
                print("  ⚠️  已检测到真实 vendor client/SDK/凭证,所有 mock 必须删除")
            print()

            if third_party_result["violations"]:
                print(f"  🔴 Critical 违规: {len(third_party_result['violations'])} 处")
                for v in third_party_result["violations"][:5]:
                    print(f"    - {v['file']}:{v['line']}")
                    print(f"      {v['rule']}: {v['hint']}")
                if len(third_party_result["violations"]) > 5:
                    print(f"    ... 还有 {len(third_party_result['violations']) - 5} 处")
                print()

            if third_party_result["compliant_pending"]:
                print(f"  🟡 合规但待 follow-up: {len(third_party_result['compliant_pending'])} 处")
                for p in third_party_result["compliant_pending"][:3]:
                    print(f"    - {p['file']}:{p['line']}")
                    print(f"      vendor={p['fields'].get('vendor')} api={p['fields'].get('api')} expected_ready={p['expected_ready']}")
                if len(third_party_result["compliant_pending"]) > 3:
                    print(f"    ... 还有 {len(third_party_result['compliant_pending']) - 3} 处")
                print()

        # 普通 mock 零容忍检查结果
        for i, r in enumerate(results, 1):
            status = "✅" if r["passed"] else "❌"
            severity_icon = "🔴" if r["severity"] == "Critical" else "🟡"
            print(f"【检查项 {i}】{r['check']} {severity_icon} {r['severity']}")

            if r["passed"]:
                print(f"  {status} 无问题")
            else:
                print(f"  {status} 发现 {r['count']} 处问题:")
                for hit in r["issues"][:10]:
                    loc = f"{hit['file']}:{hit['line']}" if hit.get('line') else hit['file']
                    print(f"    - {loc}")
                    if 'content' in hit:
                        print(f"      {hit['content'][:120]}")
                if r["count"] > 10:
                    print(f"    ... 还有 {r['count'] - 10} 处")
            print()

        print("=" * 72)
        if total_issues == 0:
            print("✅ 未发现 mock 数据残留")
        else:
            critical = sum(r["count"] for r in results if r["severity"] == "Critical" and not r["passed"])
            if third_party_mode and third_party_result:
                critical += len(third_party_result["violations"])
            important = sum(r["count"] for r in results if r["severity"] == "Important" and not r["passed"])
            if third_party_mode and third_party_result:
                important += len(third_party_result["compliant_pending"])
            print(f"❌ 发现 {total_issues} 处问题 (Critical: {critical}, Important: {important})")
        print("=" * 72)

    if strict:
        sys.exit(1 if total_issues > 0 else 0)
    else:
        critical_count = sum(r["count"] for r in results if r["severity"] == "Critical")
        if third_party_mode and third_party_result:
            critical_count += len(third_party_result["violations"])
        sys.exit(1 if critical_count > 0 else 0)


def main():
    parser = argparse.ArgumentParser(
        description="Mock 数据残留扫描脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scan_mock_data.py src/
  python scan_mock_data.py src/views/work-order src/api/workOrder.ts
  python scan_mock_data.py src/ --json
  python scan_mock_data.py src/ --strict
  python scan_mock_data.py src/ --third-party-mode
  python scan_mock_data.py src/ --third-party-mode --json
        """
    )
    parser.add_argument('scan_dir', nargs='*', default=['src/'],
                        help='一个或多个代码目录/文件 (默认: src/)')
    parser.add_argument('--json', action='store_true',
                        help='输出 JSON 格式结果')
    parser.add_argument('--strict', action='store_true',
                        help='严格模式,任何发现都返回非零退出码')
    parser.add_argument('--third-party-mode', action='store_true',
                        help='启用第三方临时 mock 协议核验 (THIRD_PARTY_MOCK 标注协议)')
    parser.add_argument('--max-overdue-days', type=int, default=DEFAULT_MAX_OVERDUE_DAYS,
                        help=f'第三方 mock 过期容忍天数 (默认 {DEFAULT_MAX_OVERDUE_DAYS} 天,超过则升 Critical)')

    args = parser.parse_args()
    raw_paths = args.scan_dir if args.scan_dir else ['src/']
    scan_dirs = [Path(p) for p in raw_paths]

    missing = [str(p) for p in scan_dirs if not p.exists()]
    if missing:
        msg = f"错误: 路径不存在 - {', '.join(missing)}"
        if args.json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        else:
            print(msg)
        sys.exit(2)  # 入参错(路径不存在),非产物违规

    run_scan(scan_dirs, output_json=args.json, strict=args.strict,
             third_party_mode=args.third_party_mode,
             max_overdue_days=args.max_overdue_days)


if __name__ == "__main__":
    main()
