/* 回归 fixture：实际项目中 V0.10.2 build1002 AI执行报告的问题数据形态（脱敏）。
 * 症状：risks 用 {high,medium,low} 分组对象（致 app.js .map 白屏）、todos 裸字符串、
 *       featureRate/testPassRate 字符串口径、无 buildNo。渲染端须兼容不崩、校验端须精确报错。 */
(function () {
  window.__AIRUNS__ = window.__AIRUNS__ || [];
  window.__AIRUNS__.push(
    {
      "build": "V0.10.2_build1002", "version": "V0.10.2",
      "startedAt": "2026-08-04 23:10:00", "finishedAt": "2026-08-04 23:55:00",
      "overview": { "statusKind": "pass", "featureRate": "6/6", "testPassRate": "100%（复测轮）", "coverage": null, "pendingCount": 0 },
      "testSummary": { "total": 5, "pass": 5, "fail": 0, "passRate": 100.0, "coverage": 100.0 },
      "steps": [{ "name": "开发", "type": "dev", "plannedStatus": "done", "actualStatus": "done" }],
      "features": [{ "num": 1, "name": "候选项跳转详情页", "status": "done" }],
      "defects": [],
      "risks": { "high": [], "medium": ["EC appId 自动解析…本轮游客态未覆盖…"], "low": ["8 条跳过用例…待补测"] },
      "todos": ["待补测游客态", "补 8 条跳过用例"]
    }
  );
})();
