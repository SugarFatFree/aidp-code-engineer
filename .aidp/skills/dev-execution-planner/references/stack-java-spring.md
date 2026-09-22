# Java / Spring 命令细则

> 探测命中 `*.java` + `pom.xml`/`build.gradle` 时加载。跨技术栈通用规则见 `../SKILL.md`。

## 一、脚手架生成

```bash
mvn archetype:generate ...              # 建工程骨架
mvn mybatis-plus:generate               # 生成 Entity/Mapper/Service CRUD 模板
```

## 二、开发期轻量验证（⚠️ Task 验收标准写这个 · 本节是本 SKILL 里 Java 编译验证命令的**唯一信源**）

> ⛔ **先读这条：`mvn compile` 不是"只编译"。** 它会跑完
> `validate → initialize → **generate-sources → process-sources → generate-resources → process-resources** → compile`
> 整条 lifecycle，**绑在这些相上的插件全部执行**——最常见的 `frontend-maven-plugin` 官方默认就绑在
> `generate-resources`，于是 `mvn compile` 会真的去跑 `npm install` + `npm run build`。
> 即一条写着"只编译不打包"的命令**可以直接触发本 SKILL 明文严禁的完整前端构建**，
> 与「开发期验证 ≠ 发布期构建」铁律（`stack-index.md`）直接冲突。
> ⚠️ ⛔ 不要写 `mvn compile  # ✅ 只编译，不打包`——**那句话是错的**。
> `mvn clean compile` 更糟：`clean` 先删 `target/`，前端产物必然重建一遍。

**默认命令是 `mvn -q compiler:compile`**（直调插件 goal、**不走 lifecycle**，是本节唯一有确定性保证的写法）。
`mvn compile` 只在**确认过本项目没有代码生成/前端构建插件**时才用——这个确认靠下面这条 grep 起步，
但 ⚠️ **grep 只能证伪、不能证实**（理由见表下第 ① 条），拿不准一律回落 `compiler:compile`。

```bash
# 递归扫全部 pom（多模块/AIDP 的 code/backend/<子项目>/pom.xml 都在 3 层以上，`*/pom.xml` 扫不到）
find . -name pom.xml -not -path '*/target/*' -print0 \
  | xargs -0 grep -nE "frontend-maven-plugin|<phase>(validate|initialize|generate-|process-|compile)</phase>|(protobuf|jooq-codegen|openapi-generator|swagger-codegen|avro|antlr4|jaxb2|build-helper|templating|git-commit-id|exec|xolstice|gmavenplus|kotlin)-maven-plugin|maven-processor-plugin|<annotationProcessorPaths>"
```

> ⚠️ **看输出，别看 `$?`**：无命中时 `xargs` 会把 `grep` 的 1 放大成 **123**，按 `$? == 1` 判「干净」会判错。

| grep 结果 | 开发期编译验证怎么写 |
| :- | :- |
| **有命中**（有插件绑在 compile 及更早的相上，或有代码生成器） | ⛔ **不得**用 `mvn compile`。用 `mvn -q compiler:compile` |
| **无命中** | 两条都可以，**默认仍推荐 `mvn -q compiler:compile`**；确需走 lifecycle（例如项目靠 `generate-sources` 产码、见下一行）才写 `mvn -q compile`。⚠️ **无命中 ≠ 证明干净**，见下方第 ① 条 |
| **有命中，且项目真的依赖 generate-sources 产码**（protobuf / jOOQ / OpenAPI codegen / MapStruct 走 `<execution>` 级 `annotationProcessorPaths`） | 开发期**不做**编译验证，**交 CI**。此时 `compiler:compile` 会漏掉生成源码而**假红**、`mvn compile` 又会触发全量构建，两条都不成立，与 `code-verification-loop` 维度 0「Java 侧刻意不做、编译期错误交 CI」同口径 |

**三条实测事实（Maven 3.8.7 / JDK 17，别照直觉改）：**

① ⚠️ **grep 无命中不等于「没有插件绑在 compile 之前」——插件可以用自己的默认相绑定，pom 里根本不写 `<phase>`。**
   实测：`build-helper-maven-plugin:add-source` 的默认相就是 `generate-sources`，一个只写 `<goals>` 不写 `<phase>`
   的 execution，上面那条 grep 是靠**插件名**命中它的；换成一个不在名单里的 codegen 插件就**一个字都扫不到**，
   而 `mvn compile` 照样会执行它。所以判据只能这么用：**有命中 ⇒ 一定别用 `mvn compile`；无命中 ⇒ 只是没查出来。**
   ⛔ 别把「无命中」写成 Task 验收标准里的结论性理由。

② ⚠️ **`compiler:compile` 跑的是 `default-cli` 执行，会静默忽略嵌在 `<execution>` 里的 `<configuration>`。**
   实测：把一个非法 `<compilerArgs>` 放进 `<execution><id>default-compile</id>` → `mvn compile` **失败**、
   `mvn compiler:compile` **成功**；把同一个参数提到插件级 `<configuration>` → 两者都失败。
   即 execution 级的 `annotationProcessorPaths`（MapStruct 最常见写法）、`<release>`、`<excludes>`、`<compilerArgs>`
   在 `compiler:compile` 下**都不生效**，编译用的是与真实构建**不同的一套设置**，失效方向是**假绿**。
   插件级 `<configuration>` 不受影响、照常生效；Lombok 这类靠 classpath 生效的注解处理器也照常工作（实测通过）。

③ ⚠️ **`compiler:compile` 假红的识别标志**：报 `cannot find symbol`，且找不到的符号来自 `target/generated-sources/`
   或已知 codegen 产物包。此时**落第三档交 CI**，⛔ **不要因此改回 `mvn compile`**——那是拿一次全量前端构建换一条编译结论。

> ❌ **禁止**把 `mvn package` / `mvn install` / `mvn clean compile` 写进开发期 Task 的验收标准。
> ⚠️ **不要给 `compile` 加 `-DskipTests`**：`compile` 相压根到不了 `test-compile`/`test`，这个开关是**空操作**，
> 只会让人误以为「compile 会跑测试」。真正需要它的是 `mvn package -DskipTests`（第四节，发布期）。
> ⚠️ **别加 `-o`（离线）来"堵住联网"**：Phase 1 骨架 Task 里依赖通常还没进本地仓，`-o` 会直接失败；
> 而且它压根堵不住要堵的那件事——`frontend-maven-plugin` 是自己发 HTTP 下 node/npm 包的，`-o` 管不着。
> 想避免联网拉依赖，正确做法是把 `mvn dependency:resolve` 单列成一个**显式的**依赖预拉取 Task（见第四节），
> 而不是给验证命令偷偷加个必然报错、且并不解决问题的开关。

## 三、单元测试（Phase 2）

```bash
mvn test -Dtest=*ServiceTest            # 只跑核心业务逻辑单测
mvn test -Dtest=OrderServiceTest#shouldRejectWhenBalanceInsufficient
```

## 四、依赖安装 / 构建

```bash
mvn dependency:resolve                  # 依赖预拉取
mvn package -DskipTests                 # ⚠️ 发布/部署期（CICD）用，不写进开发期 Task
mvn dependency-check:check              # Phase 5 安全扫描
```

## 五、本栈 Task 拆分要点

- **DDL 与详细设计 A.3 一致性**：建表 Task 的验收标准挂 `python3 <SKILL_DIR>/scripts/check_ddl_consistency.py <ddl.sql> <详细设计.md>`。
- **枚举类生成 Task**：详细设计 A.4 每个字典/枚举都要有对应枚举类 Task（含 MyBatis `TypeHandler` / JPA `@Convert`），不可并进业务 Task 里含糊带过。
- **编译验证放在骨架 Task 之后**：先建包结构 + 配置文件，再让业务 Task 逐个按**第二节的判据**挂编译验收（默认 `mvn -q compiler:compile`；⛔ 别直接写 `mvn compile`）。
