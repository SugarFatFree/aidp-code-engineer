#!/usr/bin/env python3
"""
.env / .env.example 合规检查脚本

用法:
  python check_env_config.py [项目根目录] [--json] [--strict] [--require-env-example]

检查项目的环境配置文件是否符合企业内部开发规范:
  1. .env.example 是否存在(⭕ 可选形态,默认 Important;加 --require-env-example 才判 Critical)
  2. .gitignore 是否排除了 .env
  3. .env.example 是否包含生产环境敏感信息(不允许)
  4. application.yml 是否使用环境变量引用(而非硬编码)
  5. 配置完整性检查(中间件连接信息是否齐全)

⚠️ N/A 跳过(全仓退出码约定③):项目若**根本没有** .env / .env.example、且配置文件里也没有
   ${} 环境变量引用,说明它压根不采用这套形态 —— 整脚本 N/A 跳过(exit 0),
   --json 输出 "skipped": true 供调用方把「没跑」与「真通过」区分开。
   ⛔ 此前 .env.example 不存在恒判 Critical + exit 1,等于给所有不采用该形态的项目一个**恒红门**;
   而恒红门的真实后果是整个检查被调用方无视(本仓库既有教训:假红常驻 = 硬门被绕过)。

⚠️ .env.example 是**可选产出物**:维护"示例副本"必然带来「改了 .env 忘改 .env.example」的双写漂移,
   且企业内网直填开发口令会把它写进 git 历史且不可撤销。故本脚本默认不强制其存在;
   团队规范确实要求它时,用 --require-env-example 把该项提回 Critical。

退出码:
  0 = 通过 / N/A 跳过     1 = 检出违规(严重度分档走 --json,不占退出码)     2 = 入参或环境错

跨平台支持: Linux / macOS / Windows (Python 3.6+)
"""

import json
import re
import sys
from pathlib import Path

# 生产环境敏感信息关键词(不允许出现在 .env.example 中)
PROD_SENSITIVE_PATTERNS = [
    (r'(?i)(prod|production|线上|生产).*(?:password|secret|key|token)', "生产环境密钥"),
    (r'(?i)(?:password|secret|key|token).*(?:prod|production|线上|生产)', "生产环境密钥"),
]

# 常见中间件配置键名
# 值为「必填项组」列表:每个组是一串同义键名,组内任一命中即视为该项已配置(兼容多种命名习惯)。
# 例如 mysql 的主机既可写 DB_HOST 也可写 MYSQL_HOST,二者是同义而非两个独立必填项 ——
# 否则项目只用 DB_* 命名(全配齐)时会误报"缺少 MYSQL_HOST"等(互斥命名混列的假阳性)。
MIDDLEWARE_KEYS = {
    'minio': [['MINIO_ENDPOINT'], ['MINIO_ACCESS_KEY'], ['MINIO_SECRET_KEY'], ['MINIO_BUCKET']],
    'redis': [['REDIS_HOST'], ['REDIS_PORT'], ['REDIS_PASSWORD']],
    'nacos': [['NACOS_SERVER_ADDR'], ['NACOS_NAMESPACE']],
    'mysql': [['DB_HOST', 'MYSQL_HOST'], ['DB_PORT', 'MYSQL_PORT'],
              ['DB_USERNAME', 'MYSQL_USER'], ['DB_PASSWORD', 'MYSQL_PASSWORD'],
              ['DB_NAME', 'MYSQL_DATABASE']],
    'postgresql': [['PG_HOST', 'POSTGRES_HOST'], ['PG_PORT', 'POSTGRES_PORT'],
                   ['PG_USER', 'POSTGRES_USER'], ['PG_PASSWORD', 'POSTGRES_PASSWORD'],
                   ['PG_DATABASE', 'POSTGRES_DB']],
    'rabbitmq': [['RABBITMQ_HOST'], ['RABBITMQ_PORT'], ['RABBITMQ_USER'], ['RABBITMQ_PASSWORD']],
    'kafka': [['KAFKA_BOOTSTRAP_SERVERS', 'KAFKA_BROKERS']],
    'elasticsearch': [['ES_HOST', 'ELASTICSEARCH_URL'], ['ES_PORT', 'ELASTICSEARCH_URL']],
}


def parse_env_file(filepath: Path) -> dict:
    """解析 .env 文件，返回 key-value 字典"""
    env = {}
    if not filepath.exists():
        return env
    try:
        for line in filepath.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                env[key.strip()] = value.strip().strip('"').strip("'")
    except (OSError, PermissionError):
        pass
    return env


def scheme_in_use(root: Path) -> tuple:
    """判定本项目是否采用 .env / 环境变量注入这套配置形态。

    返回 (in_use: bool, reason: str)。三个信号任一命中即算采用:
      ① 有 .env.example  ② 有 .env  ③ Spring 配置文件里出现 ${} 环境变量引用
    三者皆无 = 项目压根不用这套形态,整脚本 N/A 跳过 —— 而不是判它"不合规"。
    """
    if (root / '.env.example').exists():
        return True, "存在 .env.example"
    if (root / '.env').exists():
        return True, "存在 .env"
    yml = find_spring_config(root)
    if yml is not None:
        try:
            if '${' in yml.read_text(encoding='utf-8', errors='ignore'):
                return True, f"{yml.name} 使用了 ${{}} 环境变量引用"
        except (OSError, PermissionError):
            pass
    return False, "无 .env / .env.example,配置文件也未使用 ${} 环境变量引用"


def check_env_example_exists(root: Path, require: bool = False) -> dict:
    """检查 1: .env.example 是否存在(⭕ 可选形态)

    ⚠️ 默认 **Important 不判 Critical**:`.env.example` 只是配置形态之一,另一种同样正当的做法是
    「运行时配置文件即权威、不维护示例副本」(避免改了 .env 忘改 .env.example 的双写漂移)。
    调用方团队规范确实强制它时,传 --require-env-example 把本项提回 Critical。
    """
    env_example = root / '.env.example'
    exists = env_example.exists()
    return {
        "check": ".env.example 文件存在",
        "passed": exists,
        "severity": "Critical" if require else "Important",
        "detail": str(env_example) if exists else
                  ("文件不存在,但 --require-env-example 要求它必须存在" if require else
                   "文件不存在。若本项目采用「运行时配置文件即权威、不维护示例副本」形态,这是正常的; "
                   "若团队规范要求示例副本,请补建或加 --require-env-example 使本项判 Critical")
    }


def find_spring_config(root: Path):
    """定位 Spring Boot 主配置文件(yml/yaml/properties),找不到返回 None。

    被 scheme_in_use() 与 check_yml_env_refs() 共用 —— 两处各写一份查找逻辑必然漂移
    (一处认 .properties 另一处不认,就会出现"跳过判定说没配、检查项说有配"的自相矛盾)。
    """
    for name in ('application.yml', 'application.yaml', 'application.properties'):
        p = root / 'src' / 'main' / 'resources' / name
        if p.exists():
            return p
    return None


def check_gitignore(root: Path) -> dict:
    """检查 2: .gitignore 是否排除 .env

    ⚠️ 严重度随「本机是否真有 .env」浮动:有 .env 文件才存在"把本机口令提交上去"的现实风险 → Critical;
    只有 .env.example、本机尚无 .env 时是**预防性**要求 → Important。
    此前不分情况一律 Critical,导致「没有 .env 也不打算有」的项目同样恒红。
    """
    has_env = (root / '.env').exists()
    sev = "Critical" if has_env else "Important"
    gitignore = root / '.gitignore'
    if not gitignore.exists():
        return {
            "check": ".gitignore 排除 .env",
            "passed": False,
            "severity": sev,
            "detail": ".gitignore 文件不存在"
        }

    try:
        content = gitignore.read_text(encoding='utf-8', errors='ignore')
        lines = [l.strip() for l in content.splitlines()]
        # 检查是否有排除 .env 的规则（排除 .env.example 等应提交的文件）
        env_ignore_patterns = ['.env', '.env.local', '.env*.local', '.env.development.local']
        has_env_rule = any(
            l in env_ignore_patterns or (l.startswith('.env') and 'example' not in l)
            for l in lines if not l.startswith('#') and l
        )
        return {
            "check": ".gitignore 排除 .env",
            "passed": has_env_rule,
            "severity": sev,
            "detail": "已排除" if has_env_rule else
                      (".gitignore 中未找到 .env 排除规则，而本机已存在 .env，本地配置可能被提交"
                       if has_env else ".gitignore 中未找到 .env 排除规则（本机暂无 .env，属预防性要求）")
        }
    except (OSError, PermissionError):
        return {
            "check": ".gitignore 排除 .env",
            "passed": False,
            "severity": sev,
            "detail": "无法读取 .gitignore"
        }


def check_no_prod_secrets(root: Path) -> dict:
    """检查 3: .env.example 不包含生产环境敏感信息"""
    env_example = root / '.env.example'
    if not env_example.exists():
        return {
            "check": ".env.example 无生产密钥",
            "passed": True,
            "severity": "Critical",
            "detail": "文件不存在，跳过检查"
        }

    try:
        content = env_example.read_text(encoding='utf-8', errors='ignore')
        issues = []
        for i, line in enumerate(content.splitlines(), 1):
            for pattern, desc in PROD_SENSITIVE_PATTERNS:
                if re.search(pattern, line):
                    issues.append(f"L{i}: {line.strip()[:80]} ({desc})")

        return {
            "check": ".env.example 无生产密钥",
            "passed": len(issues) == 0,
            "severity": "Critical",
            "detail": "无生产敏感信息" if not issues else f"发现 {len(issues)} 处疑似生产密钥: " + "; ".join(issues[:3])
        }
    except (OSError, PermissionError):
        return {
            "check": ".env.example 无生产密钥",
            "passed": False,
            "severity": "Critical",
            "detail": "无法读取文件"
        }


def check_yml_env_refs(root: Path) -> dict:
    """检查 4: application.yml 是否使用环境变量引用"""
    yml_file = find_spring_config(root)

    if yml_file is None:
        return {
            "check": "配置文件使用环境变量引用",
            "passed": True,
            "severity": "Important",
            "detail": "未找到 Spring Boot 配置文件，跳过检查"
        }

    try:
        content = yml_file.read_text(encoding='utf-8', errors='ignore')
        # 检查是否有硬编码的连接信息
        hardcoded_patterns = [
            (r'(?:host|url|endpoint|server):\s*(?!.*\$\{)[\w.-]+:\d+', "硬编码连接地址"),
            (r'(?:password|secret):\s*(?!.*\$\{)[^\s$]+', "硬编码密码"),
        ]
        issues = []
        for pattern, desc in hardcoded_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for m in matches:
                if '${' not in m and 'localhost' not in m.lower():
                    issues.append(f"{m.strip()[:60]} ({desc})")

        # 检查是否使用了 ${} 引用
        has_env_refs = '${' in content

        return {
            "check": "配置文件使用环境变量引用",
            "passed": has_env_refs and len(issues) == 0,
            "severity": "Important",
            "detail": "使用环境变量引用" if (has_env_refs and not issues) else
                      f"发现硬编码配置: " + "; ".join(issues[:3]) if issues else
                      "未使用 ${} 环境变量引用"
        }
    except (OSError, PermissionError):
        return {
            "check": "配置文件使用环境变量引用",
            "passed": False,
            "severity": "Important",
            "detail": "无法读取配置文件"
        }


def check_config_completeness(root: Path) -> dict:
    """检查 5: 配置完整性(中间件连接信息是否齐全)"""
    env_example = root / '.env.example'
    env_file = root / '.env'

    # 合并两个文件的 key
    all_keys = set()
    all_keys.update(parse_env_file(env_example).keys())
    all_keys.update(parse_env_file(env_file).keys())

    if not all_keys:
        return {
            "check": "中间件配置完整性",
            "passed": True,
            "severity": "Important",
            "detail": "无 .env 配置文件，跳过检查"
        }

    # 检测使用了哪些中间件
    # 每个中间件的必填项为「同义键组」列表:组内任一键命中即算该项已配置。
    def group_hit(group):
        return any(k.lower() in ak.lower() for k in group for ak in all_keys)

    detected_middleware = {}
    for mw_name, mw_groups in MIDDLEWARE_KEYS.items():
        matched = [g[0] for g in mw_groups if group_hit(g)]
        if matched:
            # 缺失项:整组同义键都没命中的组,展示该组首选键名
            missing = [g[0] for g in mw_groups if not group_hit(g)]
            detected_middleware[mw_name] = {
                "configured": matched,
                "missing": missing[:3]
            }

    issues = []
    for mw, info in detected_middleware.items():
        if info["missing"]:
            issues.append(f"{mw}: 缺少 {', '.join(info['missing'])}")

    return {
        "check": "中间件配置完整性",
        "passed": len(issues) == 0,
        "severity": "Important",
        "detail": f"检测到 {len(detected_middleware)} 个中间件配置，均完整" if not issues else
                  f"配置不完整: " + "; ".join(issues[:3]),
        "detected_middleware": list(detected_middleware.keys())
    }


def run_check(root: Path, output_json=False, strict=False, require_env_example=False):
    """执行全部检查(项目未采用 .env 形态时整体 N/A 跳过)"""
    in_use, why = scheme_in_use(root)
    if not in_use and not require_env_example:
        # ⚠️ 全仓退出码约定③:有 N/A 跳过分支的脚本,--json 必须输出可区分标记,
        #    否则调用方无法把「真通过」与「整档没跑」分开 —— 那正是假绿的来源。
        if output_json:
            print(json.dumps({
                "project_root": str(root),
                "skipped": True,
                "skip_reason": f"本项目未采用 .env/.env.example 配置形态({why}),全部检查 N/A",
                "total_checks": 0, "passed": 0, "failed": 0, "failed_critical": 0,
                "all_passed": True, "checks": []
            }, ensure_ascii=False, indent=2))
        else:
            print(f"⏭️  N/A 跳过:本项目未采用 .env/.env.example 配置形态({why})。")
            print("   若这不符合预期(例如配置文件不在 src/main/resources 下),请检查传入的项目根是否正确;")
            print("   若团队规范强制要求 .env.example,加 --require-env-example 让本项判 Critical。")
        sys.exit(0)

    checks = [
        check_env_example_exists(root, require=require_env_example),
        check_gitignore(root),
        check_no_prod_secrets(root),
        check_yml_env_refs(root),
        check_config_completeness(root),
    ]

    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    failed_critical = sum(1 for c in checks if not c["passed"] and c["severity"] == "Critical")

    if output_json:
        output = {
            "project_root": str(root),
            "skipped": False,
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "failed_critical": failed_critical,
            "all_passed": passed == total,
            "checks": checks
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("=" * 55)
        print(".env 配置合规检查报告")
        print("=" * 55)
        print(f"项目根目录: {root}")
        print()

        for i, c in enumerate(checks, 1):
            status = "✅" if c["passed"] else "❌"
            severity_icon = "🔴" if c["severity"] == "Critical" else "🟡"
            print(f"【检查 {i}】{c['check']} {severity_icon}")
            print(f"  {status} {c['detail']}")
            print()

        print("=" * 55)
        if passed == total:
            print(f"✅ 全部通过 ({passed}/{total})")
        else:
            print(f"❌ {total - passed} 项未通过 (Critical: {failed_critical})")
        print("=" * 55)

    if strict:
        sys.exit(0 if passed == total else 1)
    else:
        sys.exit(0 if failed_critical == 0 else 1)


def main():
    if '-h' in sys.argv[1:] or '--help' in sys.argv[1:]:
        print(__doc__)
        sys.exit(0)

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]

    output_json = '--json' in flags
    strict = '--strict' in flags
    require_env_example = '--require-env-example' in flags

    known = {'--json', '--strict', '--require-env-example'}
    unknown = [f for f in flags if f not in known]
    if unknown:
        msg = f"错误: 未知参数 {' '.join(unknown)}(可用: --json / --strict / --require-env-example)"
        if output_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        else:
            print(msg, file=sys.stderr)
        sys.exit(2)  # 入参错

    root = Path(args[0]) if args else Path('.')

    # ⚠️ exists() 与 is_dir() 必须分开判(全仓退出码约定②):合并写会把「路径根本不存在」
    #    与「传的是个文件」混成同一句「目录不存在」,报错文案与事实相反、排错方向被带偏。
    if not root.exists():
        msg = f"错误: 路径不存在 - {root}"
    elif not root.is_dir():
        msg = f"错误: 需要传目录,但传入的是文件 - {root}"
    else:
        msg = None
    if msg is not None:
        if output_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        else:
            print(msg)
        sys.exit(2)  # 入参错(路径不存在),非产物违规

    run_check(root, output_json=output_json, strict=strict,
              require_env_example=require_env_example)


if __name__ == "__main__":
    main()
