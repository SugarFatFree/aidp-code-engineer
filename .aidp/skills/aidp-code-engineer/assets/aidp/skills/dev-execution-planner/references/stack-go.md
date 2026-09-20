# Go 命令细则

> 探测命中 `go.mod` 时加载。跨技术栈通用规则见 `../SKILL.md`。

## 一、脚手架生成

```bash
go mod init <module>
goctl api go -api <x.api> -dir .         # Go-Zero 生成 API 骨架
```

## 二、开发期轻量验证（⚠️ Task 验收标准写这个）

```bash
go build ./...                           # ✅ 编译检查，不产出可执行文件到处跑
go vet ./...                             # 静态检查，配合使用
```

> Go 的 `go build ./...` 本身就是轻量的（增量编译 + 编译缓存），可直接作开发期验证；但**禁止**把交叉编译 / `-ldflags` 打包 / 容器镜像构建写进开发期 Task。

## 三、单元测试

```bash
go test ./internal/service/... -run TestOrder
go test ./... -cover                     # Phase 5 覆盖率
```

## 四、依赖安装 / 构建

```bash
go mod tidy && go mod download
CGO_ENABLED=0 go build -o bin/app ./cmd/server   # ⚠️ 发布/部署期用
```

## 五、本栈 Task 拆分要点

- **`go mod tidy` 会自动改 `go.mod`**：涉及新增依赖的 Task，验收标准须含「`go.mod` diff 已 review、无未评估的重型依赖引入」。
- **枚举具名类型 Task**：详细设计 A.4 每个字典/枚举都要有对应具名类型 + `driver.Valuer`/`sql.Scanner` 实现。
