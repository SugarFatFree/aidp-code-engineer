# 运行根去嵌套设计（`.claude/aidp` → `.claude`、`.agents/aidp` → `.agents`）

> 状态：**设计定稿、未实施**。实施前请先读完「为什么不能直接改常量」一节。
> 起因：下游反馈「脚手架初始化后 `.agents/aidp` 里散落着 AIDP 全部文件，`rules/` 放那儿没有任何东西会读」。

## 1. 目标形态（对齐既有实践）

参照项目 `.claude/` 是**平铺**的，没有中间层：

```
.claude/
├── agents/ commands/ flows/ hooks/ plugins/ reference/ rules/ scripts/ skills/ templates/
├── CLAUDE.md                （项目记忆）
├── settings.json            （Claude Code 自己的）
├── settings.local.json      （个人配置·gitignore）
└── worktrees/               （git 工作树容器）
```

且 `.claude/commands/sprint-dev.md` **就是命令正文**，不是适配壳。

目标：`RUNTIME_HOME = {"claude": ".claude", "shared": ".agents"}`，契约直接落在运行根下。

## 2. 顺带的简化：Claude 侧适配层可以整个拿掉

现状是两层——`.claude/aidp/commands/` 放契约真源，`agent_sync.py` 再把它们 link 成 `.claude/commands/`。
降一层之后两者重合，**Claude 侧不再需要生成命令 / SKILL / 插件入口**。
Codex / DeepSeek Harness 不原生读 `.agents/`，它们的 `.codex/skills/aidp/`、`.dsh/commands/` 适配照旧生成。

## 3. ⛔ 为什么不能直接改常量

运行包现在是**整目录托管**：`runtime_layout.render_runtime` 在临时目录 stage 出完整树，
再 `os.replace` **整个覆盖**运行根。成立的前提是「这个目录整个是脚手架的」。

降一层之后前提消失，运行根里还住着**别人的东西**：

| 落点 | 属主 | 直接改常量的后果 |
|------|------|-----------------|
| `settings.json` / `settings.local.json` | Claude Code / 个人 | 整树替换时被删 |
| `worktrees/` | git | 被删；且体积可能是 GB 级，不该进 stage |
| `CLAUDE.md` | 项目记忆 | 被删 |
| `skills/<项目自有>` | 项目 | 被删（参照项目 16 个 skill 里多数是项目自有） |
| `commands/<项目自有>` | 项目 | 被删（参照项目 21 个命令里有非 AIDP 的） |

现有的用户文件保护 `runtime_layout._user_owned_path` 是**白名单**，只认
`USER_FILLABLE_CONTRACTS`、`reference/`、`skills/custom/` —— 上面这些一个都不在名单里。
**所以直接改常量 = 第一次 upgrade 就抹掉用户数据。**

## 4. 设计：从「整目录托管」改为「文件清单托管」

1. `.aidp-runtime.json` 已经登记了 `files`（每个文件的 sha256 + mode）。把它升格为**唯一的所有权边界**。
2. 安装 = 写/刷新清单内的文件 → 删除「上一版清单里有、本版没有」的文件 → **其余一律不枚举、不触碰**。
3. 原子性从「整树 `os.replace`」降级为「逐文件 `os.replace` + 回滚日志」。
   `_NativeInstallJournal` 已具备记录与回滚能力，复用即可。
4. 运行根下硬性禁写名单（`settings*.json`、`worktrees/`、项目记忆文件）：命中即 raise，
   防止未来某次改动又把边界放宽回去。
5. `tree_digest` / `_runtime_modified` / `validate_runtime` 的作用域同步收窄到清单内。

**副作用（正向）**：脚手架 skill 装在 `skills/aidp-code-engineer/`，因为不在清单里，天然不被触碰——
现有的 `RUNTIME_EXCLUDES` 兜底可以保留但不再是唯一依赖。

## 5. 迁移

`.claude/aidp/` → `.claude/`（以及 `.agents/` 同理）复用既有的 `.aidp/` → `.claude/aidp/` 迁移路径：
检出旧运行包 → 完整备份 → 渲染新形态 → 校验通过后删旧目录；任一步失败保留备份并写迁移失败证据。

## 6. 工作量与风险

- 硬编码运行根的非测试文件：**26 份**（多数地方本来就走 `{{AIDP_HOME}}` 令牌，不是瓶颈）。
- 测试里写死运行根路径的断言：**344 处**，集中在 `test_scaffold_modes.py`(140) 与 `test_runtime_layout.py`(124)。
  其中 `test_runtime_layout.py` 有相当一部分直接断言**整树替换语义**，需要真改而非改路径。
- 风险等级：**本轮所有任务里最高**——改的是安装事务的核心，失败模式是删用户数据。
  故必须单独一次改动、单独跑全量，⛔ 不与其它修复混在同一批提交里。
