# /sprint-dev — 参考输出与用法；执行期不加载

> 本片覆盖：参考输出与用法；执行期不加载。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

## 输出

### 分支 A（只开发：参数含 skip-test；被编排器调用时由 `/sprint-full`·`/sprint-batch` 透传 skip-test 落入本分支，test/bugfix/close 归编排器负责）

```
✅ /sprint-dev 完成（Sprint-{NNN} 开发阶段）

开发范围：{后端/前端/全部}

后端（仅获 related-test 授权时执行 TDD）：
- {列出实现的模块和接口}
- 单元测试：{真实结果；未请求为 NOT_REQUESTED}
- 编译验证：⏭️ 移至验收（/sprint-test 仅改动侧 + 资源受限执行）

前端：
- 公共组件：{列出新建/复用}
- 页面/组件：{N} 个
- 前端校验（lint + 类型检查，不打包）：⏭️ 移至验收（/sprint-test 仅改动侧 + 资源受限执行）

🔄 已更新：
- memory/{version}/{user}/activeContext.md

📌 下一步：
1. /sprint-test → 执行测试阶段
2. /sprint-bugfix sprint-{NNN} → 修复已知问题（如有）
```

### 分支 A/B 完整串联

```
🎉 /sprint-dev "{描述或编号}" 完成（Sprint-{NNN} 全流程）

{如分支 B，展示 Phase 0B 追加的文件清单}

各阶段摘要：
  Phase 0B 增量追加：✅ 完成（仅分支 B）
  Phase 0B.2 启动新 Sprint：✅ 完成（仅分支 B）
  Phase 1 开发：✅ 完成 — {摘要}
  Phase 2 测试：✅ 完成 — 通过 {N} / 失败 {N}
  Phase 3 修复：✅ 完成（{M} 轮循环，修复 {N} 个 bug）
  Phase 4 关闭：✅ 完成

📋 产出文件：
- docs/testing/{version}/sprint-{NNN}/
- docs/bugfix/{version}/bugfix-*-{user}.md（如有新 bug）
- memory/{version}/{user}/sprints/sprint-{NNN}.md

📌 下一步：
- /sprint-dev "<下个目标>" → 继续新增功能
- /sprint-bugfix → 修复零散 bug（无需新 Sprint）
- /version {version} → 发布版本
```

---

## 使用示例

```bash
# 场景 1：按计划被编排器调用（常见）
/sprint-full 001
# 内部会调用 /sprint-dev

# 场景 2：分步模式下的开发阶段
/sprint-start 001
/sprint-dev           # 默认实现+静态+相关单测；自动修复复验后终端返回
# 已授权父链中抑制自动串联可带 skip-test
/sprint-dev 001 skip-test

# 场景 3：★ 独立描述（默认 light，不累进）
/sprint-dev "新增用户导出功能"
# 默认light：实现 → 静态 → sprint-test → 必要修复/复验 → 终端；不创建Sprint

# 场景 4：只想开发不想自动测试
/sprint-dev "增加菜单缓存" skip-test

# 场景 5：只开发后端部分
/sprint-dev "重写权限模块" backend
```
