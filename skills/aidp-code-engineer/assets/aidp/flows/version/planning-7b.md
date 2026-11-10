# /version · 规划质量证据 — 分片 7b/10

> 本片是 `planning-7.md` Step 2.4.7 的 QR owner、证据复用与移交派单协议；派审/恢复/最终结清前必须 Read。

<!-- BODY-BELOW -->
**★ 逐产物/维度责任与证据复用**：调度单以 `artifact + content hash/revision + dimension + 必要 inputs` 唯一标识工作，不以「跑了某个 Agent」代替覆盖。

| 工作 | owner | 核验范围 |
|---|---|---|
| 单族内容质量、边界、格式、单族引用密度 | `skill:<skill>`；该维度已移交则 `handoff:<skill>` | SKILL 原 checklist；一项只指定一个 owner |
| 跨族语义/引用依赖、版本一致性、原型到需求/设计贯通 | `version-auditor` | A–H 中跨族部分，消费单族证据，不再独立复审相同单族维度 |
| PRD 原始条目 → 需求/设计/计划/用例反向覆盖 | `version-auditor` | 必须直接读 PRD 原文，表 D/PRD 行对账表仅辅助，不能证明全集完整 |

新增或修改产物必须补齐其必要维度；旧维度只有 hash、必要 inputs、判据版本/参数均一致且证据可读时才复用。跨族廉价引用/编号/索引每次全局跑；独立跨族审查仍必须派，不能仅因单族缓存命中而跳过。repair 的语义重查范围按目标及相关引用依赖确定，其余附可信证据与 owner；无证据按 missing 补审，不能臆造 pass。

调用层保存生成 SKILL 或移交审查的**真实返回 JSON**（现有 `overall/dims[{id,verdict}]/report_path`，不得从总 pass 补写未返回的维度）后，通过已有落地门记录/查询。每个 artifact、每个维度分别执行；必要 inputs 包括该维度实际读取的上游文件、SKILL checklist 文件、适用的参数记录（目录输入包括成员增删）。索引只消费 handoff 协议，不把清块产生的字节变化作为内容质量变化。

```bash
python3 {{AIDP_HOME}}/scripts/check_version_audit_landed.py --root . --version {version} --qr-action get --artifact <产物文件> --dimension <skill:QR-NN> --input <必要输入> --param <判据版本及实际参数> --json
python3 {{AIDP_HOME}}/scripts/check_version_audit_landed.py --root . --version {version} --qr-action put --artifact <产物文件> --dimension <skill:QR-NN> --input <必要输入> --param <判据版本及实际参数> --result <真实结果.json> --fingerprint <派单前get返回指纹> --owner <skill:名称或handoff:名称> --producer <生成者ID> --reviewer <审查者ID> --json
```

`--input` / `--param` 可重复；派单前保存 get 的 `fingerprint`，put 必须传原值，审查期间产物/input 变化即拒绝登记，不能用审完后的新指纹冒充旧审查。结果 JSON/报告按轮次保存，不覆盖被旧证据引用的文件。未命中输出 `missing`，新证据 `redone`，复用 `reused` 并返回 owner/证据 hash。缓存落 `memory/{version}/.planning-qr/`，独立移交 reviewer 必须与 producer 不同。原 SKILL 没有逐维结构化返回时不伪造缓存，保留真实报告并补派需要的审查；调用层不修改依赖 SKILL 正文。

**★ 移交维度并行审计**（`qr_level ≠ full` 时；`--fast` 不派、清单保留，Step 2.5.0 带 `--fast`）：先用原 `parse-handoff --expect-level` 校验，再按未命中证据的 artifact×dimension 组装派单。允许将多份小清单合并给一个独立 `{{AIDP_HOME}}/agents/qr-handoff-auditor.md` 实例，按 SKILL/维度分别返回结果；可与 version-auditor **同一条消息**并行派发。**不再规定每份清单必有一个 Agent**，但生成者不能兼任自己的独立审查者。

`skill_params` 与 `upstream_dirs` 读 `memory/{version}/.planning-skill-params.json`，dev-manual-testcase 用实际规模入参、计划引用按回填后的 `required` 审；其它 SKILL 同样消费实际入参。两类审计合并处置，任一 block 整体 block；只回调失败目标与失效维度，不能为一个未结维度重跑四族。

主流程逐维登记证据后，用原门的 settle 动作消费依赖协议并清块：

```bash
python3 {{AIDP_HOME}}/scripts/check_version_audit_landed.py --root . --version {version} --qr-action settle --index <该00_索引.md> --skill <skill> --expect-level {qr_level} --aidp-home {{AIDP_HOME}} --json
```

任何 artifact×移交维度缺可信证据，保留清单并失败；全部可信才调用原 `qr_orchestration.py handoff --qr-level full --write`。清块后内容/input/报告变更仍判 `qr-evidence-stale`，不能仅凭块已消失过门。审计员自己不清，`--fast` 欠账在最终发布门仍须结清。
