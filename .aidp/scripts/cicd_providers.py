#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cicd_providers.py —— CICD 平台适配层（约定 31.5）。

`cicd_watch.py` 只关心「这次推送有没有起跑流水线、跑到哪一步、成没成、该不该重试」，
不关心流水线跑在哪个平台上。各平台的差异全部收在本模块，对上只暴露同一组动作：

| 动作 | 语义 |
|------|------|
| `check()` | 平台是否可用（CLI 已装 / 已登录 / 凭据齐备 / 能连通）|
| `list_runs(pipeline, commit, limit)` | 列出某条流水线最近的运行（可按 commit 过滤）|
| `view_run(pipeline, run_id)` | 查询一次运行的当前状态 |
| `trigger(pipeline, ref)` | 主动触发一次运行 |
| `retry(pipeline, run_id)` | 重试一次失败的运行 |

每次运行统一归一为：

    {"id": str, "status": "queued|running|success|failure|cancelled|skipped|unknown",
     "commit": str, "ref": str, "url": str, "created_at": str, "event": str, "raw_status": str}

## 内置提供方（`memory/aidp-config.yaml` 的 `cicd.provider`）

| provider | 平台 | `cicd.pipelines.<env>` 的含义 | 依赖 / 凭据 |
|----------|------|-------------------------------|-------------|
| `github-actions`（默认）| GitHub Actions | workflow 文件名或名称（如 `deploy-test.yml`）| `gh` CLI 已登录 |
| `gitlab-ci` | GitLab CI/CD（含自建）| 触发与过滤用的分支名（留空 = 不按分支过滤、触发时用当前分支）| `cicd.gitlab-ci.url` / `project`；令牌经 `token_env` 指向的环境变量 |
| `jenkins` | Jenkins | Job 路径（文件夹用 `/` 分隔，如 `team/deploy-test`）| `cicd.jenkins.url`；账号 / API Token 经 `user_env` / `token_env` |
| `command` | 任意平台（Gitee、Gitea、自建平台等）| 原样代入命令模板的 `{pipeline}` | `cicd.command.<动作>` 命令模板 |
| `none` | 不接入 CICD | — | — |

⛔ 令牌、密码只经环境变量引用，绝不明文写进配置文件。

## `command` 提供方的约定

`cicd.command` 下按动作配置 shell 命令模板，占位符 `{pipeline}` `{commit}` `{run_id}` `{ref}` `{limit}`
会被替换为经 shell 转义的实参：

    cicd:
      provider: command
      command:
        check: "mycli whoami"                       # 可选；退出码 0 = 可用
        list: "mycli runs --pipeline {pipeline} --commit {commit} --limit {limit} --json"
        view: "mycli run {run_id} --json"
        trigger: "mycli trigger {pipeline} --ref {ref} --json"   # 可选
        retry: "mycli rerun {run_id} --json"                      # 可选

- `list` 输出 JSON 数组、`view` 输出 JSON 对象，字段按上面的归一格式；`status` 也可给平台原值，
  会按常见取值（success/passed/failed/error/running/pending/canceled…）自动归一。
- `trigger` / `retry` 输出 `{"run_id": "..."}` 或空输出（表示新运行需随后按 commit 探测）。
- `view` 查无此运行时以非 0 退出并在输出里包含 `not found` 或 `404`。
"""
import base64
import json
import os
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request

PROVIDERS = ("github-actions", "gitlab-ci", "jenkins", "command", "none")
DEFAULT_PROVIDER = "github-actions"

PARSE_ERR = "__parse_error__:"
NOT_FOUND = "__not_found__:"

# 平台原始状态 → 归一状态（小写比较）
_STATUS_ALIASES = {
    "success": "success", "succeeded": "success", "passed": "success", "pass": "success", "ok": "success",
    "failure": "failure", "failed": "failure", "fail": "failure", "error": "failure", "errored": "failure",
    "timed_out": "failure", "startup_failure": "failure", "unstable": "failure",
    "cancelled": "cancelled", "canceled": "cancelled", "aborted": "cancelled", "killed": "cancelled",
    "running": "running", "in_progress": "running", "building": "running", "started": "running",
    "queued": "queued", "pending": "queued", "waiting": "queued", "requested": "queued", "created": "queued",
    "preparing": "queued", "scheduled": "queued", "waiting_for_resource": "queued", "manual": "queued",
    "not_built": "skipped", "skipped": "skipped", "neutral": "skipped", "stale": "skipped",
    "action_required": "skipped",
}


def normalize_status(raw):
    return _STATUS_ALIASES.get(str(raw or "").strip().lower(), "unknown")


def parse_json_blob(out):
    """从命令输出里取出 JSON（对象或数组），容忍前后夹杂日志行。返回 (data|None, 错误说明)。"""
    if not out or not str(out).strip():
        return None, "空输出"
    try:
        return json.loads(out), ""
    except ValueError as e:
        first = str(e)
    idx = [i for i in (out.find("{"), out.find("[")) if i >= 0]
    if idx and min(idx) > 0:
        try:
            return json.loads(out[min(idx):]), ""
        except ValueError:
            pass
    lines = out.splitlines()
    for k in range(len(lines) - 1, -1, -1):
        if not lines[k].lstrip().startswith(("{", "[")):
            continue
        try:
            return json.loads("\n".join(lines[k:])), ""
        except ValueError:
            continue
    return None, first


def match_commit(run, commit):
    """运行是否由 `commit` 起跑（双向前缀比较，至少 7 位防偶然命中）。"""
    if not commit:
        return False
    c = str(commit).strip().lower()
    got = str((run or {}).get("commit") or "").strip().lower()
    if not got:
        return False
    if c == got or c.startswith(got) or got.startswith(c):
        return min(len(c), len(got)) >= 7
    return False


# ── 可注入的执行器（自测用假实现替换，保证离线可跑）──────────────────────────
def _default_exec(argv, cwd, timeout, shell=False):
    p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, shell=shell)
    return p.returncode, p.stdout or "", p.stderr or ""


def _default_http(method, url, headers, data, timeout):
    """→ (status, body_text)；网络层错误抛 OSError。"""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310（地址来自项目配置）
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})


EXEC = _default_exec
HTTP = _default_http


class Provider:
    name = "base"

    def __init__(self, root, conf):
        self.root = root
        self.conf = conf or {}

    # 各子类实现 ↓
    def check(self):
        return True, "ok", ""

    def list_runs(self, pipeline, commit, limit):
        raise NotImplementedError

    def view_run(self, pipeline, run_id):
        raise NotImplementedError

    def trigger(self, pipeline, ref):
        return False, f"{self.name} 不支持主动触发"

    def retry(self, pipeline, run_id):
        return False, f"{self.name} 不支持重试"

    def needs_pipeline(self):
        return True


# ── GitHub Actions（gh CLI）───────────────────────────────────────────────────
class GitHubActions(Provider):
    name = "github-actions"
    RUN_FIELDS = "databaseId,status,conclusion,headSha,headBranch,event,createdAt,url"

    def _gh(self, args, timeout=60):
        gh = os.environ.get("AIDP_GH_BIN", "gh")
        try:
            rc, out, err = EXEC([gh] + list(args), self.root, timeout)
        except FileNotFoundError:
            return False, "未找到 gh 可执行文件（请安装 GitHub CLI：https://cli.github.com/）", "missing"
        except subprocess.TimeoutExpired:
            return False, f"gh {' '.join(args[:2])} 调用超时（>{timeout}s）", "timeout"
        if rc != 0:
            return False, (err or out).strip()[:300] or f"gh exit={rc}", "error"
        return True, out, "ok"

    @staticmethod
    def _norm(r):
        status = str(r.get("status") or "").lower()
        concl = str(r.get("conclusion") or "").lower()
        if status == "completed":
            norm = normalize_status(concl) if concl else "unknown"
        else:
            norm = "queued" if status in ("queued", "waiting", "requested", "pending") else \
                ("running" if status == "in_progress" else "unknown")
        return {"id": str(r.get("databaseId") or ""), "status": norm, "commit": r.get("headSha") or "",
                "ref": r.get("headBranch") or "", "url": r.get("url") or "",
                "created_at": r.get("createdAt") or "", "event": r.get("event") or "",
                "raw_status": f"{status}/{concl}" if concl else status}

    def check(self):
        ok, res, kind = self._gh(["--version"], timeout=15)
        if not ok:
            return False, "cli-missing" if kind == "missing" else "provider-unavailable", res
        ok, res, _ = self._gh(["auth", "status"], timeout=30)
        if not ok:
            return False, "unauthenticated", f"gh 未登录或凭据失效（先 `gh auth login`）：{res}"
        return True, "ok", ""

    def list_runs(self, pipeline, commit, limit):
        args = ["run", "list", "--workflow", str(pipeline), "--limit", str(limit), "--json", self.RUN_FIELDS]
        if commit:
            args[2:2] = ["--commit", str(commit)]
        ok, res, _ = self._gh(args)
        if not ok:
            return False, res
        data, perr = parse_json_blob(res)
        if not isinstance(data, list):
            return False, f"{PARSE_ERR}gh run list 输出解析失败（{perr or '非数组'}）：{res.strip()[:200]}"
        return True, [self._norm(r) for r in data if isinstance(r, dict)]

    def view_run(self, pipeline, run_id):
        ok, res, _ = self._gh(["run", "view", str(run_id), "--json", self.RUN_FIELDS])
        if not ok:
            low = str(res).lower()
            if "not found" in low or "could not find" in low or "404" in low:
                return False, f"{NOT_FOUND}{res}"
            return False, res
        data, perr = parse_json_blob(res)
        if not isinstance(data, dict):
            return False, f"{PARSE_ERR}gh run view 输出解析失败（{perr or '非对象'}）：{res.strip()[:200]}"
        return True, self._norm(data)

    def trigger(self, pipeline, ref):
        ok, res, _ = self._gh(["workflow", "run", str(pipeline), "--ref", str(ref)])
        return (True, None) if ok else (False, res)

    def retry(self, pipeline, run_id):
        ok, res, _ = self._gh(["run", "rerun", str(run_id), "--failed"])
        return (True, str(run_id)) if ok else (False, res)


# ── HTTP 类提供方公共部分 ─────────────────────────────────────────────────────
class _HttpProvider(Provider):
    def _env(self, key):
        name = self.conf.get(key)
        return os.environ.get(str(name), "") if name else ""

    def _req(self, method, url, headers=None, data=None, timeout=30):
        try:
            status, body, hdrs = HTTP(method, url, headers or {}, data, timeout)
        except OSError as e:
            return None, f"连接 {url} 失败：{e}", {}
        return status, body, hdrs

    def _json(self, method, url, headers=None, data=None, want=(dict, list)):
        status, body, _ = self._req(method, url, headers, data)
        if status is None:
            return False, body
        if status == 404:
            return False, f"{NOT_FOUND}HTTP 404 {url}"
        if status in (401, 403):
            return False, f"HTTP {status}（凭据无效或无权限）：{url}"
        if status >= 400:
            return False, f"HTTP {status}：{str(body)[:200]}"
        data, perr = parse_json_blob(body)
        if not isinstance(data, want):
            return False, f"{PARSE_ERR}{url} 响应解析失败（{perr or '类型不符'}）：{str(body)[:200]}"
        return True, data


# ── GitLab CI ────────────────────────────────────────────────────────────────
class GitLabCI(_HttpProvider):
    name = "gitlab-ci"

    def _base(self):
        url = str(self.conf.get("url") or "https://gitlab.com").rstrip("/")
        project = urllib.parse.quote(str(self.conf.get("project") or ""), safe="")
        return f"{url}/api/v4/projects/{project}"

    def _headers(self):
        return {"PRIVATE-TOKEN": self._env("token_env")}

    @staticmethod
    def _norm(p):
        return {"id": str(p.get("id") or ""), "status": normalize_status(p.get("status")),
                "commit": p.get("sha") or "", "ref": p.get("ref") or "", "url": p.get("web_url") or "",
                "created_at": p.get("created_at") or "", "event": p.get("source") or "",
                "raw_status": str(p.get("status") or "")}

    def needs_pipeline(self):
        return False  # 流水线随提交自动运行，pipelines.<env> 只作分支过滤，可留空

    def check(self):
        if not self.conf.get("project"):
            return False, "not-configured", "cicd.gitlab-ci.project 未配置（形如 group/name 或项目 ID）"
        if not self._env("token_env"):
            return False, "unauthenticated", "未提供 GitLab 访问令牌（cicd.gitlab-ci.token_env 指向的环境变量为空）"
        ok, res = self._json("GET", self._base(), self._headers(), want=dict)
        if not ok:
            return False, "provider-unavailable", str(res).replace(NOT_FOUND, "")
        return True, "ok", ""

    def list_runs(self, pipeline, commit, limit):
        q = {"per_page": str(limit), "order_by": "id", "sort": "desc"}
        if commit:
            q["sha"] = commit
        if pipeline:
            q["ref"] = pipeline
        ok, res = self._json("GET", f"{self._base()}/pipelines?{urllib.parse.urlencode(q)}",
                             self._headers(), want=list)
        return (True, [self._norm(p) for p in res if isinstance(p, dict)]) if ok else (False, res)

    def view_run(self, pipeline, run_id):
        ok, res = self._json("GET", f"{self._base()}/pipelines/{run_id}", self._headers(), want=dict)
        return (True, self._norm(res)) if ok else (False, res)

    def trigger(self, pipeline, ref):
        q = urllib.parse.urlencode({"ref": pipeline or ref})
        ok, res = self._json("POST", f"{self._base()}/pipeline?{q}", self._headers(), want=dict)
        return (True, str(res.get("id") or "") or None) if ok else (False, res)

    def retry(self, pipeline, run_id):
        ok, res = self._json("POST", f"{self._base()}/pipelines/{run_id}/retry", self._headers(), want=dict)
        return (True, str(res.get("id") or run_id)) if ok else (False, res)


# ── Jenkins ──────────────────────────────────────────────────────────────────
class Jenkins(_HttpProvider):
    name = "jenkins"
    TREE = "number,result,building,url,timestamp,actions[lastBuiltRevision[SHA1,branch[name]]]"

    def _url(self):
        return str(self.conf.get("url") or "").rstrip("/")

    def _job(self, pipeline):
        return "".join(f"/job/{urllib.parse.quote(p)}" for p in str(pipeline).strip("/").split("/") if p)

    def _headers(self):
        user, token = self._env("user_env"), self._env("token_env")
        if not (user and token):
            return {}
        auth = base64.b64encode(f"{user}:{token}".encode()).decode()
        return {"Authorization": f"Basic {auth}"}

    @staticmethod
    def _norm(b):
        commit, ref = "", ""
        for act in b.get("actions") or []:
            rev = (act or {}).get("lastBuiltRevision") if isinstance(act, dict) else None
            if rev:
                commit = rev.get("SHA1") or ""
                branches = rev.get("branch") or []
                ref = (branches[0] or {}).get("name", "") if branches else ""
                break
        if b.get("building"):
            status, raw = "running", "BUILDING"
        elif b.get("result") is None:
            status, raw = "queued", "QUEUED"
        else:
            raw = str(b.get("result"))
            status = normalize_status(raw)
        return {"id": str(b.get("number") or ""), "status": status, "commit": commit, "ref": ref,
                "url": b.get("url") or "", "created_at": str(b.get("timestamp") or ""), "event": "",
                "raw_status": raw}

    def check(self):
        if not self._url():
            return False, "not-configured", "cicd.jenkins.url 未配置"
        if not self._headers():
            return False, "unauthenticated", "未提供 Jenkins 账号 / API Token（cicd.jenkins.user_env / token_env 指向的环境变量为空）"
        ok, res = self._json("GET", f"{self._url()}/api/json?tree=mode", self._headers(), want=dict)
        return (True, "ok", "") if ok else (False, "provider-unavailable", str(res).replace(NOT_FOUND, ""))

    def list_runs(self, pipeline, commit, limit):
        tree = urllib.parse.quote(f"builds[{self.TREE}]{{0,{int(limit)}}}")
        ok, res = self._json("GET", f"{self._url()}{self._job(pipeline)}/api/json?tree={tree}",
                             self._headers(), want=dict)
        if not ok:
            return False, res
        runs = [self._norm(b) for b in res.get("builds") or [] if isinstance(b, dict)]
        return True, [r for r in runs if not commit or match_commit(r, commit)]

    def view_run(self, pipeline, run_id):
        tree = urllib.parse.quote(self.TREE)
        ok, res = self._json("GET", f"{self._url()}{self._job(pipeline)}/{run_id}/api/json?tree={tree}",
                             self._headers(), want=dict)
        return (True, self._norm(res)) if ok else (False, res)

    def _crumb(self):
        ok, res = self._json("GET", f"{self._url()}/crumbIssuer/api/json", self._headers(), want=dict)
        if ok and res.get("crumbRequestField"):
            return {res["crumbRequestField"]: res.get("crumb", "")}
        return {}

    def _post_build(self, pipeline):
        headers = dict(self._headers(), **self._crumb())
        status, body, _ = self._req("POST", f"{self._url()}{self._job(pipeline)}/build", headers, b"")
        if status is None:
            return False, body
        if status in (200, 201, 202):
            return True, None  # 进入队列，构建号要等开始后按 commit 探测
        return False, f"HTTP {status}：{str(body)[:200]}"

    def trigger(self, pipeline, ref):
        return self._post_build(pipeline)

    def retry(self, pipeline, run_id):
        return self._post_build(pipeline)


# ── 自定义命令 ────────────────────────────────────────────────────────────────
class Command(Provider):
    name = "command"

    def _tpl(self, action):
        return str(self.conf.get(action) or "").strip()

    def _run(self, action, **kw):
        tpl = self._tpl(action)
        if not tpl:
            return False, f"cicd.command.{action} 未配置", "missing"
        cmd = tpl
        for k, v in kw.items():
            cmd = cmd.replace("{" + k + "}", shlex.quote(str(v if v is not None else "")))
        try:
            rc, out, err = EXEC(cmd, self.root, int(self.conf.get("timeout", 120)), shell=True)
        except subprocess.TimeoutExpired:
            return False, f"cicd.command.{action} 执行超时", "timeout"
        if rc != 0:
            return False, (err or out).strip()[:300] or f"exit={rc}", "error"
        return True, out, "ok"

    @staticmethod
    def _norm(r):
        raw = r.get("raw_status") or r.get("status")
        norm = r.get("status") if r.get("status") in (
            "queued", "running", "success", "failure", "cancelled", "skipped", "unknown") else normalize_status(raw)
        return {"id": str(r.get("id") or r.get("run_id") or ""), "status": norm,
                "commit": r.get("commit") or r.get("sha") or "", "ref": r.get("ref") or "",
                "url": r.get("url") or "", "created_at": str(r.get("created_at") or ""),
                "event": r.get("event") or "", "raw_status": str(raw or "")}

    def check(self):
        for need in ("list", "view"):
            if not self._tpl(need):
                return False, "not-configured", f"cicd.command.{need} 未配置"
        if self._tpl("check"):
            ok, res, _ = self._run("check")
            if not ok:
                return False, "provider-unavailable", res
        return True, "ok", ""

    def list_runs(self, pipeline, commit, limit):
        ok, res, _ = self._run("list", pipeline=pipeline, commit=commit or "", limit=limit)
        if not ok:
            return False, res
        data, perr = parse_json_blob(res)
        if not isinstance(data, list):
            return False, f"{PARSE_ERR}cicd.command.list 输出不是 JSON 数组（{perr}）：{res.strip()[:200]}"
        runs = [self._norm(r) for r in data if isinstance(r, dict)]
        return True, [r for r in runs if not commit or match_commit(r, commit)]

    def view_run(self, pipeline, run_id):
        ok, res, _ = self._run("view", pipeline=pipeline, run_id=run_id)
        if not ok:
            low = str(res).lower()
            return False, (f"{NOT_FOUND}{res}" if ("not found" in low or "404" in low) else res)
        data, perr = parse_json_blob(res)
        if not isinstance(data, dict):
            return False, f"{PARSE_ERR}cicd.command.view 输出不是 JSON 对象（{perr}）：{res.strip()[:200]}"
        return True, self._norm(data)

    def _write(self, action, **kw):
        if not self._tpl(action):
            return False, f"cicd.command.{action} 未配置，无法自动{'触发' if action == 'trigger' else '重试'}"
        ok, res, _ = self._run(action, **kw)
        if not ok:
            return False, res
        data, _ = parse_json_blob(res)
        rid = (data or {}).get("run_id") if isinstance(data, dict) else None
        return True, (str(rid) if rid else None)

    def trigger(self, pipeline, ref):
        return self._write("trigger", pipeline=pipeline, ref=ref)

    def retry(self, pipeline, run_id):
        return self._write("retry", pipeline=pipeline, run_id=run_id)


_CLASSES = {"github-actions": GitHubActions, "gitlab-ci": GitLabCI, "jenkins": Jenkins, "command": Command}


def get_provider(root, cicd_conf):
    """按 `cicd_config()` 结果构造提供方实例；`none` 返回 None。未知名称抛 ValueError。"""
    name = str((cicd_conf or {}).get("provider") or DEFAULT_PROVIDER)
    if name == "none":
        return None
    cls = _CLASSES.get(name)
    if cls is None:
        raise ValueError(f"未知的 cicd.provider：{name}（可选：{', '.join(PROVIDERS)}）")
    return cls(root, (cicd_conf or {}).get(name) or {})
