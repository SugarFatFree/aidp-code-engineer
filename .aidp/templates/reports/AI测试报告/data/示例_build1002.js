/**
 * AI测试报告 — 示例数据 build1002
 *
 * 职责：第二个 build 的完整测试数据，相对 build1001 通过率上升（用于演示趋势图 / 切换效果）。
 * 业务背景：同 示例_build1001.js，按相同 schema push 到 window.__BUILDS__。
 */
(function () {
  window.__BUILDS__ = window.__BUILDS__ || [];

  window.__BUILDS__.push({
    build: "V0.1.0_build1002",
    version: "V0.1.0",
    buildNo: 1002,
    startedAt: "2026-06-15 09:30",
    finishedAt: "2026-06-15 10:40",
    trigger: "缺陷修复回归",
    branch: "feature/autopilot-V0.1.0",
    deployMode: "cloud",
    testUrl: "https://uat.example.com",
    renderMode: "headed",
    // ★ 环境事实类字段必须成对：有 renderMode 就必须有 renderModeSource（四选一：
    //   显式指定 / 复用已有实例(含来源) / 无头不可用降级(含原因) / 运行取证(方法)）。
    //   ⛔ 示例里只写值不写来源，等于亲自示范「模板示例值被原样留下」那个反模式。
    renderModeSource: "复用已有实例(用户已开的 Chrome 9222 调试端口)",
    driver: "mcp",
    // 通过率较 build1001（0.4615）提升至 0.6667，体现修复成效（趋势图演示两个 build 的爬升）
    // ⛔ 同 build1001：统计字段由 gen_report.py 聚合、须与下方 cases[] 自洽，不得手填
    summary: { total: 9, pass: 6, fail: 2, block: 1, skip: 0, passRate: 0.6667 },
    suites: [
      { id: "SUITE-001", name: "用户管理", total: 2, pass: 2, fail: 0, block: 0, skip: 0 },
      { id: "SUITE-002", name: "订单中心", total: 4, pass: 2, fail: 1, block: 1, skip: 0 },
      { id: "SUITE-003", name: "数据看板", total: 2, pass: 1, fail: 1, block: 0, skip: 0 },
      { id: "SUITE-004", name: "系统设置", total: 1, pass: 1, fail: 0, block: 0, skip: 0 }
    ],
    cases: [
      { id: "T-001-01", title: "账号密码登录成功",     suite: "SUITE-001", result: "pass", note: "",                        screenshot: "screenshots/t-001-01.png" },
      { id: "T-001-03", title: "新增用户必填校验",     suite: "SUITE-001", result: "pass", note: "C-? 已补手机号校验，回归通过", screenshot: "screenshots/t-001-03.png" },
      { id: "T-002-03", title: "退订接口返回正常",     suite: "SUITE-002", result: "pass", note: "C-001 已修复",            screenshot: "screenshots/t-002-03.png" },
      { id: "T-002-04", title: "导出订单为 Excel",     suite: "SUITE-002", result: "pass", note: "C-002 已修复，文件名正常", screenshot: "screenshots/t-002-04.png" },
      { id: "T-002-05", title: "批量发货阻塞",         suite: "SUITE-002", result: "block", note: "物流接口仍未交付",       screenshot: "screenshots/t-002-05.png" },
      { id: "T-002-06", title: "订单详情金额合计",     suite: "SUITE-002", result: "fail", note: "合计金额四舍五入偏差 1 分", screenshot: "screenshots/t-002-06.png" },
      { id: "T-003-02", title: "趋势图时间切换",       suite: "SUITE-003", result: "pass", note: "C-003 已修复",            screenshot: "screenshots/t-003-02.png" },
      { id: "T-003-04", title: "看板导出 PDF",         suite: "SUITE-003", result: "fail", note: "PDF 中文字体缺失",        screenshot: "screenshots/t-003-04.png" },
      { id: "T-004-01", title: "修改系统主题",         suite: "SUITE-004", result: "pass", note: "",                        screenshot: "screenshots/t-004-01.png" }
    ],
    defects: [
      { id: "C-004", title: "订单详情金额合计四舍五入偏差 1 分", severity: "P2", caseId: "T-002-06", status: "待修复" },
      { id: "C-005", title: "看板导出 PDF 中文字体缺失",         severity: "P3", caseId: "T-003-04", status: "待修复" }
    ],
    runtimeErrors: [
      { id: "R-003", desc: "GET /api/order/export 200 但响应头 Content-Disposition 缺 filename*", url: "/order", status: "已修复" }
    ],
    screenshots: [
      { step: "登录页",     path: "screenshots/login.png",       caseId: "T-001-01" },
      { step: "退订成功",   path: "screenshots/t-002-03.png",     caseId: "T-002-03" },
      { step: "导出成功",   path: "screenshots/t-002-04.png",     caseId: "T-002-04" }
    ]
  });
})();
