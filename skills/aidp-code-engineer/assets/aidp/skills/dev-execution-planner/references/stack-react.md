# 前端 React 命令细则

> 探测命中 `*.jsx`/`*.tsx` 或 `package.json` 依赖含 `react` 时加载。跨技术栈通用规则见 `../SKILL.md`。

## 一、脚手架生成

```bash
pnpm create vite <project> --template react-ts
npx create-next-app@latest <project>     # Next.js 项目
```

## 二、开发期轻量验证（⚠️ Task 验收标准写这个）

```bash
tsc --noEmit                             # ✅ 只做类型检查，不产出构建物
pnpm type-check                          # 若 package.json 已定义该脚本，优先用它
```

**兜底**：无 TS（纯 JS 项目）时用 lint 做语法级检查：

```bash
npx eslint src --max-warnings=0
npx esbuild <入口文件> --bundle --outfile=/dev/null
```

> ❌ **禁止**把 `pnpm build` / `next build` 写进开发期 Task 验收标准——发布期构建，耗时数十倍。

## 三、单元测试 / E2E

```bash
pnpm vitest run                          # 或 pnpm jest
pnpm playwright test                     # Phase 4 E2E
```

## 四、依赖安装 / 构建

```bash
pnpm install --frozen-lockfile
pnpm build                               # ⚠️ 发布/部署期（CICD）用
```

## 五、本栈 Task 拆分要点

- **枚举/常量 Task**：与后端 code/label 一致性作为验收标准之一。
- **Mock 残留扫描**：Phase 4 挂 `scan_mock_data.py`；用 MSW 时须一并检查 `worker.start()` 调用点已删。
- **字段处置 → 独立 Task**（核心原则 11）：「前端计算还原」拆独立 Task。
