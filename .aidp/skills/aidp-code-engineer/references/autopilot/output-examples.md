# /sprint-autopilot 输出示例（参考 — 执行时无需载入）

> 本文件是 `/sprint-autopilot` 各场景的**终端输出示例**，纯说明用途、**命令执行时不需要读**——仅当你想了解"某场景下命令会打印什么样子"时按需查阅。命令主文档只留一行指针，避免这些纯举例块常驻上下文（约定：上下文管理策略 #3 文档瘦身）。

## 场景 1：PRD 无变化（/loop 包装内调用）

```
🔍 /sprint-autopilot 检查 PRD baseline
   PRD 目录：docs/requirements/V0.1.0/产品提供/（4 份 .md）
   baseline commit: a1b2c3d
   当前 commit:    a1b2c3d
   工作区改动:     无

✅ 无 PRD 变化，未触发执行（baseline=a1b2c3d）
   下次 /loop 唤起时再查（约 10 分钟后）
```

## 场景 2：PRD 有更新（触发执行主流程 Phase 3）

```
🚀 /sprint-autopilot 启动（--full-auto 模式）
   触发原因：PRD 目录有新 commit（baseline=a1b2c3d → 当前=e5f6g7h）

Phase 0：前置检查
  ✅ 里程碑通知：notify 渠道可用（feishu）
  ✅ PRD 目录：docs/requirements/V0.1.0/产品提供/（4 份 .md）
  ✅ PRD autopilot_decisions：8 段齐全（含 deployment）
  ✅ git status 干净 | 分支：feature/autopilot-V0.1.0

Phase 3.1 规划（/version）
  [里程碑通知 #1 已发：规划开始]
  ✅ /version V0.1.0 完成（3 Sprint）
  [里程碑通知 #1b 已发：规划完成，将执行 3 个 Sprint]

Phase 3.2 开发（/sprint-batch）
  [里程碑通知 #1c 已发：开发开始，共 3 个 Sprint]
  ✅ Sprint-001 关闭 [里程碑通知 #2 已发]
  ✅ Sprint-002 关闭 [里程碑通知 #2 已发]
  ✅ Sprint-003 关闭 [里程碑通知 #2 已发]
  ✅ 部署完成（cloud / https://uat.example.com）→ baseline last_deployed_at 已写
  [里程碑通知 #1d 已发：部署完成-代码已推送 + 提示并行挂 /loop 5m /sprint-aiauto-test]
  ✅ version-auditor: 八项全通过（A–H）

Phase 3.4 完成通知 + 收尾
  ✅ AI 执行报告（结果 HTML）：docs/reports/V0.1.0/AI执行报告/index.html（Build1001 子页 + data/V0.1.0_build1001.js 已注册到两页）
  ✅ AI 执行计划（plan.html 计划页，读 data 计划态）：docs/reports/V0.1.0/AI执行报告/plan.html#/build/V0.1.0_build1001
  [里程碑通知 #3 已发：AI 执行报告 + 报告路径链接]

✨ /sprint-autopilot 完成
   baseline 已更新：e5f6g7h
   分支：feature/autopilot-V0.1.0
   PR：未自动创建（按约定，请手动 gh pr create）
📌 外层 /loop 将在约 10 分钟后再次唤起命令继续监听
```

## 场景 3：首次运行 + PRD 缺 autopilot_decisions（Phase 0.6 一次性收集）

```
🚀 /sprint-autopilot 启动
   ⚠️ PRD 缺 autopilot_decisions 段，进入一次性决策收集

Phase 0.6：一次性收集（避免执行主流程 Phase 2/3 中途阻塞）

  [批 1] 开发决策核心（4 题）
    Q1 视觉基准？ → prototype-only（用户选）
    Q2 缓存策略？ → disabled（用户选）
    Q3 Mock 实现位置？ → frontend（用户选）
    Q4 决策冲突时？ → pause-notify（用户选）

  [批 2] 测试 + 部署模式（2 题）
    Q5 测试策略？ → chrome-mcp
    Q6 部署模式？ → cloud（→ 进批 4，跳批 3）

  [批 4a] 云端部署核心（2 题）
    Q7 部署触发方式？ → git-push
    Q8 部署等待时长？ → 300 秒

  [批 4b] 云端部署 URL（4 题，含 Other 自由文本）
    Q9 前端访问 URL？ → https://uat.example.com
    Q10 后端 API 基址？ → https://uat.example.com/api
    Q11 探测端点？ → https://uat.example.com/health
    Q12 部署脚本（仅 trigger=manual-script 时问）→ skip

  [批 4c] 探测超时（1 题）
    Q13 探测超时秒数？ → 900 秒

  [批 5] 第三方未交付清单
    Q14 有第三方接口未交付吗？ → 无

✍ 写回 PRD 头部：docs/requirements/V0.1.0/产品提供/PRD-用户中心.md
✅ git commit: chore(autopilot): 补全 V0.1.0 autopilot_decisions 决策预声明

Phase 0：前置检查
  ✅ 通知渠道 OK | PRD OK | git OK
  ✅ autopilot_decisions：8 段齐全

执行主流程（Phase 2/3）：进入...
```

## 场景 4：版本规划已存在 → 跳过规划直接开发

```
🚀 /sprint-autopilot 启动（--full-auto 模式）
   触发原因：V0.2.0 PRD 目录有新 commit（baseline=a1b2c3d → 当前=e5f6g7h）

Phase 0：前置检查
  ✅ 通知渠道 OK | PRD OK | git OK
  ✅ 版本扫描：V0.2.0（S1 已规划进行中）→ 选为 TARGET_VERSION

Phase 3.1.0：版本规划已存在检测（跳过规划门）
  检测 V0.2.0 规划产物：
    PLAN  = 1（docs/plans/V0.2.0/01_研发执行计划.md ✓）
    REQ   = 1（docs/requirements/V0.2.0/研发需求/ ✓）
    DESIGN= 1（docs/design/detail/V0.2.0/ ✓）
  ✅ 版本规划产物齐全，跳过 /version 规划，直接进入开发测试
  [里程碑通知 #1 规划开始：⏭️ 跳过（PLANNING_DONE=1，规划已提前完成）]
  [里程碑通知 #1b 已发：复用已有版本规划，将执行 5 个 Sprint]

Phase 3.2：批量 Sprint 执行（复用已有研发执行计划，5 Sprint）
  [里程碑通知 #1c 已发：开发开始，共 5 个 Sprint]
  ✅ Sprint-001 关闭（已在上轮完成，/sprint-batch 自动跳过）
  ✅ Sprint-002 关闭（已在上轮完成，/sprint-batch 自动跳过）
  ✅ Sprint-003 关闭 [里程碑通知 #2 已发]   ← 上次中断处，本轮继续
  ✅ Sprint-004 关闭 [里程碑通知 #2 已发]
  ✅ Sprint-005 关闭 [里程碑通知 #2 已发]

Phase 3.3-4：终审 + 完成通知 ...
✨ 全程未重跑 /version，复用已有版本规划，节省重复规划工时
```

> 💡 想推翻已有规划重新生成（如 PRD 大改）：`/sprint-autopilot --force-replan`
