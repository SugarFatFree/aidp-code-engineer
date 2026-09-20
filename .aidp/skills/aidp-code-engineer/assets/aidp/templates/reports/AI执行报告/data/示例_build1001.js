/**
 * AI 执行报告 — 示例数据 build1001（数据契约权威示例）
 *
 * 职责：以全局变量注入方式提供一个 build 的完整 AI 执行结果数据（离线 file:// 可用，不走 fetch）。
 * 业务背景：autopilot 每跑完一个 build（Phase 3.4），就在 data/ 下新增一份 {version}_build{N}.js（按本文件 schema），
 *           并在 index.html 的 <body> 末尾、app.js 之前追加一行 <script src="data/xxx.js"></script>。
 *
 * 字段单位约定：featureRate / testPassRate / coverage / passRate 均为 0~1 小数（app.js 自动 ×100% 展示）。
 * 步骤状态枚举（plannedStatus / actualStatus）：done 完成 ｜ doing 进行中 ｜ fail 失败 ｜ pend 待处理 ｜ skip 跳过 ｜ plan 仅计划。
 */
(function () {
  // 全局收集容器：所有 build 数据 push 进来，app.js 统一读取
  window.__AIRUNS__ = window.__AIRUNS__ || [];

  window.__AIRUNS__.push({
    build: "V0.1.0_build1001",            // 完整 build 标识
    version: "V0.1.0",                    // 所属版本号
    buildNo: 1001,                        // build 序号（趋势图 X 轴 / 排序键）
    reportId: "RPT-V010-1001",            // 报告编号（渐变 head 右上角）
    generatedAt: "2026-06-16 06:30",      // 报告生成时间
    trigger: "PRD 更新",                  // 触发原因（PRD 更新 / --once / cron 等）
    branch: "feature/autopilot-V0.1.0",   // 代码分支
    deployMode: "local",                  // 部署模式 local|cloud|none
    deployUrl: "http://localhost:5173",   // 部署访问地址
    startedAt: "2026-06-15 22:00",        // 执行开始时间
    finishedAt: "2026-06-16 06:30",       // 执行结束时间
    duration: "8 小时 30 分",             // 消耗时长
    result: "partial",                    // 总体结果 success|partial|failed
    planSource: "复用已有规划",           // 规划来源（本轮 /version 新规划 | 复用已有规划），plan.html 元信息用

    // 执行概览（渐变卡 6 项）。statusKind 用于综合首页结果徽标着色：done|pend|fail
    overview: {
      statusText: "⚠️ 部分成功", statusKind: "pend",
      featureRate: 0.83,                  // 功能完成率
      testPassRate: 0.4615,               // 测试通过率（来自测试报告）
      coverage: 0.92,                     // 覆盖率（备用；cockpit 已不展示，漏斗取 testSummary.coverage）
      pendingCount: 4,                    // 待人工决策数（含待决策功能 + 待修复缺陷 + 待实施建议）
      autoFixedCount: 2,                  // 自动修复缺陷数（autopilot 本轮自动修复）
      riskLevel: "中",                    // 风险等级 低|中|高
      riskBasis: "1 个 P0 + 2 个 P1，通过率 46%，API 性能回归 20% → 中"  // 风险 tip「当前判定」行（可选）
    },

    // 步骤执行结果（autopilot 0-9 流程 + Phase；★ 0/1/2 步已回填，对应第 3 步要求）
    // type：准备 / 前置 / 规划 / 构建 / 开发 / 部署 / 测试 / 报告
    steps: [
      { name: "0 拉取远端全部分支 + 最新代码", type: "准备", plannedStatus: "done", actualStatus: "done", duration: "1m", output: "git fetch --all --prune；当前分支 rebase 到最新" },
      { name: "1 前置检查（测试方案/工具/部署/通知渠道）", type: "前置", plannedStatus: "done", actualStatus: "done", duration: "3m", output: "chrome-mcp 就绪；deployment 已配置；通知渠道已配置" },
      { name: "2 版本规划（/version）", type: "规划", plannedStatus: "done", actualStatus: "done", duration: "18m", output: "复用已有规划（研发需求/设计/执行计划齐全）" },
      { name: "3 铸造 build 号 + 生成 AI 执行计划", type: "构建", plannedStatus: "done", actualStatus: "done", duration: "2m", output: "V0.1.0_build1001；执行计划见同目录 plan.html" },
      { name: "Sprint-001 用户管理", type: "开发", plannedStatus: "plan", actualStatus: "done", duration: "2h10m", output: "start→dev→test→close，已提交" },
      { name: "Sprint-002 订单中心", type: "开发", plannedStatus: "plan", actualStatus: "done", duration: "2h40m", output: "start→dev→test→close，已提交" },
      { name: "5 提交推送 + 部署应用", type: "部署", plannedStatus: "plan", actualStatus: "done", duration: "12m", output: "推送 feature 分支触发 CI；local 启动 5173" },
      { name: "6 AI 自动化测试", type: "测试", plannedStatus: "plan", actualStatus: "done", duration: "1h05m", output: "见测试报告 build1001 子页（通过率 46%）" },
      { name: "7 修复遗留问题 + 回归", type: "测试", plannedStatus: "plan", actualStatus: "doing", duration: "—", output: "C-001/C-002 待 /sprint-bugfix 接力后重测" },
      { name: "8 生成 AI 执行结果（HTML）", type: "报告", plannedStatus: "plan", actualStatus: "done", duration: "1m", output: "本报告" }
    ],

    // 需求功能详情（逐功能点，与 plan.html 执行计划页「需求功能点比对」同源）。status：done|doing|fail|pend|skip
    // reqId=需求文档功能点编号，reqSource=需求文档来源章节 —— 用于逐条对照 01_研发需求.md 标注"哪些已完成"。
    features: [
      { num: 1, reqId: "FR-001", reqSource: "01_研发需求.md §3.1 登录鉴权", name: "用户认证模块改造", status: "done", sprint: "Sprint-001", owner: "autopilot", duration: "2h10m" },
      { num: 2, reqId: "FR-008", reqSource: "01_研发需求.md §4.2 下单流程", name: "订单流程优化", status: "done", sprint: "Sprint-002", owner: "autopilot", duration: "2h40m" },
      { num: 3, reqId: "FR-012", reqSource: "01_研发需求.md §5.1 数据看板", name: "数据看板首屏", status: "done", sprint: "Sprint-002", owner: "autopilot", duration: "1h20m" },
      { num: 4, reqId: "FR-015", reqSource: "01_研发需求.md §5.4 报表导出", name: "报表导出（Excel）", status: "pend", sprint: "Sprint-003", owner: "autopilot", reason: "导出 CSV 中文乱码，需产品确认是否改 Excel 格式" },
      { num: 5, reqId: "FR-020", reqSource: "01_研发需求.md §6 系统设置", name: "系统设置", status: "done", sprint: "Sprint-003", owner: "autopilot", duration: "50m" }
    ],

    // 测试摘要（★ 骨架阶段占位 {total:0,pass:0,fail:0,passRate:null,coverage:null,pendingBrowserTest:true}；
    //   真实值由 build 关闭方在 #F 之后 finalize：有浏览器测试=测试链路 aiauto-test Phase 3.7 / 静态-only=autopilot Phase 3.4。
    //   下例为 finalize 后的最终态（emit-report 恒从同 build AI测试报告的 summary 派生，与其逐字段一致）。★ 不要写 reportLink/兄弟报告路径——AI测试报告链接由 app.js 按当前页目录
    //   运行时推导（本地中文目录 / 部署英文 slug 两端都通），写死中文目录会在部署后 404）
    testSummary: { total: 13, pass: 6, fail: 4, block: 2, skip: 1, passRate: 0.4615 },

    // 缺陷汇总。severity 用 P0~P3
    defects: [
      { id: "C-001", title: "退订接口返回 500（后端 NPE）", severity: "P1", status: "待修复", impact: "订单退订流程中断" },
      { id: "C-002", title: "导出订单 Excel 文件名乱码", severity: "P2", status: "待修复", impact: "影响导出可用性，非阻断" }
    ],

    // 风险与建议（质量风险 + 改进建议，不含具体缺陷条目；level：高|中|低）。无则留空数组，章节显示「无风险项」
    risks: [
      { id: "RISK-001", level: "高", title: "P1 缺陷阻断退订链路",
        what: "C-001（退订接口 500）未修复，阻断订单退订主流程，存在线上资损风险",
        risk: "P1 缺陷 1 个待修复，影响核心交易闭环。",
        advice: "优先 /sprint-bugfix 修复 C-001，回归退订链路后再发版。" },
      { id: "RISK-002", level: "中", title: "导出功能可用性受限",
        what: "C-002 导出 Excel 文件名乱码，非阻断但影响导出体验",
        risk: "中文文件名编码问题，影响导出可用性。",
        advice: "统一导出文件名 UTF-8 编码并补充边界用例。" },
      { id: "RISK-003", level: "中", title: "报表导出格式待产品确认",
        what: "功能 #4（报表导出）处于待决策，CSV 中文乱码需产品确认是否改 Excel",
        risk: "需求未闭环，可能影响后续 Sprint 排期。",
        advice: "尽快约产品拍板导出格式，确认后补 Sprint 实现。" }
    ],

    // 异常 / 失败处置（无则留空数组，子页自动隐藏该分区）
    incidents: [
      { step: "6 AI 自动化测试", symptom: "退订用例返回 500", action: "捕获回写问题清单 C-001", result: "待 bugfix 接力" }
    ],

    // 剩余待办（无则留空数组）
    todos: [
      { title: "修复 C-001 / C-002 后触发回归（第 7 步闭环）", detail: "/sprint-bugfix 拾取 → 重新部署 → /sprint-aiauto-test --once 重测" },
      { title: "报表导出格式待产品确认", detail: "功能 #4 处于待决策，确认后补 Sprint" }
    ],

    // 关联链接（执行计划见同目录 plan.html，由 app.js 按 build 拼 plan.html#/build/<build>，不再用 planDoc；
    //   ★ 不要写 testReport/兄弟报告路径——AI测试报告链接由 app.js/plan.js 按当前页目录运行时推导，
    //   兼容本地中文目录与部署英文 slug，写死会在部署后 404）
    links: {
      buildsLog: "../../../../release/builds/builds-2026-06-16.md"
    }
  });
})();
