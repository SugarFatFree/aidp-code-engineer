/**
 * AI 执行报告 — 示例数据 build1002（第二个 build，用于综合首页趋势对比）
 * 字段 schema 与 示例_build1001.js 完全一致，详见该文件字段注释。
 */
(function () {
  window.__AIRUNS__ = window.__AIRUNS__ || [];

  window.__AIRUNS__.push({
    build: "V0.1.0_build1002",
    version: "V0.1.0",
    buildNo: 1002,
    reportId: "RPT-V010-1002",
    generatedAt: "2026-06-17 05:10",
    trigger: "C-001/C-002 修复后回归",
    branch: "feature/autopilot-V0.1.0",
    deployMode: "local",
    deployUrl: "http://localhost:5173",
    startedAt: "2026-06-16 22:00",
    finishedAt: "2026-06-17 05:10",
    duration: "7 小时 10 分",
    result: "success",
    planSource: "复用已有规划",           // 规划来源，plan.html 元信息用

    overview: {
      statusText: "✅ 成功", statusKind: "done",
      featureRate: 1.0, testPassRate: 0.6667, coverage: 0.94, pendingCount: 0, autoFixedCount: 0, riskLevel: "低"
    },

    steps: [
      { name: "0 拉取远端全部分支 + 最新代码", type: "准备", plannedStatus: "done", actualStatus: "done", duration: "1m", output: "git fetch --all --prune" },
      { name: "1 前置检查", type: "前置", plannedStatus: "done", actualStatus: "done", duration: "2m", output: "环境/配置/通知渠道 复用 baseline" },
      { name: "2 版本规划", type: "规划", plannedStatus: "done", actualStatus: "skip", duration: "—", output: "规划已存在，跳过" },
      { name: "3 铸造 build 号 + AI 执行计划", type: "构建", plannedStatus: "done", actualStatus: "done", duration: "1m", output: "V0.1.0_build1002" },
      { name: "4 修复 C-001 / C-002", type: "开发", plannedStatus: "plan", actualStatus: "done", duration: "1h20m", output: "退订 NPE + 导出乱码已修" },
      { name: "5 提交推送 + 部署", type: "部署", plannedStatus: "plan", actualStatus: "done", duration: "10m", output: "重新部署 5173" },
      { name: "6 AI 自动化测试（回归）", type: "测试", plannedStatus: "plan", actualStatus: "done", duration: "55m", output: "通过率 67%（2 条失败已登记下个 build）" },
      { name: "8 生成 AI 执行结果（HTML）", type: "报告", plannedStatus: "plan", actualStatus: "done", duration: "1m", output: "本报告" }
    ],

    features: [
      { num: 1, name: "退订接口修复", status: "done", owner: "autopilot", duration: "40m" },
      { num: 2, name: "导出乱码修复", status: "done", owner: "autopilot", duration: "40m" }
    ],

    // ★ 不写 reportLink/兄弟报告路径——AI测试报告链接由 app.js 按当前页目录运行时推导（本地中文 / 部署英文 slug 两端都通）
    testSummary: { total: 9, pass: 6, fail: 2, block: 1, skip: 0, passRate: 0.6667 },

    defects: [],
    // 风险与建议（level：高|中|低）。成功 build 一般为低风险或空
    risks: [
      { id: "RISK-001", level: "低", title: "无显著质量风险",
        what: "本 build 全部功能完成、通过率 67%、无 P0/P1 缺陷",
        risk: "未发现阻断性风险。", advice: "保持当前质量基线，持续监控线上指标。" }
    ],
    incidents: [],
    todos: [],

    // 关联链接：不写 testReport/兄弟报告路径——由 app.js/plan.js 按当前页目录运行时推导（本地中文 / 部署英文 slug 两端都通）
    links: {}
  });
})();
