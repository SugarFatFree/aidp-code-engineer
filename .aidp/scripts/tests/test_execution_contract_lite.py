#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精简执行契约 ↔ 权威枚举 的逐项对账。

## 为什么这道门必须存在

`auto-test-runner/references/execution-contract-lite.md` 是给**执行子 Agent** 读的那一份
（子 Agent 拿不到 Skill 工具，只能 `Read`；派四份全文 = 一轮 5 个 Agent 4× 重复加载）。
它为了「一份读完就能干活」，把 `status` / `block_reason` / `execution_mode` / `mechanism` /
`entry_kind` 五组枚举**抄了一遍** —— 这是本仓库最高频的缺陷形态：**同一判据两份实现**。

该文件自己写明「本文件不是判据信源，枚举以 `scripts/check_result.py` 常量为准」，
并点名由本测试逐枚举比对。⛔ 没有这道门，那句话就只是一句散文承诺：
**漏同步时不会有任何东西出声**，而失效方向是**假绿** —— 执行方照精简契约写出一个
校验器眼里合法、但语义已经偏了的值（实测形态：`mechanism` 少登记 `app-mcp` 时，
跨端应用自有 MCP 的用例被填成 `webmcp`，即「测试驱动用了 MCP」与「应用提供了 MCP 能力」
两条轴的混淆，而 `check_result.py` 不报错）。

## 三个信源，两两必须一致

  · **`scripts/check_result.py` 的常量** —— 校验器实际认什么（**权威**）
  · **`assets/result-schema.json` 的 `$field_notes`** —— 执行方照着写 result 的依据
  · **`references/execution-contract-lite.md`** —— 子 Agent 实际读到的那一份

⚠️ 三者都要比，⛔ 不能只比「精简契约 vs 校验器」：schema 是**执行方的依据**，
它漏一个值的后果与精简契约漏一个值完全相同（都让那个值写不出来）。

## 采集量自证（⛔ 别把「没解析到」读成「一致」）

每个用例先断言**解析到的枚举值个数 > 0**。本测试的失效形态与通过同形：
正则认不出文档里的写法 ⇒ 抽到空集合 ⇒ `set() == set()` ⇒ **绿**。
这正是本轮上游同步要立的那条规矩（「扫到 0 个东西，和扫完一切都合格，退出码一模一样」），
故在这里就地落实，⛔ 不要把 `assertTrue(parsed)` 删掉当成冗余。
"""
import importlib.util
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AIDP = os.path.dirname(HERE)                      # .aidp/scripts
SKILL = os.path.join(os.path.dirname(AIDP), "skills", "auto-test-runner")
LITE = os.path.join(SKILL, "references", "execution-contract-lite.md")
SCHEMA = os.path.join(SKILL, "assets", "result-schema.json")
CHECKER = os.path.join(SKILL, "scripts", "check_result.py")

# 行内反引号枚举值：`dom` / `app-mcp` / `webmcp-driver-too-old`
_TOKEN = re.compile(r"`([a-z][a-z0-9-]*)`")


def _load_checker():
    """按路径加载 check_result.py（它不在 sys.path 上，且与命令端同名脚本无关）。"""
    spec = importlib.util.spec_from_file_location("_atr_check_result", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lite_text():
    with open(LITE, encoding="utf-8") as fh:
        return fh.read()


def _schema_note(field):
    with open(SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)["$field_notes"][field]


def _tokens_after(text, marker, stop=None, limit=1200):
    """取 `marker` 之后一段窗口内的反引号 token 集合。

    ⚠️ 窗口而不是整篇：整篇扫会把别处顺带提到的枚举值（如红线段里的 `block`）
    混进来，让比对恒过 —— 那是**假绿**方向。
    """
    i = text.find(marker)
    if i < 0:
        return set()
    seg = text[i + len(marker): i + len(marker) + limit]
    if stop:
        j = seg.find(stop)
        if j >= 0:
            seg = seg[:j]
    return set(_TOKEN.findall(seg))


class TestExecutionContractLite(unittest.TestCase):
    """精简契约抄下来的五组枚举，必须与校验器常量 / schema 说明逐项相同。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_checker()
        cls.lite = _lite_text()

    def test_lite_file_exists_and_declares_its_own_source(self):
        """精简契约必须自述「不是判据信源」并指到本测试 —— 否则它会被当成权威抄走。"""
        self.assertIn("本文件不是判据信源", self.lite)
        self.assertIn("test_execution_contract_lite.py", self.lite,
                      "精简契约必须点名这道回检；指针丢了，下一个人就不知道改完要跑什么")

    def test_status_enum(self):
        lite = _tokens_after(self.lite, "## 三、四态口径", "`block_reason` 枚举")
        parsed = lite & {"pass", "fail", "block", "na"}
        self.assertTrue(parsed, "采集量为 0：精简契约的四态表没解析到任何值")
        self.assertEqual(self.mod.STATUS_ENUM, parsed,
                         "精简契约的 status 四态与 check_result.STATUS_ENUM 不一致")

    def test_block_reason_enum(self):
        lite = _tokens_after(self.lite, "`block_reason` 枚举", "## 四、")
        # 窗口里混有正文词（precondition_probe / status 等），取与并集的交集后比对全集
        parsed = {t for t in lite if "-" in t}
        self.assertTrue(parsed, "采集量为 0：精简契约的 block_reason 枚举没解析到任何值")
        self.assertEqual(self.mod.BLOCK_REASON_ENUM, parsed,
                         "精简契约的 block_reason 枚举与 check_result.BLOCK_REASON_ENUM 不一致")

    def test_entry_kind_enum(self):
        lite = _tokens_after(self.lite, "`entry_kind`", "`execution_mode`")
        parsed = lite & self.mod.ENTRY_KIND_ENUM
        self.assertTrue(parsed, "采集量为 0：精简契约没解析到 entry_kind 取值")
        self.assertEqual(self.mod.ENTRY_KIND_ENUM, parsed,
                         "精简契约的 entry_kind 取值与 check_result.ENTRY_KIND_ENUM 不一致")

    def test_mechanism_enum_three_way(self):
        """★ 三方对账：校验器常量 ⟷ 精简契约 ⟷ schema 字段说明。

        这一组是实测踩过的那一处：schema 少登记 `app-mcp` 时校验器与精简契约都没错，
        而执行方照 schema 写，`app-mcp` 这个机制**写不出来**。
        """
        auth = self.mod.MECHANISM_ENUM
        lite = _tokens_after(self.lite, "`mechanism` ∈", "耗时来源")
        lite_parsed = lite & auth
        self.assertTrue(lite_parsed, "采集量为 0：精简契约没解析到 mechanism 取值")
        self.assertEqual(auth, lite_parsed,
                         "精简契约的 mechanism 取值与 check_result.MECHANISM_ENUM 不一致")

        note = _schema_note("mechanism")
        schema_parsed = set(re.findall(r"`([a-z][a-z0-9-]*)`\(", note)) & auth
        self.assertTrue(schema_parsed, "采集量为 0：schema 的 mechanism 说明没解析到枚举值")
        self.assertEqual(auth, schema_parsed,
                         "schema `$field_notes.mechanism` 的枚举与 check_result.MECHANISM_ENUM "
                         "不一致；执行方照 schema 写 result，少登记的值就填不出来")

    def test_execution_mode_enum_three_way(self):
        """`execution_mode` 的全集只在 schema 与精简契约里，校验器只持「须有证据」的子集。"""
        lite = _tokens_after(self.lite, "`execution_mode` ∈", "`evidence[]`")
        lite_parsed = {t for t in lite if t in {"direct", "verified", "self-heal"}}
        self.assertTrue(lite_parsed, "采集量为 0：精简契约没解析到 execution_mode 取值")
        self.assertEqual({"direct", "verified", "self-heal"}, lite_parsed)
        # 子集关系：须有证据的模式必须都在全集内，⛔ 不能出现只有校验器认的第四种模式
        self.assertTrue(self.mod.EVIDENCE_REQUIRED_MODES <= lite_parsed,
                        "check_result.EVIDENCE_REQUIRED_MODES 里有精简契约没登记的模式")
        note = _schema_note("execution_mode")
        self.assertTrue(all(m in note for m in lite_parsed),
                        "schema 的 execution_mode 说明缺了精简契约里的某个模式")

    def test_required_fields_are_all_known_to_schema(self):
        """精简契约列的「必填」字段，必须都是 schema 的顶层字段 —— 否则是凭空要求。"""
        seg = _tokens_after(self.lite, "## 四、产物契约", "- `entry_kind`", limit=900)
        with open(SCHEMA, encoding="utf-8") as fh:
            top = {k for k in json.load(fh) if not k.startswith("$")}
        required = {t for t in seg if "_" in t or t in top}
        self.assertTrue(required, "采集量为 0：精简契约的必填字段清单没解析到任何字段")
        unknown = sorted(required - top)
        self.assertEqual([], unknown,
                         f"精简契约要求的必填字段不在 result-schema.json 顶层：{unknown}")


class TestImplementationKindEnum(unittest.TestCase):
    """`implementation_kind` 的**声明侧**与**结果侧**必须同一套枚举。

    ## 为什么单独一组

    其余枚举的三方对账都在 SKILL 内部（精简契约 / schema / 校验器）。这一组不同：
    「应用自有 MCP 的实现形态」是**跨层**契约 —— 项目在 PRD / 设计里声明 `app-native`，
    执行方照抄进结果 JSON；校验器若不认这个值就判 Critical。

    实测踩过：声明侧四处（`check_client_mcp.py::IMPLEMENTATIONS`、可选规则模板、
    设计 Agent 指令）都写 `app-native`，而结果侧 `check_result.py` 只认 `app-service`。
    于是非 Web 项目**两条路都是错的**：如实写 `app-native` 被假红；为过门改写成
    `app-service` 又与自己的声明不一致 —— 而"改成能过门的值"在结果文件里看不出来。
    """

    #: 声明侧 —— 这几个文件共同定义「项目可以声明什么」
    #: ⚠️ `AIDP` 已是 `.aidp/scripts`，声明侧在 `.aidp/{templates,agents}` 下。
    AIDP_HOME = os.path.dirname(AIDP)
    DECLARATION_SOURCES = (
        os.path.join(AIDP, "check_client_mcp.py"),
        os.path.join(AIDP_HOME, "templates", "optional-rules", "client-mcp.md"),
        os.path.join(AIDP_HOME, "agents", "frontend.md"),
    )

    def test_declared_and_result_enum_agree(self):
        checker = _load_checker()
        # 结果侧：非 Web 端允许的取值（`web` 走 webmcp，不在此列）
        result_kinds = set()
        for client in ("miniprogram", "mobile", "desktop"):
            result_kinds |= set(checker.VALID_IMPLEMENTATION_KIND[client])
        self.assertTrue(result_kinds, "采集量为 0：check_result 没给出非 Web 端的实现形态集合")

        declared = set()
        for path in self.DECLARATION_SOURCES:
            self.assertTrue(os.path.isfile(path), f"声明侧文件不存在：{path}")
            with open(path, encoding="utf-8") as fh:
                declared |= set(re.findall(r"`(app-[a-z]+|bridge|webmcp|none)`", fh.read()))
        declared &= {"app-native", "app-service", "bridge"}
        self.assertTrue(declared, "采集量为 0：声明侧没解析到任何实现形态取值")

        self.assertEqual(result_kinds, declared,
                         "声明侧与结果侧的实现形态枚举不一致："
                         f"结果侧={sorted(result_kinds)} 声明侧={sorted(declared)}。"
                         "非 Web 项目如实登记声明值会被判 Critical 假红")


if __name__ == "__main__":
    unittest.main(verbosity=2)
