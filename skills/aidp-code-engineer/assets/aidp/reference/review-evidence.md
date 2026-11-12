# 任务审查与等价证据

仅在 review、full-cvl 或 equivalent-evidence 已获授权时读取；日常 light 实现不预加载。

## 审查与报告

`review` 分支读 `agents/reviewer.md`，只读核本轮 diff 与验收标准，报告自动写上下文目录；不生成 unit-scope、不顺带 CVL/文档。`full-cvl` 另获授权时按 `/sprint-test` Step 2 做一次 verify-only，review 消费这次证据及差量发现，不额外叠完整轮。独立审查保留 schema、kind=code-review、`execution_context=entry_context.evidence_identity(ctx)`、覆盖当前write_set的具体文件→SHA256 inputs映射、reviewer/checks/findings与证据。每项检查保留kind/status及非空evidence路径数组；未核验/FAIL不填PASS。只读可结束并保留FAIL；Minor/Suggestion纯改进有reason/evidence可accepted，错误不得借此放行。

同时有 related-test+review 且本轮真实质量检查完成时，才用既有 `test_ledger.py record-review` 绑定 scope/hash、全部 run_ids 和真实报告；review-only 使用 `--review-evidence` 完成，不依赖测试账本。所有错误性发现保留原等级与状态；改进建议可附不修原因，不能为通过而删发现或把工具失败转 BUG。

## 差量与等价证据

review已授权且有审查基线才review-delta，可信零diff复用；变化只补失效项。真实只分析/只修改/skip受限返回，不冒充完整开发通过。等价证据仅在equivalent-evidence显式授权下走entry_context equivalent，传原original-run-id、env-id、review-evidence及适用ledger-root；仅脚本支持的原TOOL_ERROR且实际exit0/当前输入一致情形可用。check/complete消费独立equivalent-evidence JSON，保留原失败，业务FAIL不替代。
