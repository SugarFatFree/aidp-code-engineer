#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维度 6「DI 依赖可解析性」静态回检（Java / Spring 专用，grep 级纯文本分析）。

拦的是什么
----------
编译期完全无感、只在 **Spring 容器启动期**才解析的错误。最典型：新类写
`@Autowired private RestTemplate restTemplate;`，但全项目没有任何 `RestTemplate`
的 `@Bean`（既有用法都是构造函数里 `new RestTemplate()`）——`mvn compile` 必过，
容器启动直接 `APPLICATION FAILED TO START: Field restTemplate ... required a bean
of type 'RestTemplate' that could not be found`。反馈周期是「提交 → 推送 → CICD →
部署 → 启动失败」十几分钟起，还污染部署记录；无人值守批量场景下一个 DI 错误让
整批 Sprint 部署验证空转。而它本可被一条 grep 静态拦下。

一并覆盖两类近亲（同样编译无感、启动期爆炸、纯静态可检）：
  · 多 bean 无 `@Qualifier` → NoUniqueBeanDefinitionException 风险
  · `@Value("${key}")` 无默认值且配置文件/配置项清单里查无此键 → 占位符解析失败

★ 本脚本**不编译、不打包、不起服务、不起 Spring 容器**，纯文本静态分析，
  成本与其余 grep 类检查同量级。

判定逻辑
--------
对注入点（`@Autowired`/`@Resource`/`@Inject` 字段、`@RequiredArgsConstructor` +
`private final` 构造注入、显式构造参数、setter 注入）提取注入类型 T，三源命中任一
即判「可解析」：
  1) 项目内组件：T 的定义类带 @Service/@Component/@Repository/@Controller/
     @RestController/@Configuration/@Mapper/@FeignClient/@Aspect 或
     @ConfigurationProperties（含 @EnableConfigurationProperties(T.class) 注册）；
     T 是接口/父类时，其带注解的实现（implements/extends T）也算来源；
     `@MapperScan` 约定下 *Mapper / *Dao 接口视为已注册
  2) 显式 @Bean：全仓存在返回类型为 T 的 @Bean 方法
  3) 框架自动配置：命中白名单（StringRedisTemplate / ObjectMapper / DataSource / …）

severity 口径（**精度优先，避免噪音误阻断**）
--------------------------------------------
  · Critical（近乎确定不可解析）
      ① 框架不自动装配的常见误注入类型（RestTemplate / WebClient / OkHttpClient / HttpClient）
      ② 仓内已定义为【具体类】却无组件注解 / @Bean / @ConfigurationProperties
      ③ @Value 键确缺且无默认值
  · Warn（静态无法确证，容忍跨模块 / 外部 starter）
      接口或抽象类无带注解实现；多 bean 无 @Qualifier（Spring 会先按字段名匹配
      beanName 兜底，不能判死）；全仓无来源但可能来自未扫描模块

增量快筛 `--changed-only`
--------------------------
默认全量扫描，服务**验收期**的维度 6 主检测点。加 `--changed-only` 后只报告落在
git 变更文件里的注入点，服务**开发期前置门** —— 写码当场拦下，而不是等到验收阶段。

⚠️ **只收窄「报告范围」，绝不收窄「bean 索引范围」。** bean 来源（组件注解、@Bean
方法、@ConfigurationProperties）照旧全仓解析 —— 否则新写的 `@Autowired Foo foo`
会因为 `FooImpl` 这次没改动而被误判成「无来源」，增量模式就成了误报机器。

`--base` 指定对比基准（默认 `HEAD` = 已改未提交；传 `origin/develop` 之类可比整条
分支）。**未跟踪的新文件一律纳入** —— 新建的 Java 类恰恰是 DI 问题最高发的来源，
漏掉它增量模式就白做了。非 git 仓库 / git 不可用时**退回全量并在 stderr 告警**
（全量是更严的一侧，安全失败）。

> **刻意不提供 `--gate`。** 本脚本默认就是「有 Critical → exit 1」；「默认恒 `exit 0`、
> 须显式 `--gate` 才让 Critical 返回 1」的查询模式与全仓退出码约定（`1` = 检出违规）
> 直接冲突，等于给调用方留一个「忘了加参数就静默放行」的假绿开关。确需「只看不闸」
> 请用 `--json` 读 `stats.critical` 自行决定，别让退出码撒谎。

用法
----
    python check_di_resolvability.py <代码目录> [--json] [--strict]
                                     [--config-keys-file <配置项清单.txt>]
                                     [--changed-only [--base <git-ref>]]

退出码：0 = 无 Critical（含「非 Java 项目 → 整维度跳过」）；1 = 有 Critical
（`--strict` 时 Warn 也返回 1）；2 = 用法/输入错误。
"""
import argparse
import json
import os
import subprocess
import re
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# 常量表
# ---------------------------------------------------------------------------

# 使 bean 被容器注册的类级注解
COMPONENT_ANNOTATIONS = {
    "Service", "Component", "Repository", "Controller", "RestController",
    "Configuration", "Mapper", "FeignClient", "Aspect", "ConfigurationProperties",
    "ControllerAdvice", "RestControllerAdvice", "Configurable",
}

# 框架 starter 自动装配的 bean（注入它们不需要项目自己声明 @Bean）
AUTOCONFIGURED = {
    # Spring 容器基础设施
    "ApplicationContext", "ConfigurableApplicationContext", "ApplicationEventPublisher",
    "Environment", "ConfigurableEnvironment", "ResourceLoader", "MessageSource",
    "ConversionService", "Validator", "BeanFactory", "ServletContext",
    # 数据访问
    "DataSource", "JdbcTemplate", "NamedParameterJdbcTemplate", "TransactionTemplate",
    "PlatformTransactionManager", "EntityManager", "EntityManagerFactory",
    "SqlSessionFactory", "SqlSessionTemplate", "MongoTemplate", "MongoDatabaseFactory",
    # 缓存 / 消息
    "StringRedisTemplate", "RedisTemplate", "ReactiveRedisTemplate",
    "RedisConnectionFactory", "RedissonClient", "CacheManager",
    "RabbitTemplate", "AmqpTemplate", "KafkaTemplate",
    # 序列化 / 邮件 / 检索 / 监控
    "ObjectMapper", "JavaMailSender", "MailSender",
    "ElasticsearchOperations", "ElasticsearchRestTemplate", "ElasticsearchClient",
    "MeterRegistry", "HealthEndpoint",
    # 异步 / 调度
    "TaskExecutor", "TaskScheduler", "AsyncTaskExecutor",
    # Web
    "RestTemplateBuilder", "WebClient.Builder", "ServerProperties",
    "HttpServletRequest", "HttpServletResponse", "HttpSession",
}

# 框架【不】自动装配、却最常被误 @Autowired 的类型 → 命中即 Critical
KNOWN_NOT_AUTOCONFIGURED = {
    "RestTemplate": "Spring Boot 只自动装配 RestTemplateBuilder，不装配 RestTemplate 本身",
    "WebClient": "Spring Boot 只自动装配 WebClient.Builder，不装配 WebClient 本身",
    "OkHttpClient": "OkHttp 无 Spring Boot 官方自动装配",
    "HttpClient": "JDK / Apache HttpClient 均无自动装配",
    "RestClient": "Spring 6.1 只自动装配 RestClient.Builder，不装配 RestClient 本身",
}

# 注入点注解
INJECT_ANNOTATIONS = {"Autowired", "Resource", "Inject"}

# 不当作 bean 类型看待的（值类型 / 容器类型 / JDK 常见类）
NON_BEAN_TYPES = {
    "int", "long", "short", "byte", "char", "boolean", "float", "double", "void",
    "Integer", "Long", "Short", "Byte", "Character", "Boolean", "Float", "Double",
    "String", "BigDecimal", "BigInteger", "Object", "Number",
    "Date", "LocalDate", "LocalDateTime", "LocalTime", "Instant", "Duration",
    "UUID", "Class", "Enum", "Exception", "RuntimeException", "Throwable",
}

# 注入 List<T>/Optional<T>/Map<String,T> 时解包出 T，但结论一律降级为 Warn
CONTAINER_TYPES = {"List", "Set", "Collection", "Optional", "Map", "ObjectProvider"}

SRC_EXCLUDE_DIRS = {
    ".git", ".svn", "node_modules", "target", "build", "out", "dist",
    ".idea", ".gradle", "__pycache__", "generated", "generated-sources",
}

# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------

def strip_comments_and_strings(text, keep_strings=False):
    """去掉注释（用空格填充），保留换行以维持行号对齐。

    `keep_strings=False`（默认，**结构解析**用）：连字符串字面量内容一并清空，
    避免把注释里的 `@Autowired` 示例、字符串常量里的 `"@Autowired private Foo f;"`
    当成真代码。
    `keep_strings=True`（**`@Value` 扫描**用）：只清注释、保留字符串内容——配置键
    本身就写在字符串字面量里（`@Value("${demo.timeout}")`），清空了就采不到；
    而注释已剥离，注释掉的 `@Value` 不会误报。
    """
    out = []
    i, n = 0, len(text)
    state = None  # None | 'line' | 'block' | 'str' | 'char'
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                state, i = "line", i + 2
                out.append("  ")
                continue
            if c == "/" and nxt == "*":
                state, i = "block", i + 2
                out.append("  ")
                continue
            if c == '"':
                state, i = "str", i + 1
                out.append('"')
                continue
            if c == "'":
                state, i = "char", i + 1
                out.append("'")
                continue
            out.append(c)
            i += 1
        elif state == "line":
            if c == "\n":
                state = None
                out.append("\n")
            else:
                out.append(" ")
            i += 1
        elif state == "block":
            if c == "*" and nxt == "/":
                state, i = None, i + 2
                out.append("  ")
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
        else:  # 'str' / 'char'
            quote = '"' if state == "str" else "'"
            if c == "\\":
                out.append(text[i:i + 2] if keep_strings else "  ")
                i += 2
                continue
            if c == quote:
                state = None
                out.append(quote)
            elif c == "\n":            # 未闭合，容错
                state = None
                out.append("\n")
            else:
                out.append(c if keep_strings else " ")
            i += 1
    return "".join(out)


def simple_name(type_str):
    """`com.foo.Bar<Baz>` → `Bar`；数组 / 可变参一并剥掉。"""
    t = type_str.strip().replace("...", "").replace("[]", "")
    t = re.sub(r"<.*", "", t).strip()
    return t.rsplit(".", 1)[-1]


def unwrap_container(type_str):
    """List<Foo> / Optional<Foo> / Map<String, Foo> → (Foo, True)；其余 → (T, False)。"""
    raw = simple_name(type_str)
    if raw not in CONTAINER_TYPES:
        return raw, False
    m = re.search(r"<(.+)>", type_str.strip())
    if not m:
        return raw, True
    args = [a.strip() for a in re.split(r",(?![^<]*>)", m.group(1))]
    return simple_name(args[-1]), True


# ---------------------------------------------------------------------------
# 采集：Java 源码
# ---------------------------------------------------------------------------

CLASS_RE = re.compile(
    r"^\s*(?:public|protected|private|final|abstract|static|sealed|non-sealed|\s)*"
    r"\b(class|interface|enum|record)\s+(\w+)"
)
ANNO_RE = re.compile(r"^\s*@(\w+)")
FIELD_RE = re.compile(
    r"^\s*(?:public|protected|private|final|static|transient|volatile|\s)*"
    r"([A-Za-z_][\w.]*(?:\s*<[^;=]*>)?(?:\[\])?)\s+(\w+)\s*(?:[;=]|$)"
)
METHOD_RE = re.compile(
    r"^\s*(?:public|protected|private|static|final|abstract|synchronized|default|\s)*"
    r"([A-Za-z_][\w.]*(?:\s*<[^()]*>)?(?:\[\])?)\s+(\w+)\s*\("
)
VALUE_RE = re.compile(r'@Value\s*\(\s*"\s*\$\{([^}]*)\}')
QUALIFIER_RE = re.compile(r"@(?:Qualifier|Named)\s*\(")


class JavaFile(object):
    """单个 .java 文件的解析结果。"""

    def __init__(self, path, rel):
        self.path, self.rel = path, rel
        self.types = []          # 本文件声明的类型
        self.beans = []          # @Bean 方法产出的类型
        self.injections = []     # 注入点
        self.values = []         # @Value("${key}") 占位符
        self.has_mapper_scan = False
        self.enable_config_props = set()
        # 读取失败标记：读不出来的文件**不是"已扫描且干净"**。不打这个标记的话，
        # 空 JavaFile 会被计进 java_files、findings 为 0、skipped=false —— 三者组合
        # 对调用方就是「本维度扫过 N 个文件、干净」，是最具误导性的假绿。
        self.unreadable = None


def _collect_type_decl(lines, idx, annos):
    """解析类型声明行，返回 dict 或 None。"""
    m = CLASS_RE.match(lines[idx])
    if not m:
        return None
    kind, name = m.group(1), m.group(2)
    # extends / implements 可能跨行，向后并 3 行取父类型
    tail = " ".join(lines[idx:idx + 4])
    supers = []
    for kw in ("extends", "implements"):
        mm = re.search(kw + r"\s+([^{]+)", tail)
        if mm:
            for part in re.split(r",(?![^<]*>)", mm.group(1)):
                sn = simple_name(part)
                if sn and sn not in ("", "{"):
                    supers.append(sn)
    return {
        "kind": kind, "name": name, "line": idx + 1,
        "annos": set(annos), "supers": supers,
        "is_abstract": bool(re.search(r"\babstract\b", lines[idx])),
    }


def parse_java(path, rel):
    jf = JavaFile(path, rel)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        jf.unreadable = str(e)
        return jf
    text = strip_comments_and_strings(raw)
    lines = text.split("\n")
    # @Value 的键写在字符串字面量里，须用「保留字符串」的那份扫（行号与 lines 对齐）
    lines_with_str = strip_comments_and_strings(raw, keep_strings=True).split("\n")

    if "@MapperScan" in text:
        jf.has_mapper_scan = True
    for m in re.finditer(r"@EnableConfigurationProperties\s*\(([^)]*)\)", text):
        for t in re.findall(r"([\w.]+)\s*\.class", m.group(1)):
            jf.enable_config_props.add(simple_name(t))

    annos = []             # 紧邻上方的注解缓冲
    cur_type = None        # 当前所在类型
    ctor_injected_types = defaultdict(list)   # 类型名 → final 字段类型（Lombok 构造注入）

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # ---- @Value 占位符（独占一行 / 与字段同行 / 构造参数上都可能出现）----
        # 必须先于下面的「纯注解行 continue」扫描，否则独占一行的 @Value 永远采不到
        for vm in VALUE_RE.finditer(lines_with_str[i]):
            expr = vm.group(1)
            jf.values.append({
                "key": expr.split(":", 1)[0].strip(), "has_default": ":" in expr,
                "file": rel, "line": i + 1,
            })

        # ---- 注解行（可能与声明同行，如 `@Autowired private Foo foo;`）----
        inline_annos = re.findall(r"@(\w+)", stripped)
        if ANNO_RE.match(stripped) and not re.search(
                r"\b(class|interface|enum|record)\b|[;{]\s*$", stripped):
            # 纯注解行（含跨行注解参数的首行）→ 只入缓冲，等真正的声明行来消费
            annos.extend(inline_annos)
            continue

        effective_annos = annos + inline_annos

        # ---- 类型声明 ----
        decl = _collect_type_decl(lines, i, effective_annos)
        if decl:
            decl["file"], jf_types = rel, jf.types
            jf_types.append(decl)
            cur_type = decl
            annos = []
            continue

        # ---- @Bean 方法 ----
        if "Bean" in effective_annos:
            mm = METHOD_RE.match(line)
            if mm and simple_name(mm.group(1)) not in ("return", "new"):
                jf.beans.append({
                    "type": simple_name(mm.group(1)), "method": mm.group(2),
                    "file": rel, "line": i + 1,
                })
                annos = []
                continue

        owner = cur_type["name"] if cur_type else "?"

        # ---- 字段注入（@Autowired / @Resource / @Inject）----
        fm = FIELD_RE.match(re.sub(r"@\w+\s*(\([^)]*\))?", "", line).strip()) \
            if INJECT_ANNOTATIONS & set(effective_annos) else None
        if fm is None and (INJECT_ANNOTATIONS & set(effective_annos)):
            fm = FIELD_RE.match(line)
        if fm and (INJECT_ANNOTATIONS & set(effective_annos)):
            if "(" not in line.split(fm.group(2))[0]:   # 排除方法声明
                jf.injections.append({
                    "type_raw": fm.group(1), "name": fm.group(2), "owner": owner,
                    "style": "field", "file": rel, "line": i + 1,
                    "qualified": bool(QUALIFIER_RE.search(line)) or "Resource" in effective_annos,
                })
                annos = []
                continue

        # ---- setter 注入 ----
        if INJECT_ANNOTATIONS & set(effective_annos):
            sm = re.match(r"^\s*(?:public|protected)?\s*void\s+set(\w+)\s*\(([^)]*)\)", line)
            if sm and sm.group(2).strip():
                p = sm.group(2).split(",")[0].strip()
                parts = p.replace("final ", "").split()
                if len(parts) >= 2:
                    jf.injections.append({
                        "type_raw": parts[-2], "name": parts[-1], "owner": owner,
                        "style": "setter", "file": rel, "line": i + 1,
                        "qualified": bool(QUALIFIER_RE.search(line)),
                    })
                annos = []
                continue

        # ---- Lombok 构造注入：@RequiredArgsConstructor + private final ----
        if cur_type and ("RequiredArgsConstructor" in cur_type["annos"]
                         or "AllArgsConstructor" in cur_type["annos"]):
            if re.match(r"^\s*(?:private|protected)\s+final\s+", line) and "=" not in line:
                fm2 = FIELD_RE.match(line)
                if fm2 and "(" not in line:
                    ctor_injected_types[cur_type["name"]].append({
                        "type_raw": fm2.group(1), "name": fm2.group(2),
                        "owner": cur_type["name"], "style": "lombok-ctor",
                        "file": rel, "line": i + 1,
                        "qualified": bool(QUALIFIER_RE.search(line)),
                    })

        # ---- 显式构造函数参数注入 ----
        if cur_type and cur_type["annos"] & COMPONENT_ANNOTATIONS:
            cm = re.match(r"^\s*(?:public|protected)\s+" + re.escape(cur_type["name"])
                          + r"\s*\(([^)]*)\)", line)
            if cm and cm.group(1).strip():
                for p in re.split(r",(?![^<]*>)", cm.group(1)):
                    p = p.strip()
                    if not p or "@Value" in p:
                        continue
                    parts = re.sub(r"@\w+\s*(\([^)]*\))?", "", p).replace("final ", "").split()
                    if len(parts) >= 2:
                        jf.injections.append({
                            "type_raw": parts[-2], "name": parts[-1], "owner": cur_type["name"],
                            "style": "ctor", "file": rel, "line": i + 1,
                            "qualified": bool(QUALIFIER_RE.search(p)),
                        })
        annos = []

    for lst in ctor_injected_types.values():
        jf.injections.extend(lst)
    return jf


# ---------------------------------------------------------------------------
# 采集：配置文件（yml / properties）—— 供 @Value 键存在性判定
# ---------------------------------------------------------------------------

def normalize_key(key):
    """relaxed binding：忽略 `-` / `_` / 大小写。"""
    return re.sub(r"[-_]", "", key).lower()


def parse_properties(path):
    keys = set()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue
                if "=" in line:
                    keys.add(line.split("=", 1)[0].strip())
                elif ":" in line:
                    keys.add(line.split(":", 1)[0].strip())
    except OSError:
        pass
    return keys


def parse_yaml_keys(path):
    """缩进式 YAML 的**键路径**抽取（不解析值，无需 PyYAML）。"""
    keys, stack = set(), []   # stack: [(indent, key)]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip() or line.strip().startswith("#"):
                    continue
                if line.strip() == "---":
                    stack = []
                    continue
                indent = len(line) - len(line.lstrip(" "))
                body = line.strip()
                if body.startswith("- "):        # 列表项：不作键路径
                    continue
                m = re.match(r"^([\w.\-]+)\s*:(.*)$", body)
                if not m:
                    continue
                key, rest = m.group(1), m.group(2).strip()
                while stack and stack[-1][0] >= indent:
                    stack.pop()
                path_keys = [k for _, k in stack] + [key]
                keys.add(".".join(path_keys))
                if not rest:                      # 还有下级
                    stack.append((indent, key))
    except OSError:
        pass
    return keys


def collect_config_keys(root, extra_file=None):
    keys = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SRC_EXCLUDE_DIRS]
        for fn in filenames:
            low = fn.lower()
            if not low.startswith(("application", "bootstrap")):
                continue
            full = os.path.join(dirpath, fn)
            if low.endswith((".yml", ".yaml")):
                keys |= parse_yaml_keys(full)
            elif low.endswith(".properties"):
                keys |= parse_properties(full)
    if extra_file and os.path.isfile(extra_file):
        try:
            with open(extra_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        keys.add(line.split("=", 1)[0].split(":", 1)[0].strip())
        except OSError:
            pass
    return {normalize_key(k) for k in keys}


# ---------------------------------------------------------------------------
# 索引与判定
# ---------------------------------------------------------------------------

def build_index(files):
    idx = {
        "types": {},            # 简单名 → decl
        "components": {},       # 简单名 → decl（带组件注解）
        "supers": defaultdict(list),   # 父类型/接口名 → [带注解的实现 decl]
        "beans": defaultdict(list),    # 类型名 → [@Bean 方法]
        "mapper_scan": False,
        "config_props": set(),
    }
    for jf in files:
        idx["mapper_scan"] = idx["mapper_scan"] or jf.has_mapper_scan
        idx["config_props"] |= jf.enable_config_props
        for b in jf.beans:
            idx["beans"][b["type"]].append(b)
        for t in jf.types:
            idx["types"].setdefault(t["name"], t)
            if t["annos"] & COMPONENT_ANNOTATIONS:
                idx["components"].setdefault(t["name"], t)
                for s in t["supers"]:
                    idx["supers"][s].append(t)
    return idx


def bean_candidates(t, idx):
    """返回 T 的全部 bean 来源（用于「多 bean 无 @Qualifier」判定）。

    ★ 按【声明位置】去重：同一个声明常被多条规则同时命中（如 `@ConfigurationProperties`
    类既算 component 又算 config-props、`*Mapper` 接口既算 component 又算 mapper-scan），
    那是**一个** bean 被两条规则识别，不是两个候选。不去重会把多 bean 告警刷成噪音。
    """
    out = []
    decl = idx["types"].get(t)
    if t in idx["components"]:
        out.append(("component", idx["components"][t]))
    for impl in idx["supers"].get(t, []):
        out.append(("impl", impl))
    for b in idx["beans"].get(t, []):
        out.append(("bean", b))
    if decl is not None and (decl["annos"] & {"ConfigurationProperties"}
                             or t in idx["config_props"]):
        out.append(("config-props", decl))
    if idx["mapper_scan"] and decl is not None and decl["kind"] == "interface" \
            and re.search(r"(Mapper|Dao|DAO|Repository)$", t):
        out.append(("mapper-scan", decl))

    deduped, seen = [], set()
    for kind, obj in out:
        ident = (obj.get("file"), obj.get("line"))
        if ident in seen:
            continue
        seen.add(ident)
        deduped.append((kind, obj))
    return deduped


def grep_new_usages(root, type_name, limit=6):
    """grep `new T(` 现有位置——把一次告警直接变成一次修复。"""
    hits, pat = [], re.compile(r"\bnew\s+" + re.escape(type_name) + r"\s*[(<]")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SRC_EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    body = strip_comments_and_strings(f.read())
            except OSError:
                continue
            for i, line in enumerate(body.split("\n")):
                if pat.search(line):
                    hits.append("%s:%d" % (os.path.relpath(full, root), i + 1))
                    if len(hits) >= limit:
                        return hits
    return hits


def analyze(root, files, idx, config_keys):
    findings = []

    # ---- ① / ② DI 可解析性 ----
    for jf in files:
        for inj in jf.injections:
            t, boxed = unwrap_container(inj["type_raw"])
            if not t or t in NON_BEAN_TYPES or t in AUTOCONFIGURED:
                continue
            cands = bean_candidates(t, idx)
            decl = idx["types"].get(t)

            if not cands:
                reason = KNOWN_NOT_AUTOCONFIGURED.get(t)
                if reason:
                    sev, why = "critical", "框架不自动装配：" + reason
                elif decl is not None and decl["kind"] == "class" and not decl["is_abstract"]:
                    sev, why = "critical", ("仓内已定义为具体类 %s（%s:%d）却无组件注解 / @Bean / "
                                            "@ConfigurationProperties" % (t, decl["file"], decl["line"]))
                elif decl is not None:
                    sev, why = "warn", "仓内 %s 是%s，未找到带组件注解的实现" % (
                        t, "接口" if decl["kind"] == "interface" else "抽象类")
                else:
                    sev, why = "warn", "全仓未找到 %s 的定义与 bean 来源（可能来自未扫描模块 / 外部 starter）" % t
                if boxed and sev == "critical":
                    sev, why = "warn", why + "（容器类型注入，静态无法确证）"
                item = {
                    "kind": "di-unresolvable", "severity": sev, "type": t,
                    "injection": "%s.%s" % (inj["owner"], inj["name"]),
                    "style": inj["style"], "file": inj["file"], "line": inj["line"],
                    "reason": why,
                }
                if sev == "critical":
                    usages = grep_new_usages(root, t)
                    if usages:
                        item["existing_new_usages"] = usages
                findings.append(item)
                continue

            # ---- 多 bean 无 @Qualifier ----
            if len(cands) >= 2 and not inj["qualified"] and not boxed:
                primary = any(
                    isinstance(c[1], dict) and "Primary" in c[1].get("annos", set())
                    for c in cands
                )
                if not primary:
                    findings.append({
                        "kind": "multi-bean-no-qualifier", "severity": "warn", "type": t,
                        "injection": "%s.%s" % (inj["owner"], inj["name"]),
                        "style": inj["style"], "file": inj["file"], "line": inj["line"],
                        "reason": "%s 有 %d 个候选 bean 且未 @Qualifier / @Primary → "
                                  "NoUniqueBeanDefinitionException 风险"
                                  "（Spring 会先按字段名匹配 beanName 兜底，故不判死）" % (t, len(cands)),
                        "candidates": [
                            "%s@%s:%s" % (c[0], c[1].get("file", "?"), c[1].get("line", "?"))
                            for c in cands
                        ],
                    })

    # ---- ③ @Value 键缺失 ----
    for jf in files:
        for v in jf.values:
            if v["has_default"] or not v["key"]:
                continue
            if re.search(r"[#$]\{|random\.", v["key"]):   # 嵌套/随机占位，静态不判
                continue
            if normalize_key(v["key"]) in config_keys:
                continue
            findings.append({
                "kind": "value-key-missing", "severity": "critical", "type": v["key"],
                "injection": "@Value(\"${%s}\")" % v["key"],
                "style": "value", "file": v["file"], "line": v["line"],
                "reason": "配置键 %s 无默认值，且 application*/bootstrap* 配置与配置项清单中均无该键 "
                          "→ 占位符解析失败、容器启动报 IllegalArgumentException" % v["key"],
            })
    return findings


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

_KIND_LABEL = {
    "di-unresolvable": "DI 依赖不可解析",
    "multi-bean-no-qualifier": "多 bean 无 @Qualifier",
    "value-key-missing": "@Value 键缺失",
}


def print_human(res):
    if res["skipped"]:
        print("⏭️  未扫描到后端 .java 源码 → 维度 6「DI 依赖可解析性」整维度跳过（不影响其它技术栈）")
        return
    crit = [f for f in res["findings"] if f["severity"] == "critical"]
    warn = [f for f in res["findings"] if f["severity"] == "warn"]
    print("═══ 维度 6：DI 依赖可解析性（Java/Spring 静态回检）═══")
    print("  扫描 %d 个 .java、%d 个注入点、%d 个 @Value 占位符"
          % (res["stats"]["java_files"], res["stats"]["injections"], res["stats"]["values"]))
    print("  🔴 Critical %d 项 / 🟡 Warn %d 项" % (len(crit), len(warn)))
    for group, icon in ((crit, "❌"), (warn, "⚠️")):
        for f in group:
            print("\n%s %s：%s (%s)  —— %s:%d"
                  % (icon, _KIND_LABEL[f["kind"]], f["injection"], f["type"], f["file"], f["line"]))
            print("   %s" % f["reason"])
            if f.get("existing_new_usages"):
                print("   本项目既有 %d 处均为构造自建：%s"
                      % (len(f["existing_new_usages"]), " / ".join(f["existing_new_usages"])))
                print("   建议照此改为 new %s(...)，而非 @Autowired 注入。" % f["type"])
            if f.get("candidates"):
                print("   候选：%s" % " / ".join(f["candidates"]))
    print("\n" + "─" * 60)
    if crit:
        print("🔴 %d 项 Critical——编译期无感、容器启动期必炸，须修复后再提交" % len(crit))
    elif warn:
        print("🟡 无 Critical；%d 项 Warn 需 Agent 结合跨模块上下文人工确认（不阻断）" % len(warn))
    else:
        print("✅ 全部注入点均可解析")


def git_changed_files(root, base):
    """返回 root 下发生变更的 .java 文件集合（相对 root 的路径）。

    含三类：相对 base 的已跟踪改动 + 暂存区 + **未跟踪新文件**。
    第三类不可省 —— 新建的 Java 类正是 DI 问题最高发的来源。
    git 不可用 / 非 git 仓库时返回 None，调用方退回全量（更严的一侧）。
    """
    def _run(cmd):
        try:
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None

    top = _run(["git", "rev-parse", "--show-toplevel"])
    if top is None:
        return None
    # ⚠️ **两侧都要 realpath。** `git rev-parse --show-toplevel` 返回的是**解析过软链的
    #    真实路径**，而 root 是用户传进来的原始路径。二者不一致时（code_dir 是符号链接、
    #    macOS 的 /tmp→/private/tmp、CI 里软链的 workspace、~/work→/data/work 等常见布局），
    #    下面的 relpath 会算出 `../…`，被判成「不在被检目录内」→ **全部 finding 被过滤成
    #    空、exit 0**，是彻底静默的假绿。实测踩过。
    repo_root = os.path.realpath(top.strip())
    root_real = os.path.realpath(root)

    cmds = []
    if base is not None:
        # ⚠️ 必须先验 base 是**真 ref**。直接 `git diff --name-only <base>` 时，若 base
        #    其实是个路径（如 `--base src`），git 会把它当 **pathspec** 接受、退出码 0，
        #    返回一份语义完全不同的变更集而毫无提示。`^{commit}` 强制按提交解析。
        if _run(["git", "rev-parse", "--verify", "--quiet", base + "^{commit}"]) is None:
            return False
        cmds += [["git", "diff", "-z", "--name-only", base],
                 ["git", "diff", "-z", "--name-only", "--cached", base]]
    # ⚠️ **必须带 `-z`（NUL 分隔）。** git 默认 `core.quotepath=true`，会把非 ASCII 路径
    #    输出成 C 风格转义并**加上双引号**（`"src/…/\344\270\255\346\226\207/X.java"`），
    #    于是 `endswith(".java")` 恒为 False，中文/日文等目录下的文件被**静默丢弃**——
    #    真实的 Critical 在增量模式下消失、exit 0。`-z` 一并解决含空格、含引号、
    #    甚至含换行的病态文件名。实测踩过：中文目录下的注入点被整个丢掉。
    cmds.append(["git", "ls-files", "-z", "--others", "--exclude-standard"])

    out = []
    for cmd in cmds:
        got = _run(cmd)
        if got is None:
            if cmd[1] == "diff":
                return False
            continue
        out.extend(p for p in got.split("\0") if p)

    # 子模块变更在顶层只显示为 gitlink 目录名，其内部文件不会出现在 --name-only 里。
    # 静默丢弃会让子模块内的 Critical 消失，故显式告警而非假装扫过了。
    for p in out:
        if not p.endswith(".java") and os.path.isdir(os.path.join(repo_root, p, ".git")):
            print("⚠️  检测到子模块变更 %s —— 其内部文件未纳入增量范围，请对子模块单独运行"
                  % p, file=sys.stderr)

    changed = set()
    for rel_to_repo in out:
        if not rel_to_repo.endswith(".java"):
            continue
        absolute = os.path.join(repo_root, rel_to_repo)
        try:
            rel_to_root = os.path.relpath(absolute, root_real)
        except ValueError:            # Windows 跨盘符
            continue
        # 用路径分段判「是否落在被检目录内」，而非 startswith("..")——
        # 后者会误伤名字以 `..` 开头的真实目录（如 `..mod/`）
        if rel_to_root.split(os.sep)[0] != "..":
            changed.add(os.path.normpath(rel_to_root))
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="维度 6「DI 依赖可解析性」静态回检（Java/Spring，不编译不起容器）")
    ap.add_argument("code_dir", help="待检代码目录")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--strict", action="store_true", help="Warn 也返回非零退出码（默认只有 Critical 返回 1）")
    ap.add_argument("--config-keys-file", help="额外的配置项清单（每行一个 key，用于 @Value 键存在性判定）")
    ap.add_argument("--changed-only", action="store_true",
                    help="只报告 git 变更文件里的注入点（bean 索引仍全仓解析）；供开发期前置门用")
    # default=None 而非 "HEAD"：必须能区分「用户显式传了 base」与「用了默认值」，
    # 否则 `--base HEAD` 单独使用（不带 --changed-only）会被静默忽略，
    # 且零提交仓库里无法把「默认 HEAD 不存在」降级处理（见 git_changed_files 调用处）。
    ap.add_argument("--base", default=None,
                    help="--changed-only 的对比基准 git ref（默认 HEAD）")
    args = ap.parse_args(argv)

    if args.base is not None and not args.changed_only:
        print("✗ --base 需与 --changed-only 同用", file=sys.stderr)
        return 2
    base_explicit = args.base is not None
    base = args.base or "HEAD"

    root = args.code_dir
    if not os.path.isdir(root):
        print("✗ 目录不存在：%s" % root, file=sys.stderr)
        return 2

    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SRC_EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".java"):
                full = os.path.join(dirpath, fn)
                files.append(parse_java(full, os.path.relpath(full, root)))

    if not files:
        res = {"skipped": True, "reason": "未扫描到 .java 源码（非 Java/Spring 项目）",
               "findings": [], "stats": {"java_files": 0, "injections": 0, "values": 0}}
        print(json.dumps(res, ensure_ascii=False, indent=2)) if args.json else print_human(res)
        return 0

    # ⚠️ build_index / analyze 一律吃**全量** files —— 增量模式只在拿到 findings 后
    #    按变更文件过滤。收窄索引会让「新写的注入点 + 未改动的实现类」被误判成无来源。
    idx = build_index(files)
    config_keys = collect_config_keys(root, args.config_keys_file)
    findings = analyze(root, files, idx, config_keys)

    changed_scope = None
    if args.changed_only:
        changed = git_changed_files(root, base)
        if changed is False:
            # 零提交的新仓库里 HEAD 本就不存在。这**不是**用户的错，而且此时所有 .java
            # 都是未跟踪新文件 —— 正是增量模式价值最高的场景，不该一律 exit 2 顶回去。
            # 只有用户**显式**传了无效 ref 才判入参错。
            if base_explicit:
                print("✗ git 基准无效：%s（--base 指定的 ref 不存在？）" % base, file=sys.stderr)
                return 2
            print("⚠️  仓库尚无提交（HEAD 不存在），--changed-only 降级为「仅扫未跟踪新文件」",
                  file=sys.stderr)
            changed = git_changed_files(root, None)
            if changed in (None, False):
                print("⚠️  未跟踪文件也取不到，退回全量扫描", file=sys.stderr)
                changed = None
        if changed is None:
            print("⚠️  非 git 仓库或 git 不可用，--changed-only 失效，退回全量扫描",
                  file=sys.stderr)
        else:
            changed_scope = len(changed)
            findings = [f for f in findings if os.path.normpath(f["file"]) in changed]

    findings.sort(key=lambda f: (f["severity"] != "critical", f["file"], f["line"]))

    unreadable = [{"file": f.rel, "error": f.unreadable} for f in files if f.unreadable]
    res = {
        "skipped": False,
        "findings": findings,
        # 读不出的文件单列，绝不计进 java_files（否则等于声称"扫过且干净"）
        "unreadable_files": unreadable,
        "stats": {
            "java_files": sum(1 for f in files if not f.unreadable),
            "changed_scope": changed_scope,
            "injections": sum(len(f.injections) for f in files),
            "values": sum(len(f.values) for f in files),
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "warn": sum(1 for f in findings if f["severity"] == "warn"),
        },
    }
    print(json.dumps(res, ensure_ascii=False, indent=2)) if args.json else print_human(res)

    if unreadable:
        sys.stderr.write(
            "ERROR: %d 个 .java 读取失败（权限/断链符号链接），本维度结论不可信：%s\n"
            % (len(unreadable), "、".join(u["file"] for u in unreadable[:5])))
    if res["stats"]["critical"]:
        return 1
    if args.strict and res["stats"]["warn"]:
        return 1
    # 读失败属环境错(2)，不能落到 0 —— 「读不出来」永远不等于「没有违规」
    if unreadable:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
