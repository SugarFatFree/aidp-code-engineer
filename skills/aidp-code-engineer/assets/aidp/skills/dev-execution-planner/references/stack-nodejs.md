# Node.js 后端命令细则（NestJS / Express / Koa）

> 探测命中 `package.json` 依赖含 `express`/`koa`/`@nestjs/core` 时加载。跨技术栈通用规则见 `../SKILL.md`。

## 一、脚手架生成

```bash
npx @nestjs/cli new <project>
npx @nestjs/cli generate resource <name>   # 生成 CRUD 骨架
```

## 二、开发期轻量验证（⚠️ Task 验收标准写这个）

```bash
tsc --noEmit                              # ✅ 只做类型检查
pnpm lint                                 # 配合 ESLint
```

> ❌ **禁止**把 `nest build` / `pnpm build` 写进开发期 Task 验收标准——发布期构建。

## 三、单元测试

```bash
pnpm jest src/order/order.service.spec.ts
pnpm test:cov                             # Phase 5 覆盖率
```

## 四、依赖安装 / 构建

```bash
pnpm install --frozen-lockfile
pnpm build                                # ⚠️ 发布/部署期用
```

## 五、本栈 Task 拆分要点

- **`devDependencies` 陷阱**：运行时代码 import 的包若只声明在 `devDependencies`，生产 `npm ci --omit=dev` 后启动即 `MODULE_NOT_FOUND`。涉及新依赖的 Task，验收标准须含「已确认放在正确的依赖区」。
- **枚举/DTO Task**：详细设计 A.4 每个字典/枚举要有 TS 定义 + ORM 映射（TypeORM `enum` / Prisma `enum`）。
