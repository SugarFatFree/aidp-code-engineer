#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存机制用户确认核验脚本
用于 dev-logic-architect SKILL 的质量审计

核心约束(对应核心原则 17):
  详细设计中出现缓存关键词 → 必须能找到"用户已确认"标注 / A.2 缓存方案子章节 / Module E 待澄清条目
  否则视为"自作主张添加缓存机制",违反核心原则 17

检测项:
1. 扫描设计文档中的缓存关键词(Redis/Memcached/Caffeine/@Cacheable/...)
2. 对每条疑似缓存语句,在前后上下文中查找用户确认标注或 A.2 缓存方案章节
3. 排除豁免场景(HTTP 协商缓存/JVM 内置缓存/连接池/CDN 边缘缓存等)
4. 输出违规清单(关键词+所在行+缺失的确认标注)

退出码: 0=通过, 1=不通过

用法:
  python check_cache_user_confirmed.py <设计文档路径或目录>
  python check_cache_user_confirmed.py <设计文档路径或目录> --json
"""

import argparse
import json
import re
import sys
from pathlib import Path


CACHE_KEYWORD_PATTERN = re.compile(
    r'(Redis(?!Config)|Memcached|Caffeine|EhCache|Hazelcast|'
    r'Spring\s+Cache|@Cacheable|@CacheEvict|@CachePut|@Cache\b|'
    r'CacheManager|RedisTemplate|Redisson|StringRedisTemplate|'
    r'本地缓存|多级缓存|缓存层|缓存\s*TTL|缓存失效|缓存预热|'
    r'缓存击穿|缓存雪崩|缓存穿透|缓存穿透防护|布隆过滤器(?=.*缓存)|'
    r'MyBatis\s+二级缓存|Hibernate\s+L2|JPA\s+@Cacheable|'
    r'localStorage(?=.*缓存)|sessionStorage(?=.*缓存))',
    re.IGNORECASE
)


CONFIRM_PATTERN = re.compile(
    r'(用户同意|用户确认|已征得用户同意|已经用户确认|'
    r'缓存方案[(()]用户确认后填写[)]|'
    r'缓存方案[((]已确认[))]|'
    r'已确认使用缓存|建议使用缓存\(待用户确认\)|'
    r'🔧\s*暂行方案[((].*缓存|'
    r'❓\s*待澄清.*缓存|'
    r'#\s*缓存方案|'
    r'##+\s*缓存方案|'
    r'A\.2.*缓存方案)',
    re.IGNORECASE
)


# ⚠️ 锁语境负向护栏：Redis 分布式锁归检查项 32（核心原则 24 的 P1 档），**不是**本维度的缓存。
#    没有这道护栏时，一个逐条满足核心原则 24 的合规 P1 设计（SET NX PX / Redisson RLock / 看门狗续期）
#    会被本维度判 Critical —— 照 SKILL 推荐档位做设计，必然挂在 SKILL 自己的另一道硬门上。
#    词表与 check_lock_strategy.py 的 LOCK_CTX_RE 保持同源。
LOCK_CTX_RE = re.compile(r"锁|lock|FOR\s+UPDATE|SETNX|Redisson|RLock|互斥|临界区|看门狗|leaseTime",
                         re.IGNORECASE)

EXEMPT_PATTERN = re.compile(
    r'(Cache-Control|ETag|If-None-Match|If-Modified-Since|Last-Modified|'
    r'304\s+Not\s+Modified|协商缓存|HTTP\s+缓存头|'
    r'连接池|线程池|JVM\s+内置|方法内联|字符串常量池|'
    r'class\s+元数据|webpack|静态资源缓存|浏览器缓存|'
    r'CDN\s+边缘缓存|DNS\s+解析缓存|'
    r'PreparedStatement\s+Cache|语句缓存|查询计划缓存预热|'
    r'package-lock|yarn\.lock|pnpm-lock|RedisConfig\s*类)',
    re.IGNORECASE
)


CONTEXT_BEFORE = 30
CONTEXT_AFTER = 10


def has_global_cache_section(content):
    """检查文档全局是否有 A.2 缓存方案章节(用户已确认的标志)"""
    patterns = [
        r'###?\s*A\.2.*缓存方案',
        r'###?\s*缓存方案',
        r'###?\s*缓存设计',
        r'###?\s*缓存策略[^(待]',
    ]
    for p in patterns:
        if re.search(p, content, re.IGNORECASE):
            return True
    return False


def scan_file(path):
    """扫描单个文件,返回违规列表"""
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return [{"error": f"读取失败: {e}", "file": str(path)}]

    violations = []
    has_section = has_global_cache_section(text)
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if EXEMPT_PATTERN.search(line):
            continue
        # 锁语境整行跳过（归检查项 32，见 LOCK_CTX_RE 上方注释）
        if LOCK_CTX_RE.search(line):
            continue

        m = CACHE_KEYWORD_PATTERN.search(line)
        if not m:
            continue

        ctx_start = max(0, i - CONTEXT_BEFORE)
        ctx_end = min(len(lines), i + CONTEXT_AFTER + 1)
        ctx = '\n'.join(lines[ctx_start:ctx_end])

        if has_section or CONFIRM_PATTERN.search(ctx):
            continue

        violations.append({
            "file": str(path),
            "line": i + 1,
            "keyword": m.group(0),
            "snippet": line.strip()[:120]
        })

    return violations


def collect_files(target):
    """收集待扫描的 Markdown 文件"""
    p = Path(target)
    if p.is_file():
        return [p] if p.suffix.lower() == '.md' else []
    if p.is_dir():
        return sorted(p.rglob('*.md'))
    return []


def render_text(target, files, violations):
    print(f"\n缓存机制用户确认核验")
    print(f"扫描目标: {target}")
    print(f"扫描文件数: {len(files)}")
    print("-" * 80)

    if not violations:
        print("✅ 全部通过 - 未发现自作主张添加的缓存机制")
        return 0

    print(f"❌ 不通过 - 发现 {len(violations)} 处疑似违规")
    print()
    print(f"{'文件':<50} {'行号':<8} {'关键词':<20} 片段")
    print("-" * 120)
    for v in violations:
        if 'error' in v:
            print(f"  ⚠ {v['file']}: {v['error']}")
            continue
        file_short = v['file'][-50:] if len(v['file']) > 50 else v['file']
        print(f"{file_short:<50} L{v['line']:<7} {v['keyword']:<20} {v['snippet']}")

    print()
    print("修复建议:")
    print("  方案 1: 删除缓存相关描述,业务接口直接走数据库")
    print("  方案 2: 主动询问用户是否使用缓存,确认后在 A.2 添加「缓存方案」子章节")
    print("  方案 3: 在 Module E 添加「建议使用缓存(待用户确认)」待澄清条目")
    print()
    print("详见: dev-logic-architect/SKILL.md 核心原则 17「缓存机制用户确认原则(Critical)」")
    return 1


def render_json(target, files, violations):
    payload = {
        "target": str(target),
        "files_scanned": len(files),
        "violation_count": len(violations),
        "passed": len(violations) == 0,
        "violations": violations,
        "principle_ref": "dev-logic-architect/SKILL.md 核心原则 17",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not violations else 1


def main():
    parser = argparse.ArgumentParser(
        description='缓存机制用户确认核验 - 扫描设计文档中的缓存关键词,核验是否经用户确认'
    )
    parser.add_argument('target', help='设计文档路径或目录')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    args = parser.parse_args()

    files = collect_files(args.target)
    if not files:
        msg = f"未找到 Markdown 文件: {args.target}"
        if args.json:
            print(json.dumps({"error": msg, "passed": False}, ensure_ascii=False))
        else:
            print(f"错误: {msg}")
        sys.exit(2)  # 入参错(路径不存在 / 无 .md),非产物违规

    all_violations = []
    for f in files:
        all_violations.extend(scan_file(f))

    if args.json:
        sys.exit(render_json(args.target, files, all_violations))
    else:
        sys.exit(render_text(args.target, files, all_violations))


if __name__ == '__main__':
    main()
