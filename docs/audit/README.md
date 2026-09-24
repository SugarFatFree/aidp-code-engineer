# 版本规划产物审计报告目录

>  两类写入者：**版本规划产物审计**由 `/version` Step 2.4.7 写入，单一信源 `{{AIDP_HOME}}/agents/version-auditor.md`；**范式合规检查**由 `aidp-compliance` Agent 写入，单一信源 `{{AIDP_HOME}}/agents/aidp-compliance.md`。

## 目录结构

```
docs/audit/
├── README.md                              # 本文件
├── 合规检查-{YYYYMMDD}.md                  # 范式合规检查报告（aidp-compliance；仅当存在 ERROR 或 ≥5 个 WARN 时写盘）
└── {version}/                             # 按版本号隔离
    ├── version-output-audit-YYYY-MM-DD.md           # fresh 模式审计报告
    ├── version-output-audit-补丁-NN.md              # 补充模式（B-2）审计报告，NN 与同轮 NN_<业务主题>.md 增量共用编号
    ├── version-output-audit-{version}_build{N}.md   # /sprint-autopilot Phase 3.3 build 终审（强制仪式，命名必须带 build——
    │                                                #   不带 build 时本终审可被上游遗留文件静默满足）
    ├── 发布欠账.md                                   # 发布流程未尽事项登记（补跑命令 `/version {version} --finalize-docs`）
    └── 全量设计差异-YYYY-MM-DD.md                    # 全量详细设计重算守恒未过时的差集报告
```

## 报告生成时机

- **fresh 模式**：`/version V0.X.0` 在 Step 2.4.6 完成后自动触发 Step 2.4.7，调用独立子 Agent `{{AIDP_HOME}}/agents/version-auditor.md`
- **补充模式（B-2）**：每次 `/version V0.X.0`（PRD/原型已变）执行补充流程末段同样触发审计

## 报告内容（8 项审计）

| 项 | 名称 | 关注点 |
|----|------|--------|
| **A** | 存在性 | 4 类产物文件齐全 + 补充模式额外项 |
| **B** | 边界 | 4 类产物互不越界 |
| **C** | 覆盖完整性 | PRD 100% 映射到 4 类产物（含 C-4 PRD 行级原子条目→研发需求、C-5 研发需求字段→详细设计 反向覆盖）|
| **D** | 增量一致性 | 仅增量版本：与 prev_version + code/ 已有事实一致 |
| **E** | 引用链 | 100% 引用密度（4 行 / 9 列 / 5 行强制结构） |
| **F** | 原型覆盖度 ★ Critical 硬门 | 原型 `code/` 全部元素 + 操作逻辑 100% 被研发需求 + 详细设计覆盖（约定 4）；无原型 → N/A |
| **G** | 语义变更派生完整性 ★ Critical 硬门 | 语义/口径/范围/单位/默认值变更的派生展示物（提示文案/表头/图例/空态等）三层贯通（约定 22 第三类触发）；无语义变更 → N/A |
| **H** | 跨版本需求作废完整性 | 本版推翻历史版本已生效需求时逐条清算（约定 34）；无语义反转 → N/A |

## 阻塞处置

- 报告 `overall: pass` → `/version` 继续 Step 2.5
- 报告 `overall: warn` → 继续 + Step 2.8 报告追加警告区块
- 报告 `overall: block` → `AskUserQuestion` 三选一（自动按 fix_actions 回调 SKILL / 用户手工 / 强制忽略）

详见 `{{AIDP_HOME}}/agents/version-auditor.md` 第四节「审计报告输出」与第五节「与命令端的交互协议」。

---

*基于 AIDP 范式*
