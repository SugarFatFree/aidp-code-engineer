<!-- 本文件是 `/version` 发布路径 Step 3.4.4「失败处置」的执行分片，由 `release-7.md` 指向。 -->

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/version/release-7c.md`。理据见同目录 `rationale.md`。

# /version 发布路径 · Step 3.4.4 失败处置

> ⛔ **本步写的 `docs/audit/{version}/发布欠账.md` 必须落库**：3.4.1 的提交发生在**本步之前**，
> 故本步新写入的欠账**赶不上那一笔**——不补一次提交，`git status` 会留一个 untracked 文件，
> 换台机器 clone 或任何一次 `git clean` 就连本地都不剩，而 `--finalize-docs` / `--rebuild-baseline`
> 都以「开始先读发布欠账.md」为驱动。**本步任何一条欠账写完后立即**：
>
> ```bash
> VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version 2>/dev/null)   # ⛔ 跨围栏取空会 git add 到 docs/audit//
> if [ -n "$VERSION" ] && [ -n "$(git status --porcelain docs/audit/)" ]; then
>   git add "docs/audit/$VERSION/" && git commit --amend --no-edit
>   # ⛔ 若 tag 已推送则改用独立提交，⛔ 不得 amend 已推送的提交：
>   #   git add "docs/audit/$VERSION/" && git commit -m "docs($VERSION): 登记发布欠账"
> fi
> ```

> 本文件承接 `release-7.md`（3.4.1 提交 / 3.4.2 打 tag / 3.4.3 推送）。
> **进入本步的前提**：3.4.3 的推送或 tag 动作出现失败/冲突。

- `git push` 因远端有新提交而拒绝 → 自动 `git pull --rebase origin <branch>` 一次再 push；rebase 冲突 → 中断并提示用户手动处理
- 网络/权限失败 → 报错并提示用户后续手动 `git push origin $TAG_NAME` **和 `git push origin $BRANCH_NAME`**，**不撤销本地 tag 与版本分支**（都已就位）
- 远端**已有同名 tag / 版本分支**（3.4.2 预检后被并发推入）→ 本次已授权的强推及 tag 保护降级已由 `release-7.md` 在同一执行块内完成；授权在首次 push 前经 `baseline_edit.py take release_force_authorized` 原子消费。本片**不得读历史授权位重新强推或删除 ref**。剩余失败登记发布欠账，重新发布需重新经过现有授权门。
- **★ tag 保护策略仍拒绝（含删除失败）** → 在 Step 3.6 报告显式标注「远端 tag 受保护、推送失败，需人工处置」，保留失败证据并登记欠账；**绝不静默留下“本地 tag 与远端不一致”**。网络或权限失败不等于可以无授权删除远端 tag。
- **★ tag 成功但版本分支创建/推送失败**（或反之）→ 不回滚已成功的一方，终端 WARN 提示手动补齐缺失的一方（`git branch $BRANCH_NAME && git push origin $BRANCH_NAME`），并在报告里标注

输出提示：
```
🏷️ 已创建本地 tag {TAG_NAME} 并推送到 origin（命名规则见 Step 3.4.2）。
🌿 已创建版本分支 {BRANCH_NAME}（大写 V 风格）并推送到 origin。
📤 已推送本分支 + 标签 {TAG_NAME} + 版本分支 {BRANCH_NAME}
```

> ⏭ **Step 3.5 / 3.6 见 `release-7b.md`**（本片超 20480B 上限后按仓内惯例二次切分）。
