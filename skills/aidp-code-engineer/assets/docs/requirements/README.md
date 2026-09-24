# docs/requirements/ — 需求文档

> **隔离级别**：版本级（不按用户隔离，团队共享）

> ★ **约定 22 攒批级联产物（受 `check_cascade_landing.py` 硬门约束）**：
> `{version}/研发需求/_开发期需求增量.md`（约定 22 族增量册·需求，append-only，收口即删；与 `01_研发需求.md` 同目录；`_` 起头 → 不占 `NN_` 序号、不进 `00_索引.md`、SKILL 命名门豁免）。
> 详规单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`。

## 目录结构

```
docs/requirements/
├── PRD-{项目名}.md                       # 项目级 PRD（兜底；版本级"产品提供"目录为空时使用）
└── {version}/                            # 版本级
    ├── README.md                         # 本版本需求总览
    ├── 产品提供/                          # ★ 输入：产品交付的原始 PRD（每版独立，可多文件多系统）
    │   ├── PRD-XX系统-V0.1.md
    │   └── PRD-YY系统-V0.1.md
    └── 研发需求/                          # ★ 输出：/sprint-requirements 生成的研发版需求
        ├── 00_索引.md                    # ★ 恒有：专职索引（文件清单 + 每文件生成时间 + 主/补充标识，约定 14/15）
        ├── 01_研发需求.md                # 单系统：内容主文档
        │   或（多系统，Claude 智能判断）
        ├── 01_XX系统.md
        └── 02_YY系统.md
```

## 文件说明

| 路径 | 内容 | 来源 |
|------|------|------|
| `PRD-{项目名}.md` | 项目总体 PRD（跨版本稳定） | 产品经理手工放置（兜底） |
| `{version}/产品提供/*.md` | 该版本由产品团队交付的原始 PRD | 产品经理手工放置（★ 推荐） |
| `{version}/研发需求/00_索引.md` + `01_研发需求.md`（多系统 `01_<系统>.md`/`02_<系统>.md`）| 该版本研发视角的需求（融合 + 冲突消解 + 拆分；目录恒有专职索引） | `/sprint-requirements` 生成 |

## 工作流程

```
产品交付  →  docs/requirements/{version}/产品提供/*.md
                         ↓
                  /sprint-requirements
                         ↓
                  ux-logic-extractor 模式 B：
                  - 多源融合
                  - 冲突识别
                  - 不清晰标注（阻塞下一步）
                  - 过度内容裁剪
                         ↓
研发使用  →  docs/requirements/{version}/研发需求/00_索引.md + 01_研发需求.md（或多系统拆分）
```

## 结构与多系统拆分规则（约定 15）

- **目录恒有专职 `00_索引.md`**（文件清单 + 每文件生成时间 + 主/补充标识），内容文档从 `01_` 起
- **single（默认）**：`00_索引.md` + `01_研发需求.md`
- **单系统但规模超阈**：按业务模块拆 `00_索引.md` + `01_<模块>.md` / `02_<模块>.md` …
  ⚠️ **拆分触发阈值以 `ux-logic-extractor` SKILL 为单一信源**，此处不另立数值。
- **multi（多系统）**：按系统拆 `00_索引.md` + `01_<系统A>.md` / `02_<系统B>.md`（Claude 智能判断）

详见 [`../init/02_迭代输入指导.md`](../init/02_迭代输入指导.md) §10.4。

## 兜底与多源

- `产品提供/` 为空 → `/sprint-requirements` 回退读取项目级 `PRD-{项目名}.md`
- `产品提供/` 含多份 PRD → ux-logic-extractor 模式 B 自动融合 + 标冲突

## 相关命令

- `/sprint-requirements` — 生成研发需求文档（输入：`产品提供/` 或 `PRD-*.md`）
- `/version V0.1.0 "M1 MVP"` — 串联调用 `/sprint-requirements`

## 相关文档

- [`../init/02_迭代输入指导.md`](../init/02_迭代输入指导.md) — 迭代输入说明与约定 15 拆分规则（§10.4）
- [`../init/06_版本与用户目录约定.md`](../init/06_版本与用户目录约定.md) — 路径规则
- [`../../{{AIDP_HOME}}/commands/sprint-requirements.md`](../../{{AIDP_HOME}}/commands/sprint-requirements.md) — 命令详细执行步骤
