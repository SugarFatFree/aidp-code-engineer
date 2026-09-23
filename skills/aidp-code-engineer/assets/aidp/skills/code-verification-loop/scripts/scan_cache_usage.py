#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缓存使用点扫描脚本(对应 code-verification-loop 维度 4「缓存代码与设计一致性」🔴 Critical)

扫描指定代码目录里的缓存使用关键词命中点,输出 `文件:行号 + 命中关键词 + 代码片段`,
供 Agent 与详细设计 A.2「缓存方案」子章节双向比对。

⚠️ 重要:本脚本只负责"采集缓存使用点",**不判定是否违规**。
   是否违规需 Agent 拿命中清单与详细设计 A.2 比对:
     - 设计无「缓存方案」但代码出现缓存 → ❌ Critical(未授权缓存)
     - 设计有「缓存方案」且一致 → ✅ 通过
     - 设计有但代码缺失 → ⚠️ Important
   因此本脚本退出码恒为 0(仅报告),不因命中而判错。

关键词集合(内联自包含,不跨 SKILL 引用):
   后端注解/组件: @Cacheable @CacheEvict @CachePut @Caching @EnableCaching
                  @Cache(Hibernate 二级缓存) <cache/>/<cache-ref>(MyBatis)
                  RedisTemplate Redisson CacheManager EhCache
                  Hazelcast Caffeine Memcached Spring Cache
   缓存概念词:    本地缓存 缓存层 缓存 TTL 缓存失效 缓存预热
                  缓存击穿 缓存雪崩 缓存穿透 MyBatis 二级缓存
   前端缓存:      localStorage sessionStorage 前端缓存
   ⚠️ 自实现 ConcurrentHashMap 当缓存用语义不确定(多数非缓存),误报高,刻意不收,仍需 Agent 人工补查

扫描文件类型: .java .ts .js .tsx .jsx .vue .py .xml .yml .yaml .kt .go
豁免目录:     node_modules .git dist build target out
              .next .nuxt vendor __pycache__ coverage .idea .vscode

退出码:
  0 = 始终(仅报告,命中与否都不判错;违规判定交给 Agent 比对设计 A.2)
  2 = 用法错误或目录不存在

用法:
  python scan_cache_usage.py <代码目录>
  python scan_cache_usage.py <代码目录> --json

JSON 输出:
  {"cache_hits": [{"file": ..., "line": ..., "keyword": ..., "snippet": ...}],
   "total": N}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 扫描的源码后缀
SCAN_SUFFIXES = {
    ".java", ".kt", ".ts", ".js", ".tsx", ".jsx", ".vue",
    ".py", ".go", ".xml", ".yml", ".yaml",
}

# 豁免目录段
EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "build", "target", "out",
    ".next", ".nuxt", "vendor", "__pycache__", ".idea", ".vscode",
    "coverage", ".nyc_output", "tmp", ".cache",
}

# 缓存关键词集合(内联自包含)。每项 (显示名, 编译后的正则)。
# 注解类用 \b 边界 + 可选 @;概念词直接子串匹配。大小写不敏感。
_KEYWORD_SPECS = [
    # 后端注解
    (r"@Cacheable", r"@Cacheable\b"),
    (r"@CacheEvict", r"@CacheEvict\b"),
    (r"@CachePut", r"@CachePut\b"),
    (r"@Caching", r"@Caching\b"),
    (r"@Cache (Hibernate L2)", r"@(?:[\w.]+\.)?Cache\b"),  # Hibernate 二级缓存注解,含 FQN 形式(@Cacheable/@CacheConfig 等因 \b 不误命中)
    (r"<cache (MyBatis)", r"<cache(?:-ref)?[\s/>]"),   # MyBatis mapper <cache/> / <cache-ref>
    (r"@EnableCaching", r"@EnableCaching\b"),
    # 后端组件/框架
    (r"RedisTemplate", r"\bRedisTemplate\b"),
    (r"Redisson", r"\bRedisson\b"),
    (r"CacheManager", r"\bCacheManager\b"),
    (r"EhCache", r"\bEh[-\s]?Cache\b"),
    (r"Hazelcast", r"\bHazelcast\b"),
    (r"Caffeine", r"\bCaffeine\b"),
    (r"Memcached", r"\bMemcached\b"),
    (r"Spring Cache", r"Spring[\s-]?Cache"),
    # 概念词(中文)
    (r"本地缓存", r"本地缓存"),
    (r"缓存层", r"缓存层"),
    (r"缓存 TTL", r"缓存\s*TTL"),
    (r"缓存失效", r"缓存失效"),
    (r"缓存预热", r"缓存预热"),
    (r"缓存击穿", r"缓存击穿"),
    (r"缓存雪崩", r"缓存雪崩"),
    (r"缓存穿透", r"缓存穿透"),
    (r"MyBatis 二级缓存", r"MyBatis\s*二级缓存"),
    # 前端缓存
    (r"localStorage", r"\blocalStorage\b"),
    (r"sessionStorage", r"\bsessionStorage\b"),
    (r"前端缓存", r"前端缓存"),
]

KEYWORD_PATTERNS = [
    (name, re.compile(pat, re.IGNORECASE)) for name, pat in _KEYWORD_SPECS
]


def is_excluded(path: Path, root: Path) -> bool:
    """仅基于 root 以内的相对路径判断排除,避免项目位于含排除名祖先目录时被整体跳过。"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = set(rel.parts)
    return bool(parts & EXCLUDED_DIRS)


def scan_file(path: Path, root: Path) -> List[Dict]:
    hits: List[Dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pat in KEYWORD_PATTERNS:
            if pat.search(line):
                hits.append({
                    "file": rel,
                    "line": lineno,
                    "keyword": name,
                    "snippet": line.strip()[:200],
                })
    return hits


def scan(root: Path) -> Dict:
    cache_hits: List[Dict] = []
    scanned = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if is_excluded(path, root):
            continue
        scanned += 1
        cache_hits.extend(scan_file(path, root))
    # 稳定排序: 文件 → 行号
    cache_hits.sort(key=lambda h: (h["file"], h["line"]))
        # ⚠️ 「0 命中」必须能与「0 文件被扫(路径给错)」区分开:早期二者都输出 total=0 → 报告照抄
    #    「✅ 无残留 / ✅ 一致」,而把 `src/` 误写成后端源码根这类**路径给错**属最常见形态,
    #    本脚本又正是 Critical 档的采集侧 → 假绿。故补 scanned_files,为 0 时置 skipped=true。
    return {"cache_hits": cache_hits, "total": len(cache_hits), "scanned_files": scanned, "skipped": scanned == 0}


def render_text(result: Dict) -> str:
    out: List[str] = []
    out.append("=== 缓存使用点扫描 (维度 4: 缓存代码与设计一致性) ===")
    total = result["total"]
    out.append(f"\n命中缓存使用点: {total} 处")
    if total == 0:
        out.append("\n✅ 未发现缓存使用关键词。")
        out.append("   (若详细设计 A.2 声明了缓存方案而代码无实现,属 ⚠️ Important,需 Agent 另行核对)")
        return "\n".join(out)
    for h in result["cache_hits"]:
        out.append(f"  - {h['file']}:{h['line']}  [{h['keyword']}]  {h['snippet']}")
    out.append("\n⚠️ 以上仅为命中清单,是否违规由 Agent 与详细设计 A.2「缓存方案」比对决定:")
    out.append("   · 设计无「缓存方案」但出现命中 → ❌ Critical 未授权缓存")
    out.append("   · 设计有「缓存方案」且一致     → ✅ 通过")
    out.append("   · 设计有但代码未实现           → ⚠️ Important")
    out.append("   · Key/TTL/失效逻辑与设计不符   → ❌ Critical")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", type=Path, help="代码根目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出供 Agent 解析")
    args = parser.parse_args(argv)

    if not args.root.exists() or not args.root.is_dir():
        print(f"错误: 目录不存在或不是目录: {args.root}", file=sys.stderr)
        return 2

    result = scan(args.root)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))

    # 仅报告:命中与否都返回 0,违规判定交给 Agent 比对设计 A.2
    return 0


if __name__ == "__main__":
    sys.exit(main())
