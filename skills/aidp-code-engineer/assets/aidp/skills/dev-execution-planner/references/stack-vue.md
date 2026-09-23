# 前端 Vue 命令细则

> 探测命中 `*.vue` 或 `package.json` 依赖含 `vue` 时加载。跨技术栈通用规则见 `../SKILL.md`。

## 一、脚手架生成

```bash
pnpm create vite <project> --template vue-ts
pnpm dlx @vue/cli create <project>       # Vue CLI 老项目
```

## 二、开发期轻量验证（⚠️ Task 验收标准写这个）

```bash
vue-tsc --noEmit                         # ✅ 只做类型检查，不产出构建物
pnpm type-check                          # 若 package.json 已定义该脚本，优先用它
```

**兜底**：未装 `vue-tsc`（或无 `type-check` 脚本）时，降级用打包器做一次语法级检查：

```bash
npx esbuild <入口文件> --bundle --outfile=/dev/null
```

> ❌ **禁止**把 `pnpm build` / `vite build` 写进开发期 Task 的验收标准——那是发布期构建，会做完整打包 + 压缩 + 产物输出，耗时数十倍于类型检查。

## 三、单元测试 / E2E

```bash
pnpm vitest run src/components/OrderList.spec.ts   # 单测
pnpm playwright test                                # Phase 4 E2E
```

## 四、依赖安装 / 构建

```bash
pnpm install --frozen-lockfile
pnpm build                               # ⚠️ 发布/部署期（CICD）用，不写进开发期 Task
```

## 五、本栈 Task 拆分要点

- **枚举/常量 Task**：与后端枚举 code/label 一致性作为验收标准的一条，防前后端各自定义。
- **Mock 残留扫描**：Phase 4 挂 `python3 <SKILL_DIR>/scripts/scan_mock_data.py src/`。
- **字段处置 → 独立 Task**（核心原则 11）：需求字段处置为「前端计算还原」的，必须拆独立前端计算 Task，不并进列表渲染 Task。
