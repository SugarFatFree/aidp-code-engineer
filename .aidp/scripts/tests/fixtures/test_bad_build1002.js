/* 回归 fixture：实际项目中 V0.10.2 build1002 AI测试报告的问题数据形态（脱敏）。
 * 症状：cases 用 name/status/detail（非契约 title/result/note）、passRate=100.0（致 10000%）、无 buildNo。
 *       渲染端须别名容错不显 undefined、校验端须精确报错。 */
(function () {
  window.__BUILDS__ = window.__BUILDS__ || [];
  window.__BUILDS__.push(
    {
      "build": "V0.10.2_build1002", "version": "V0.10.2",
      "summary": { "total": 5, "pass": 5, "fail": 0, "block": 0, "skip": 0, "passRate": 100.0 },
      "suites": [], "defects": [], "runtimeErrors": [],
      "cases": [
        { "id": "TC-A-07", "name": "候选项跳转详情页（六板块）", "status": "pass", "detail": "★复测通过：六板块均可跳转" }
      ]
    }
  );
})();
