# {{AIDP_HOME}}/templates/ — 模板与骨架

本目录放**待填充的骨架**，不放规则本身。规则在 `{{AIDP_HOME}}/rules/`（路径限定）与
`{{AIDP_HOME}}/reference/`（查阅型分片）。

| 子目录 / 文件 | 用途 | 谁来消费 |
|---|---|---|
| `reports/` | AI 报告 HTML SPA 骨架（AI执行报告 / AI测试报告 / 版本测试报告 / AI数据清理）+ README | `emit-report.py` 渲染时取用 |
| `deployment/` | 部署骨架（`部署流程.md` / `SQL执行台账.md`） | `/sprint-dev` Step X.8 检测到需要时复制填充 |
| `cicd/` | CICD 流水线定义起步模板：`github-actions/deploy.yml`（默认）、`gitlab-ci/.gitlab-ci.yml`、`jenkins/Jenkinsfile`；三者遵守同一组约定（随提交触发、按 commit 可查、部署完成即结束） | 下游按 `memory/aidp-config.yaml` 的 `cicd.provider` 复制对应模板到平台约定位置，并登记 `cicd.pipelines`（约定 31.5） |
| `optional-rules/` | **按需安装规则的权威模板位** | 由各自的 `--install-rule` 装到 `{{AIDP_HOME}}/rules/` |
| `_开发期族增量.md` | 约定 22 四族增量册的空骨架 | 各族首次记增量时复制到对应族目录 |

## ⚠️ `optional-rules/` 是权威源，`{{AIDP_HOME}}/rules/` 下装的那份是副本

可选规则（如 WebMCP）默认**不在** `{{AIDP_HOME}}/rules/` —— 那里的加载是路径触发的，
只要编辑的文件命中 `paths:` 整份就进上下文，而绝大多数项目根本不启用这些能力，
读完的唯一结论是「本项目不适用」。故它们住在这里，启用后才安装过去。

**改动一律改这里**。装到 `{{AIDP_HOME}}/rules/` 的是副本：改了无法回流、下次刷新被覆盖。
安装位由 `scaffold.py::refresh_optional_rules` 随升级刷新（只刷已安装的、
下游手改过的只告警不覆盖），漏装会被对应的 `--detect` 判成 `rule-not-installed` ERROR。

## 维护边界（约定 16）

本目录是脚手架契约，随 `aidp-code-engineer` 下发/升级同步 —— 下游不应直接手改
（改后无法回流、下次升级被覆盖）。需要项目特化，用嵌套 `code/{子项目}/AGENTS.md`（Claude Code 下为 `CLAUDE.md`）。
