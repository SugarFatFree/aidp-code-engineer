/**
 * AI测试报告 — 示例数据 build1001
 *
 * 职责：以全局变量注入方式提供一个 build 的完整测试数据（离线 file:// 可用，不走 fetch）。
 * 业务背景：下游每跑完一个 build，就在 data/ 下新增一份 示例_buildNNNN.js（按本文件 schema），
 *           并在 index.html 的 <body> 末尾、app.js 之前追加一行 <script src="data/xxx.js"></script>。
 *
 * 数据契约（两套模板共用，务必严格对齐）：见文件末尾字段注释。
 */
(function () {
  // 全局收集容器：所有 build 数据 push 进来，app.js 统一读取
  window.__BUILDS__ = window.__BUILDS__ || [];

  window.__BUILDS__.push({
    build: "V0.1.0_build1001",            // 完整 build 标识
    version: "V0.1.0",                    // 所属版本号
    buildNo: 1001,                        // build 序号（趋势图 X 轴 / 排序键）
    startedAt: "2026-06-14 10:00",        // 测试开始时间
    finishedAt: "2026-06-14 11:30",       // 测试结束时间
    trigger: "PRD 更新",                  // 触发原因
    branch: "feature/autopilot-V0.1.0",   // 代码分支
    deployMode: "local",                  // 部署模式 local|cloud|none
    testUrl: "http://localhost:5173",     // 被测访问地址
    // ★ 渲染模式 = 环境事实字段：值由上游 auto-test-runner「运行环境取证」产出的 env-facts.json 填充（headless|headed|null）；
    //   ★ 取不到写 null（展示为「未取到」），严禁回落成本示例值或按启动 flag 推断（缺陷反馈：报告恒显「有头」根因 = 用意图值/兜底）。
    //   具体取证判据的单一信源 = auto-test-runner references/driver-<端>.md + execution-methodology.md §10（本示例不复刻判据）。
    renderMode: "headless",               // 渲染模式 headless|headed|null(未取到)
    renderModeSource: "运行取证(浏览器运行时渲染标识含无头标记)",  // ★ 来源标注：显式指定 / 复用已有实例(含来源) / 无头不可用降级(含原因) / 运行取证(方法) / 未取到(原因)
    driver: "cli",                        // 自动化驱动 cli|mcp
    // 汇总：total=pass+fail+block+skip；passRate=pass/total（0~1 小数）
    // ⛔ 统计字段必须由 gen_report.py 从 results/*.json 聚合得来、与下方 cases[] 逐条自洽，不得手填：
    //    emit-report.py 的溯源校验会重算 cases[] 的 pass 占比比对（容差 ±0.005），对不上即报错。
    summary: { total: 13, pass: 6, fail: 4, block: 2, skip: 1, passRate: 0.4615 },
    // 套件分解：每个套件的用例分布（各计数之和须等于 summary，且与 cases[] 的 suite 归属一致）
    suites: [
      { id: "SUITE-001", name: "用户管理", total: 3, pass: 2, fail: 1, block: 0, skip: 0 },
      { id: "SUITE-002", name: "订单中心", total: 5, pass: 2, fail: 2, block: 1, skip: 0 },
      { id: "SUITE-003", name: "数据看板", total: 3, pass: 1, fail: 1, block: 1, skip: 0 },
      { id: "SUITE-004", name: "系统设置", total: 2, pass: 1, fail: 0, block: 0, skip: 1 }
    ],
    // 用例明细：result 取值 pass|fail|block|skip
    cases: [
      { id: "T-001-01", title: "账号密码登录成功",        suite: "SUITE-001", result: "pass",  note: "",                       screenshot: "screenshots/t-001-01.png" },
      { id: "T-001-02", title: "错误密码登录提示",        suite: "SUITE-001", result: "pass",  note: "",                       screenshot: "screenshots/t-001-02.png" },
      { id: "T-001-03", title: "新增用户必填校验",        suite: "SUITE-001", result: "fail",  note: "手机号未做格式校验",     screenshot: "screenshots/t-001-03.png" },
      { id: "T-002-01", title: "订单列表分页加载",        suite: "SUITE-002", result: "pass",  note: "",                       screenshot: "screenshots/t-002-01.png" },
      { id: "T-002-02", title: "订单状态筛选",            suite: "SUITE-002", result: "pass",  note: "",                       screenshot: "screenshots/t-002-02.png" },
      { id: "T-002-03", title: "退订接口返回 500",        suite: "SUITE-002", result: "fail",  note: "后端 NPE，见缺陷 C-001", screenshot: "screenshots/t-002-03.png" },
      { id: "T-002-04", title: "导出订单为 Excel",        suite: "SUITE-002", result: "fail",  note: "导出文件名乱码",         screenshot: "screenshots/t-002-04.png" },
      { id: "T-002-05", title: "批量发货阻塞",            suite: "SUITE-002", result: "block", note: "依赖物流接口未交付",     screenshot: "screenshots/t-002-05.png" },
      { id: "T-003-01", title: "看板首屏指标渲染",        suite: "SUITE-003", result: "pass",  note: "",                       screenshot: "screenshots/t-003-01.png" },
      { id: "T-003-02", title: "趋势图时间切换",          suite: "SUITE-003", result: "fail",  note: "切换近 7 天数据未刷新",  screenshot: "screenshots/t-003-02.png" },
      { id: "T-003-03", title: "导出报表阻塞",            suite: "SUITE-003", result: "block", note: "报表服务 503",           screenshot: "screenshots/t-003-03.png" },
      { id: "T-004-01", title: "修改系统主题",            suite: "SUITE-004", result: "pass",  note: "",                       screenshot: "screenshots/t-004-01.png" },
      { id: "T-004-02", title: "短信网关配置（暂缓）",    suite: "SUITE-004", result: "skip",  note: "本期不交付，忽略",       screenshot: "" }
    ],
    // 缺陷汇总：severity 用 P0~P3
    defects: [
      { id: "C-001", title: "退订接口返回 500（后端 NPE）", severity: "P1", caseId: "T-002-03", status: "待修复" },
      { id: "C-002", title: "导出订单 Excel 文件名乱码",    severity: "P2", caseId: "T-002-04", status: "待修复" },
      { id: "C-003", title: "看板趋势图切换近 7 天不刷新",  severity: "P2", caseId: "T-003-02", status: "修复中" }
    ],
    // 运行时错误：浏览器 console / network 层异常
    runtimeErrors: [
      { id: "R-001", desc: "Uncaught TypeError: cannot read 'list' of undefined", url: "/order", status: "待修复" },
      { id: "R-002", desc: "GET /api/report/export 503 Service Unavailable",      url: "/dashboard", status: "待修复" }
    ],
    // 截图清单：用于报告内引用展示
    screenshots: [
      { step: "登录页",       path: "screenshots/login.png",     caseId: "T-001-01" },
      { step: "订单列表",     path: "screenshots/order-list.png", caseId: "T-002-01" },
      { step: "退订报错",     path: "screenshots/t-002-03.png",   caseId: "T-002-03" }
    ]
  });
})();
