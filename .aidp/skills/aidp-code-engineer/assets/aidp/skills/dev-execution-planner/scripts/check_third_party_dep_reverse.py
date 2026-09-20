#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第三方依赖反向兜底识别脚本

对应本 SKILL 检查项 9.8「反向兜底」/ SKILL.md「第一步半之二 反向兜底」
(概念源自 dev-logic-architect 核心原则 19「第三方依赖反向兜底识别」)。

实测发现: 设计期靠关键词扫 PRD("对接/调用第三方/外部平台")判定第三方依赖,
PRD 漏写时直接默判"无第三方依赖" → 编码计划"第三方对接:无" → 联调阶段才暴雷。

本脚本从代码 / 配置 / 依赖清单三向反推第三方依赖,与 PRD 正向识别求并集。

扫描维度:
  1. HTTP 客户端调用(代码层):
     - Java: RestTemplate / WebClient / OkHttpClient / @FeignClient / RestClient / @HttpExchange
     - .NET: HttpClient / IHttpClientFactory / Refit
     - Go: http.NewRequest / resty / httpx
     - Python: requests / httpx / aiohttp / urllib
     - Node: axios / fetch / undici / got
     - Kotlin: Ktor Client
  2. 配置项(配置层): application.yml / .env / appsettings.json 中的非本服务地址
  3. 依赖清单(依赖层): pom.xml / package.json / requirements.txt 中的 vendor SDK

使用:
  python check_third_party_dep_reverse.py <代码根目录>
  python check_third_party_dep_reverse.py <代码根目录> --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

# HTTP 客户端调用模式(代码层)
HTTP_CLIENT_PATTERNS = {
    "Java/RestTemplate": [
        r"\bRestTemplate\s*\(\s*\)",
        r"\.exchange\s*\(\s*[\"'](https?://[^\"']+)",
        r"\.getForObject\s*\(\s*[\"'](https?://[^\"']+)",
    ],
    "Java/WebClient": [
        r"WebClient\s*\.\s*builder\s*\(\)",
        r"WebClient\s*\.\s*create\s*\(",
    ],
    "Java/OkHttp": [
        r"OkHttpClient\s*(?:\.|\.Builder|\(\))",
    ],
    "Java/Feign": [
        r"@FeignClient\s*\(\s*(?:name\s*=\s*[\"'][^\"']+[\"']|url\s*=\s*[\"'][^\"']+[\"'])",
    ],
    "Python/requests": [
        r"\brequests\.(get|post|put|delete|patch)\s*\(\s*[\"']?(https?://[^\"',\s)]+)",
    ],
    "Python/httpx": [
        r"\bhttpx\.(AsyncClient|Client|get|post)\s*\(",
    ],
    "Python/aiohttp": [
        r"aiohttp\.ClientSession\s*\(",
    ],
    "Node/axios": [
        r"\baxios\.(create|get|post|put|delete)\s*\(",
    ],
    "Node/fetch": [
        r"\b(fetch|undici)\s*\(\s*[\"'](https?://[^\"']+)",
    ],
    "Go/net.http": [
        r"http\.(Get|Post|NewRequest)\s*\(\s*[\"']?(https?://[^\"',\s)]+)",
    ],
    "Go/resty": [
        r"resty\.(New|Client|R\(\))",
    ],
    ".NET/HttpClient": [
        r"new\s+HttpClient\s*\(",
        r"IHttpClientFactory",
        r"Refit\.RestService",
    ],
}

# Vendor SDK 关键词(依赖层)
VENDOR_SDK_KEYWORDS = {
    "支付/金融": ["alipay-sdk", "wechatpay-java", "stripe", "paypal", "unionpay"],
    "云厂商": ["aws-sdk", "google-cloud", "azure-sdk", "aliyun-sdk", "tencent-cloud", "huaweicloud"],
    "OAuth/统一认证": ["spring-security-oauth", "oauth2-client", "auth0", "okta-sdk", "passport"],
    "短信/邮件": ["twilio", "sendgrid", "aliyun-sms", "tencent-sms", "mailgun"],
    "对象存储": ["minio", "aws-s3", "oss-java-sdk", "qcloud-cos", "qiniu"],
    "推送/IM": ["jpush", "getui", "wechat-mp", "dingtalk-sdk", "feishu-sdk", "lark-sdk"],
    "海关/政务": ["customs-sdk", "ecq-sdk", "single-window"],
    "其他第三方": ["square-okhttp", "feign", "retrofit", "openfeign"],  # 偏向 HTTP 客户端,但也是第三方
}

# 配置文件中的"地址"键
CONFIG_URL_KEYS = [
    "base-url", "baseUrl", "base_url",
    "endpoint", "endpoints",
    "host", "server-url", "serverUrl",
    "api-url", "apiUrl", "api_url",
    "gateway", "callback-url",
]

# 本系统域名识别(自定义可扩展)
LOCALHOST_PATTERNS = [
    r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)",
    r"^https?://.*\.local\b",
    r"^https?://.*\.internal\b",
    r"^https?://.*\.svc\.cluster\.local",
]

# 跳过目录
SKIP_DIRS = {"node_modules", "target", "build", "dist", ".git", ".idea", "__pycache__", "venv", ".venv", "out"}

# 配置文件扩展名
CONFIG_EXTS = {".yml", ".yaml", ".json", ".env", ".properties", ".toml", ".conf"}

# 依赖清单文件名
DEPENDENCY_FILES = {"pom.xml", "build.gradle", "build.gradle.kts", "package.json", "requirements.txt", "Pipfile", "go.mod", "Cargo.toml", "*.csproj"}


def is_localhost_url(url: str) -> bool:
    """判断 URL 是否为本系统/本地址"""
    return any(re.match(p, url) for p in LOCALHOST_PATTERNS)


def scan_code_for_http_clients(root: Path) -> List[Dict]:
    """扫描代码中的 HTTP 客户端调用"""
    findings: List[Dict] = []
    code_exts = {".java", ".kt", ".ts", ".tsx", ".js", ".py", ".go", ".cs"}

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in code_exts:
            continue
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for client_type, patterns in HTTP_CLIENT_PATTERNS.items():
            for pat in patterns:
                for m in re.finditer(pat, content):
                    line_no = content[:m.start()].count("\n") + 1
                    snippet = m.group(0)[:100]
                    # 提取 URL(若 pattern 含 URL 捕获组)
                    url = m.group(2) if m.lastindex and m.lastindex >= 2 else None
                    is_external = (url and not is_localhost_url(url)) or url is None
                    findings.append({
                        "type": "http_client",
                        "client": client_type,
                        "file": str(path.relative_to(root)),
                        "line": line_no,
                        "snippet": snippet,
                        "url": url,
                        "is_external": is_external,
                    })
                    break  # 同 pattern 只记一次/方法
    return findings


def scan_config_for_external_urls(root: Path) -> List[Dict]:
    """扫描配置文件中的外部 URL"""
    findings: List[Dict] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.suffix.lower() not in CONFIG_EXTS and path.name not in {".env", ".env.example", ".env.local"}:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # 找包含 URL 的配置行
        for line_no, line in enumerate(content.splitlines(), start=1):
            line_lower = line.lower()
            if not any(key.lower() in line_lower for key in CONFIG_URL_KEYS):
                continue
            # 找 URL
            url_match = re.search(r"https?://[^\s\"',}{]+", line)
            if not url_match:
                continue
            url = url_match.group(0)
            if is_localhost_url(url):
                continue
            findings.append({
                "type": "config_url",
                "file": str(path.relative_to(root)),
                "line": line_no,
                "url": url,
                "snippet": line.strip()[:120],
                "is_external": True,
            })
    return findings


def scan_dependencies_for_vendors(root: Path) -> List[Dict]:
    """扫描依赖清单中的 vendor SDK"""
    findings: List[Dict] = []

    # 从 DEPENDENCY_FILES 常量派生扫描清单(此前该常量未被使用、且与硬编码列表不一致漏扫 Cargo.toml)
    dep_files: List[Path] = []
    for fname in sorted(DEPENDENCY_FILES):
        dep_files.extend(root.rglob(fname))  # 含字面名与 *.csproj 通配

    for path in dep_files:
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        content_lower = content.lower()
        for category, sdks in VENDOR_SDK_KEYWORDS.items():
            for sdk in sdks:
                if sdk.lower() in content_lower:
                    # 找具体行
                    for line_no, line in enumerate(content.splitlines(), start=1):
                        if sdk.lower() in line.lower():
                            findings.append({
                                "type": "dependency",
                                "category": category,
                                "sdk": sdk,
                                "file": str(path.relative_to(root)),
                                "line": line_no,
                                "snippet": line.strip()[:120],
                                "is_external": True,
                            })
                            break
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="第三方依赖反向兜底识别(对应本 SKILL 检查项 9.8;概念源自 dev-logic-architect 核心原则 19)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("root", type=Path, help="代码根目录")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if not args.root.exists():
        print(f"❌ 路径不存在: {args.root}", file=sys.stderr)
        return 2

    code_findings = scan_code_for_http_clients(args.root)
    config_findings = scan_config_for_external_urls(args.root)
    dep_findings = scan_dependencies_for_vendors(args.root)

    external_code = [f for f in code_findings if f.get("is_external")]
    external_config = [f for f in config_findings if f.get("is_external")]

    aggregated = {
        "scan_root": str(args.root),
        "code_findings_total": len(code_findings),
        "code_findings_external": len(external_code),
        "config_findings_external": len(external_config),
        "dependency_findings": len(dep_findings),
        "code": external_code,
        "config": external_config,
        "dependencies": dep_findings,
        "passed": True,  # 此脚本不直接判通过/不通过,只输出清单供设计期参考
    }

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        return 0

    # 文本输出
    print(f"扫描根目录: {args.root}\n")
    print(f"📊 第三方依赖反向兜底扫描结果\n")

    print(f"代码层(HTTP 客户端调用): 共 {len(code_findings)} 处, 外部地址 {len(external_code)} 处")
    if external_code:
        print(f"  示例(前 5 条):")
        for f in external_code[:5]:
            url_info = f"  → {f['url']}" if f.get('url') else ""
            print(f"    [{f['client']}] {f['file']}:L{f['line']}{url_info}")
    print()

    print(f"配置层(外部 URL): {len(external_config)} 处")
    if external_config:
        for f in external_config[:5]:
            print(f"    {f['file']}:L{f['line']}  {f['url']}")
            print(f"      → {f['snippet']}")
    print()

    print(f"依赖层(Vendor SDK): {len(dep_findings)} 处")
    if dep_findings:
        seen_sdks: Set[str] = set()
        for f in dep_findings:
            key = f"{f['category']}/{f['sdk']}"
            if key in seen_sdks:
                continue
            seen_sdks.add(key)
            print(f"    [{f['category']}] {f['sdk']}  ({f['file']}:L{f['line']})")
    print()

    if external_code or external_config or dep_findings:
        print("⚠️  反向识别到外部依赖信号,设计期 B.7 章节必须逐一登记并标注交付状态。")
        print("    若 PRD 未提及上述任一外部依赖 → 触发主动询问用户机制。")
        print("    详见 dev-logic-architect 核心原则 19「第三方依赖反向兜底识别」")
    else:
        print("✅ 三向扫描均无外部依赖信号(代码 + 配置 + 依赖清单)")
        print("    B.7 章节可标注'无外部依赖',但仍需附扫描证据(本次脚本输出)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
