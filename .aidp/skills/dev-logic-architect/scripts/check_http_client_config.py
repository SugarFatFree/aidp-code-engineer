#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP 客户端配置驱动一致性检查器
用于 dev-logic-architect SKILL 的质量审计

检测项:
1. A.2 是否包含「HTTP 客户端落地」子章节
2. A.2 是否提供 Bean/Client 初始化示例
3. A.2 是否提供配置块(application.yml/config.yaml/.env/appsettings.json)
4. 配置块是否使用 ${ENV_VAR} 占位符,无明文凭证
5. B.7 第三方集成项是否引用 A.2 配置 Key
6. 代码示例是否硬编码 IP/URL

不覆盖(以语义判定为主):
- 「失败返回契约 ⟷ 调用方失败判定对齐」(核心原则 16 第 4 子项 / checklist 检查项 8 失败返回契约、检查项 4 系统故障吞成空数据)
  属**语义层**判定——"吞异常返裸空"与"带 `_error` 标记"是否在同一调用链混用、系统故障是否被静默降级为空数据,
  需理解链路上下文,grep 难以可靠区分"真空数据"与"故障吞空",极易误报,故不在本脚本硬核覆盖,
  交由 Quality Review Agent 按 checklist 语义审查。本脚本只管配置完备性/无硬编码,不判失败返回语义。

用法:
  python check_http_client_config.py <设计文档路径或目录>   # 目录模式合并全部 .md 再扫
  python check_http_client_config.py <设计文档路径或目录> --json

退出码: 0=通过(含纯 CRUD/仅前端"无外部集成"时 N/A 跳过), 1=不通过
"""

import argparse
import json
import re
import sys
from pathlib import Path


def extract_sections(content):
    """提取 A.2 和 B.7 章节内容"""
    a2_pattern = re.compile(
        r'##\s*A\.2[^\n]*基础框架.*?(?=##\s*A\.\d|##\s*B\.|$)',
        re.DOTALL | re.IGNORECASE
    )
    b7_pattern = re.compile(
        r'##\s*B\.7[^\n]*外部依赖.*?(?=##\s*B\.\d|##\s*C\.|$)',
        re.DOTALL | re.IGNORECASE
    )

    a2_match = a2_pattern.search(content)
    b7_match = b7_pattern.search(content)

    return (
        a2_match.group(0) if a2_match else '',
        b7_match.group(0) if b7_match else ''
    )


def check_http_client_section(a2_content):
    """检查 A.2 是否包含 HTTP 客户端落地章节"""
    keywords = [
        'HTTP 客户端落地',
        'HTTP客户端落地',
        'HTTP Client',
        'http客户端',
        'HTTP 客户端配置'
    ]
    for kw in keywords:
        if re.search(re.escape(kw), a2_content, re.IGNORECASE):
            return True, "找到 HTTP 客户端落地章节"
    return False, "未找到 HTTP 客户端落地相关章节"


def check_init_example(a2_content):
    """检查是否包含 Bean/Client 初始化示例"""
    code_blocks = re.findall(r'```(?:java|go|python|javascript|typescript|csharp|kotlin)\s*\n(.*?)\n```', a2_content, re.DOTALL | re.IGNORECASE)

    init_patterns = [
        r'@Bean',
        r'@Configuration',
        r'FeignClient',
        r'RestTemplate',
        r'HttpClient',
        r'new\s+\w+Client',
        r'client\s*=',
        r'def\s+\w+_client',
        r'axios\.create',
        r'IHttpClientFactory'
    ]

    for block in code_blocks:
        for pattern in init_patterns:
            if re.search(pattern, block, re.IGNORECASE):
                return True, f"找到初始化示例(匹配 {pattern})"

    return False, "未找到 Bean/Client 初始化代码示例"


def check_config_block(a2_content):
    """检查是否包含配置块"""
    config_patterns = [
        r'```ya?ml\s*\n.*?application\.ya?ml',
        r'```ya?ml\s*\n.*?config\.ya?ml',
        r'```properties\s*\n',
        r'```json\s*\n.*?appsettings\.json',
        r'```env\s*\n',
        r'```bash\s*\n.*?\.env'
    ]

    for pattern in config_patterns:
        if re.search(pattern, a2_content, re.DOTALL | re.IGNORECASE):
            return True, "找到配置块"

    return False, "未找到配置块(application.yml/config.yaml/.env/appsettings.json)"


def check_env_placeholder(a2_content):
    """检查配置是否使用 ENV 占位符,无明文凭证"""
    config_blocks = re.findall(r'```(?:ya?ml|properties|json|env|bash)\s*\n(.*?)\n```', a2_content, re.DOTALL | re.IGNORECASE)

    issues = []
    has_placeholder = False

    for block in config_blocks:
        if re.search(r'\$\{[A-Z_][A-Z0-9_]*\}', block):
            has_placeholder = True

        secrets = re.findall(
            r'(?:api[_-]?key|secret|token|password|private[_-]?key)\s*[:=]\s*["\']?([^"\'\s\n]+)',
            block,
            re.IGNORECASE
        )

        for secret in secrets:
            if not re.match(r'\$\{[A-Z_][A-Z0-9_]*\}', secret):
                issues.append(f"发现明文凭证: {secret[:20]}...")

    if issues:
        return False, "; ".join(issues)

    if not has_placeholder:
        return False, "配置块未使用 ${ENV_VAR} 占位符"

    return True, "配置使用 ENV 占位符,无明文凭证"


def extract_config_keys(a2_content):
    """从 A.2 配置块提取所有配置 Key"""
    config_blocks = re.findall(r'```(?:ya?ml|properties)\s*\n(.*?)\n```', a2_content, re.DOTALL | re.IGNORECASE)

    keys = set()
    for block in config_blocks:
        yaml_keys = re.findall(r'^([a-z0-9._-]+):', block, re.MULTILINE | re.IGNORECASE)
        keys.update(yaml_keys)

        prop_keys = re.findall(r'^([a-z0-9._-]+)\s*=', block, re.MULTILINE | re.IGNORECASE)
        keys.update(prop_keys)

    return keys


def check_b7_references(b7_content, a2_keys):
    """检查 B.7 是否引用 A.2 配置 Key"""
    if not b7_content:
        return True, "无 B.7 章节,跳过检查"

    if not a2_keys:
        return True, "A.2 无配置 Key,跳过 B.7 引用检查"

    key_refs = re.findall(r'`([a-z0-9._-]+)`', b7_content, re.IGNORECASE)

    missing = []
    for ref in key_refs:
        if '.' in ref and ref not in a2_keys:
            partial_match = any(key.startswith(ref.split('.')[0]) for key in a2_keys)
            if not partial_match:
                missing.append(ref)

    if missing:
        return False, f"B.7 引用了 A.2 中不存在的配置 Key: {', '.join(missing[:3])}"

    return True, "B.7 引用的配置 Key 均在 A.2 中存在"


def check_hardcoded_urls(content):
    """检查是否硬编码 IP/URL"""
    code_blocks = re.findall(r'```(?:java|go|python|javascript|typescript|csharp|kotlin)\s*\n(.*?)\n```', content, re.DOTALL | re.IGNORECASE)

    issues = []
    for block in code_blocks:
        ips = re.findall(r'(?:url\s*=\s*|Uri\(|base_url\s*=\s*)["\']?(https?://\d+\.\d+\.\d+\.\d+)', block, re.IGNORECASE)
        issues.extend([f"硬编码 IP: {ip}" for ip in ips])

        localhosts = re.findall(r'(?:url\s*=\s*|Uri\(|base_url\s*=\s*)["\']?(https?://localhost[:\d]*)', block, re.IGNORECASE)
        issues.extend([f"硬编码 localhost: {loc}" for loc in localhosts])

        domains = re.findall(r'(?:url\s*=\s*|Uri\(|base_url\s*=\s*)["\']https?://[a-z0-9.-]+\.[a-z]{2,}[^${\s"\']*', block, re.IGNORECASE)
        for domain in domains:
            if '${' not in domain:
                issues.append(f"硬编码域名: {domain[:50]}")

    if issues:
        return False, "; ".join(issues[:3])

    return True, "代码示例未硬编码 IP/URL"


def main():
    parser = argparse.ArgumentParser(description='HTTP 客户端配置驱动一致性检查')
    parser.add_argument('path', help='设计文档路径或目录')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    args = parser.parse_args()

    path = Path(args.path)

    if path.is_dir():
        files = sorted(path.glob('**/*.md'))
        if not files:
            print(json.dumps({"error": "未找到 Markdown 文件"}, ensure_ascii=False) if args.json else "错误: 未找到 Markdown 文件")
            sys.exit(2)  # 入参错(路径不存在 / 无 .md),非产物违规
        # 多文件拆分模式:A.2(HTTP 客户端落地)与 B.7(配置引用)可能分散在不同子文档,
        # 合并全部 md 文本后再扫,避免只查 files[0] 漏检其余文档(与其它 check 脚本"遍历全部 md"对齐)
        content = "\n".join(f.read_text(encoding='utf-8', errors='replace') for f in files)
    else:
        if not path.exists():
            print(json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False) if args.json else f"错误: 文件不存在: {path}")
            sys.exit(2)  # 入参错(路径不存在 / 无 .md),非产物违规
        content = path.read_text(encoding='utf-8', errors='replace')
    a2_content, b7_content = extract_sections(content)

    # SKILL.md 自检 23(a)(= quality-review-checklist.md 检查项/维度 8「外部依赖与集成说明」
    # 的 HTTP 客户端 Critical 子项;⚠️ 此处的 23 是**作者侧自检编号**,不是 QR 维度 23
    # 「缓存机制用户确认」——两套编号不可换算,见 SKILL.md「多套编号并存」节)
    # 是条件性的:仅"若 Phase 1 Step 3 选定 HTTP 客户端 / 存在外部集成"时才要求 A.2 落地。
    # 纯 CRUD / 仅前端设计无外部依赖时(SKILL 核心原则:B.7 标注"无外部依赖,本期不涉及"),本检查 N/A——
    # 不得把"无 HTTP 客户端章节"误判为不通过(对齐 SKILL.md「若 PRD 未涉及任何外部集成(纯 CRUD 系统)」)。
    has_http_section = check_http_client_section(a2_content)[0]
    NO_INTEGRATION_RE = re.compile(
        r"无外部\s*(?:依赖|集成)|无第三方\s*(?:依赖|集成|接口|服务|调用)|"
        r"(?:无|没有|不涉及)[^\n。]{0,8}(?:外部集成|外部依赖|外部接口|第三方)|纯\s*CRUD",
        re.IGNORECASE)
    declares_no_integration = bool(NO_INTEGRATION_RE.search(content))

    # ── 反证:设计里出现了具体的外部端点,则无论文中哪句话写了"不涉及第三方",都不算无外部集成 ──
    # 场景:B.7 列了银行代扣/短信平台的真实域名,而 B.5 有一句"权限模型不涉及第三方登录"——
    # 只按全文正则会把整份检查误跳过,让"真有外部集成却缺配置块/ENV 占位符"的设计静默放行。
    external_endpoint = re.compile(
        r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(?:com|org))([a-z0-9.-]+\.[a-z]{2,})",
        re.IGNORECASE)
    # ★文档/仓库/规范站不算「外部集成证据」:A.2 里引一句框架官方文档链接
    # (`参考 https://docs.spring.io/...`)极常见,若把它也当集成端点,纯 CRUD 设计的
    # N/A 跳过就会被这条链接顶掉,判出一条「A.2 无 HTTP 客户端落地章节」的不可修复 Critical。
    DOC_HOST = re.compile(
        r"^(?:docs?|developer|guide|guides|wiki|blog|learn|help|support|www)\."
        r"|(?:github|gitee|gitlab|stackoverflow|baeldung|wikipedia|npmjs|mvnrepository)\."
        r"|(?:readthedocs\.io|spring\.io|apache\.org|w3\.org|ietf\.org|json-schema\.org"
        r"|openapis\.org|oracle\.com|python\.org|golang\.org|nodejs\.org|mozilla\.org)$",
        re.IGNORECASE)

    def _has_external(text):
        return any(not DOC_HOST.search(m.group(1))
                   for m in external_endpoint.finditer(text))

    has_external_evidence = _has_external(a2_content) or _has_external(b7_content)

    # 两种 N/A 形态都要覆盖:
    #  ① A.2 根本没写 HTTP 客户端落地章节 + 文中声明无外部集成;
    #  ② A.2 写了「HTTP 客户端落地」小节但只是一句"本期无外部集成/不涉及"的占位
    #     (既无初始化示例也无配置块)——此时同样无从检查,若判不通过会让 QR 陷入
    #     "没东西可改却反复重写"的死循环。
    #     ★形态②的"无外部集成"声明必须出现在 **A.2 小节自身**:该小节写了标题却没有
    #     初始化示例/配置块,恰恰也是"真有外部集成但漏写配置"的失败态,二者只能靠
    #     声明位置区分。若沿用全文匹配,文档任意角落一句"不涉及第三方登录"就能把
    #     真实缺陷洗成 N/A(552a50e 引入的放宽即有此洞)。
    http_section_is_placeholder = (
        has_http_section
        and bool(NO_INTEGRATION_RE.search(a2_content))
        and not check_init_example(a2_content)[0]
        and not check_config_block(a2_content)[0]
    )
    if (declares_no_integration and not has_external_evidence
            and (not has_http_section or http_section_is_placeholder)):
        msg = "设计已声明无外部集成需求(纯 CRUD / 仅前端),HTTP 客户端配置检查 N/A,跳过"
        if args.json:
            print(json.dumps({"file": str(path), "passed": True, "skipped": True,
                              "msg": msg}, ensure_ascii=False, indent=2))
        else:
            print(f"\n检查目标: {path}\n⏭️  {msg}\n")
        sys.exit(0)

    results = []

    checks = [
        ("A.2 包含 HTTP 客户端落地章节", check_http_client_section(a2_content)),
        ("A.2 包含 Bean/Client 初始化示例", check_init_example(a2_content)),
        ("A.2 包含配置块", check_config_block(a2_content)),
        ("配置使用 ENV 占位符无明文凭证", check_env_placeholder(a2_content)),
    ]

    a2_keys = extract_config_keys(a2_content)
    checks.append(("B.7 引用 A.2 配置 Key", check_b7_references(b7_content, a2_keys)))
    checks.append(("代码示例无硬编码 IP/URL", check_hardcoded_urls(content)))

    all_pass = True
    for name, (passed, msg) in checks:
        status = "✅ 通过" if passed else "❌ 不通过"
        results.append({
            "项": name,
            "状态": status,
            "说明": msg
        })
        if not passed:
            all_pass = False

    if args.json:
        print(json.dumps({
            "file": str(path),
            "passed": all_pass,
            "results": results
        }, ensure_ascii=False, indent=2))
    else:
        print(f"\n检查目标: {path}\n")
        print(f"{'项':<40} {'状态':<12} {'说明'}")
        print("-" * 100)
        for r in results:
            print(f"{r['项']:<40} {r['状态']:<12} {r['说明']}")
        print("\n" + ("=" * 100))
        print(f"总体结果: {'✅ 全部通过' if all_pass else '❌ 存在问题'}\n")

    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
