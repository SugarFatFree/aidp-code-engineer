# 容器工具：以宿主机用户运行（按需 Read）

容器默认以 root 运行，写进 bind mount 的产物（导入回执、导出文件、构建物）会变成 **root 属主**，宿主机普通用户之后读不了、删不掉。凡在项目里通过 `docker run` / `docker exec` 跑工具，统一带宿主用户：

```bash
# 标准包装：自动补 --user "$(id -u):$(id -g)"；已显式传 --user/-u 的原样转发
python3 {{AIDP_HOME}}/scripts/docker_host_user.py run --rm -v "$PWD/code/backend:/w" IMAGE CMD…   # cli-check: ignore 其余参数原样透传给 docker
python3 {{AIDP_HOME}}/scripts/docker_host_user.py exec CONTAINER CMD…
python3 {{AIDP_HOME}}/scripts/docker_host_user.py --dry-run run --rm IMAGE CMD…   # 只打印最终命令  cli-check: ignore 透传 docker 参数
```

等价的手写形式：`docker run --user "$(id -u):$(id -g)" …`。镜像里该 uid 没有家目录时，工具若要写 `$HOME`，再补 `-e HOME=/tmp`。

## 检查现有容器包装脚本

```bash
python3 {{AIDP_HOME}}/scripts/docker_host_user.py --check run_tests.sh scripts/*.sh
```

逐个找出缺 `--user` / `-u` 的 `docker|podman|docker compose run/exec`（合并 `\` 续行后判断）；退出 1 表示有缺项，按提示补 `--user`。确需 root 的行加注释 `# aidp:allow-root` 显式留痕。

## 与入口护栏的关系

`pretool-guard.py` 对 `docker cp/exec/run` 分类：写**容器文件系统**属外部副作用，走授权提示（不是“包装器写入”拒绝）；容器内命令改的路径落在 `-v/--mount` 绑定到仓库的目录时，按宿主源路径校验是否在任务 `write_set` 内。离线自检：`python3 {{AIDP_HOME}}/hooks/pretool-guard.py --explain "<docker 命令>"`。
