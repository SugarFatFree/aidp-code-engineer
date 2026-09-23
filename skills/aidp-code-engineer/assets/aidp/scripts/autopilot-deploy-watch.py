#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autopilot-deploy-watch.py —— 部署就绪探针 + last_deployed_at 写入（确定性、可复用）

职责边界（与约定 31.5 / sprint-autopilot Phase 3.2.1 对齐）：
  本脚本封装「推送即监听不变式」6 步里【可确定性脚本化的通用部分 = 步骤 ④⑤⑥】：
    ④ 按后端冷启动特性等待（期间 502/503/连接拒绝属正常，内置容忍窗口）
    ⑤ 部署就绪探针——先判 health（actuator/health 或自定义健康端点 UP/200），
       再可选「登录后自身鉴权接口连续 2 次正常取到数据」（--auth-url，⛔ 不用登录页可达性判就绪）
    ⑥ 就绪后写 baseline versions.{version}.last_deployed_at（放行测试链路）
  ★ 步骤 ①②③（查流水线是否被自动触发 / 未触发则主动触发 / 轮询至终态 + 失败重试≤3）
    因依部署 mode 而异——cicd-provider 经 `cicd_watch.py`（平台 = cicd.provider）、git-push 依 CI、
    local 起后台进程——不在本脚本内实现；由命令端 Phase 3.2.1 按 mode 编排后，
    调本脚本做 ④⑤⑥。命令端「一行调用」即得确定性就绪判定，无需每处手写轮询循环。

设计原则：
  - 仅用 Python3 标准库（urllib），无外部依赖，任何环境可跑。
  - 就绪判据：health 200/UP 为**必要**；--auth-url 给出时额外要求连续 2 次取到**非空**数据体。
  - 冷启动容忍：--cold-start-seconds（默认 55s，JVM/Spring 冷启动常见量级）内 502/503/连接错误
    **不判失败**、继续轮询；超 --timeout 才判超时。
  - 跨 tick 续探：`--since` 给出首次探测时刻时，冷启动窗口与 --timeout 都从它起算；单次调用最多运行
    `--max-seconds`（默认 480s，短于宿主 Bash 工具 10 分钟上限），到时未就绪且总超时未到 → exit 4。
  - 退出码：0=就绪并已写 last_deployed_at；2=超时未就绪（命令端据此走 probe_fail_streak 熔断，不重跑流水线）；
    3=参数错误；**4=本次调用已到 --max-seconds 上限但总超时未到（pending：下个 tick 带同一 --since 续探，不记失败）**；
    **5=已就绪但写 last_deployed_at 失败**（⛔ 不得并入 2：2 会触发 probe-timeout 冻结，
    而那个 reason 的解冻证据正是 last_deployed_at，等于把恢复路径一起堵死）。输出 JSON 到 stdout（ok/ready/elapsed/reason/last_deployed_at），诊断/进度到 stderr。
  - 时间：用 datetime.now() 取本地 ISO-8601（供 last_deployed_at）——本脚本是独立 CLI 进程、不在被禁时间 API 的工作流沙箱内，可正常用。

用法：
  python3 AIDP_HOME/scripts/autopilot-deploy-watch.py \
      --health-url http://host:8080/actuator/health \
      [--auth-url http://host:8080/api/xxx/list] \
      [--cold-start-seconds 55] [--timeout 300] [--interval 5] \
      [--since <首次探测时刻 ISO>] [--max-seconds 480] \
      [--auth-header 'Authorization: Bearer <token>'] \
      --version V0.10.1 [--baseline memory/.sprint-autopilot-baseline.json] \
      [--no-write]           # 只探针、不写 last_deployed_at（用于纯就绪检查）
"""
import sys
import os
import json
import time
import argparse
import re
import urllib.request
import urllib.error
from datetime import datetime

# 冷启动期视为"正常、继续等"的 HTTP 状态与网络错误
COLD_START_HTTP = {502, 503, 504}


def _http_get(url, headers=None, timeout=8):
    """返回 (status_code:int|None, body:str)。网络层异常 → (None, err_str)。"""
    req = urllib.request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:  # URLError / socket timeout / 连接拒绝 等
        return None, str(e)


def _health_ok(status, body):
    """health 判据：200 且（若是 JSON）status 字段非 DOWN/OUT_OF_SERVICE。"""
    if status != 200:
        return False
    b = (body or "").strip()
    if not b:
        return True  # 200 空体也算通（有些健康端点返回空）
    # ⛔ **HTML 一律不认**，哪怕是 200：nginx 的 `try_files $uri /index.html` 会把
    #   `/actuator/health` 这种「后端还没起来、路由打不到」的请求兜成 **200 + 前端首页 HTML**。
    #   把它算成健康，就会写下 `last_deployed_at` + `phase_beta_done_at` 放行测试链路，
    #   让整套用例对着一个死后端跑完 —— 这是本脚本能造成的最坏后果（姊妹函数
    #   `_data_nonempty` 早就防住了同一类响应，两个函数不能一松一紧）。
    low = b[:400].lstrip().lower()
    if low.startswith("<!doctype html") or low.startswith("<html") or "<html" in low[:200]:
        return False
    try:
        j = json.loads(b)
        st = str(j.get("status", "")).upper()
        if st in ("DOWN", "OUT_OF_SERVICE"):
            return False
    except Exception:
        pass  # 非 JSON 的 200 短文本（如 "OK" / "UP"）算通
    return True


def _data_nonempty(status, body):
    """鉴权接口取数判据：200 且响应体非空、非明显空集。"""
    if status != 200:
        return False
    b = (body or "").strip()
    if not b:
        return False
    # 明显空集（[] / {} / null / 空分页）视为未取到数据
    if b in ("[]", "{}", "null"):
        return False
    try:
        j = json.loads(b)
        # 常见分页结构：data.total==0 / records==[] 视为空
        data = j.get("data", j) if isinstance(j, dict) else j
        if isinstance(data, dict):
            if data.get("total") in (0, "0"):
                return False
            recs = data.get("records", data.get("list", data.get("rows")))
            if isinstance(recs, list) and len(recs) == 0:
                return False
        if isinstance(data, list) and len(data) == 0:
            return False
    except Exception:
        # ⛔ 非 JSON 的非空 200 **不等于取到数据**：会话失效时大量 Spring/SPA 后端
        #   返回 `200 + 登录页 HTML` 而非 401/302。把它算作就绪，就会让测试链路
        #   对着「起来了但登不进去」的环境跑完整套用例 —— 整批 block 或大面积假失败，
        #   最后按 unconverged / account-invalid 冻结，诊断方向被彻底带偏。
        #   `--auth-url` 的语义是「登录后**自身鉴权接口**正常取到数据」，那必然是结构化响应。
        low = b[:400].lower()
        if "<html" in low or "<!doctype html" in low:
            return False
        return False          # 非 JSON 一律不认（保守：宁可多等一轮，不误判就绪）
    return True



def derive_health_url(root, version, baseline_path):
    """`--health-url` 缺省时的推导链（返回 (url, source)；都取不到返回 ("", 原因)）。

    ⛔ 补的是一处会直接崩的缺口：调用方（`release-7.md` Step 3.4.3）从 PRD frontmatter 取
    `cloud_ready_api_url`，而**没有该字段的项目**会让本脚本以
    `the following arguments are required: --health-url` 退出 —— 在发布链的中段。
    推导链只用**本地已有事实**，不猜、不编：
      ① baseline `versions.{V}.deployment.cloud_ready_api_url`
      ② baseline `versions.{V}.deployment.local_backend_url`（+ /actuator/health）
      ③ `docs/testing/{V}/研发自测/01_测试环境与账号.md` 里的后端 URL（约定 38 的归档落点）
    """
    try:
        with open(os.path.join(root, baseline_path), encoding="utf-8") as f:
            vo = ((json.load(f).get("versions") or {}).get(version) or {})
        dep = vo.get("deployment") or {}
        u = str(dep.get("cloud_ready_api_url") or "").strip()
        if u:
            return u, "baseline deployment.cloud_ready_api_url"
        u = str(dep.get("local_backend_url") or "").strip()
        if u:
            return u.rstrip("/") + "/actuator/health", "baseline deployment.local_backend_url"
    except Exception:
        pass
    doc = os.path.join(root, "docs/testing", version, "研发自测", "01_测试环境与账号.md")
    try:
        text = open(doc, encoding="utf-8").read()
    except OSError:
        return "", "baseline 无 deployment URL，且测试环境与账号文档不存在"
    m = re.search(r"https?://[^\s`|)>\]]+", text)
    if m:
        return m.group(0).rstrip("/") + "/actuator/health", "01_测试环境与账号.md"
    return "", "baseline 与测试环境与账号文档里都找不到后端 URL"


def _write_last_deployed(baseline_path, version, ts):
    """写 versions.{V}.last_deployed_at。

    ★ 并发安全：baseline 同时被两条 /loop 写（开发链路 10m / 测试链路 5m）。此处曾是**裸
    read-modify-write**（读整份 → 改一个键 → 整份覆盖写），与对方的写交叉时会把对方刚落的
    字段（典型：aiauto-test 刚写的 ai_report_finalized）整体抹掉。故复用 baseline_edit.py 的
    flock + 锁内重读 + os.replace；模块导入失败才退化为原地写（比不写强）。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    # ⛔ **只把 import 放进 try**：把写操作一起包住时，加锁写路径上的任何异常都会被
    #    静默吞成"降级"，且零 stderr —— "走了锁"与"降级了"在外部完全同形。
    try:
        from baseline_edit import LockedBaseline
    except Exception:
        LockedBaseline = None
    if LockedBaseline is not None:
        with LockedBaseline(baseline_path, write=True) as b:
            _v = b.data.setdefault("versions", {}).setdefault(version, {})
            _v["last_deployed_at"] = ts
            # ★ 必须**同一把锁内成对写** `phase_beta_done_at`（契约见 phase-3-5b.md）：
            #   `baseline_edit.py current-version` 的定义是「phase_beta_done_at 非空且
            #   internal_released_at 为空」——只写 last_deployed_at 时它**选不出版本**，
            #   测试链路每 tick 静默 exit 0，而开发链路因心跳还在刷而判「测试链路健康」，
            #   两条 loop 互等、都在跑、什么都没测。路径 A（phase-3-7）与 sprint-batch
            #   step-6b 都成对写了，唯独本脚本（IRON-5 路径 B，覆盖最高频的"修完再推一次"）漏写。
            _v.setdefault("phase_beta_done_at", ts)
        return
    sys.stderr.write("⚠️ baseline_edit 不可用 → 本次 last_deployed_at 降级为**无锁写**\n")
    if not os.path.exists(baseline_path):
        sys.stderr.write("⚠️ baseline 不存在，放弃写 last_deployed_at（⛔ 不新建桩文件）\n")
        return
    try:
        with open(baseline_path, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("baseline 顶层不是对象")
    except Exception as exc:
        # ⛔ 绝不用 `d = {}` 继续往下走：那会把两条 loop 的全部 run_state / builds /
        #    冻结字段替换成只含 last_deployed_at 的桩文件，全链路状态归零且无人察觉
        #    （下一 tick 表现为"首次运行"）——而这发生在部署刚成功、最不该出事的时刻。
        sys.stderr.write(f"⚠️ baseline 读取失败（{exc}）→ 放弃写 last_deployed_at，⛔ 不覆盖\n")
        return
    _v = d.setdefault("versions", {}).setdefault(version, {})
    _v["last_deployed_at"] = ts
    _v.setdefault("phase_beta_done_at", ts)   # 同上：成对写，否则 current-version 选不出版本
    os.makedirs(os.path.dirname(baseline_path) or ".", exist_ok=True)
    tmp = baseline_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, baseline_path)


def main():
    ap = argparse.ArgumentParser(description="部署就绪探针 + last_deployed_at 写入")
    ap.add_argument("--health-url", default="",
                    help="健康端点（actuator/health 等），⛔ 不要用登录页 URL。"
                         "省略时按 baseline → 测试环境与账号文档 依次推导（见 --help 下方说明）")
    ap.add_argument("--auth-url", default="", help="可选：登录后自身鉴权取数接口，要求连续 2 次取到非空数据")
    ap.add_argument("--auth-header", action="append", default=[], help="可选：请求头，如 'Authorization: Bearer <token>'（可多次）")
    ap.add_argument("--cold-start-seconds", type=int, default=55, help="冷启动容忍窗口（期间 502/503/连接错不判失败）")
    ap.add_argument("--timeout", type=int, default=300, help="总超时秒数，超时判未就绪 exit 2")
    ap.add_argument("--interval", type=int, default=5, help="轮询间隔秒")
    ap.add_argument("--version", default="", help="写 last_deployed_at 的版本键（--no-write 时可省）")
    ap.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    ap.add_argument("--no-write", action="store_true", help="只探针、不写 last_deployed_at")
    ap.add_argument("--since", default="",
                    help="首次探测时刻（ISO-8601）；给出时冷启动窗口与 --timeout 从它起算（跨 tick 续探）")
    ap.add_argument("--max-seconds", type=int, default=480,
                    help="单次调用运行上限秒（默认 480）；到时未就绪且总超时未到 → exit 4（pending）")
    args = ap.parse_args()

    if not args.no_write and not args.version:
        print(json.dumps({"ok": False, "reason": "写 last_deployed_at 需 --version（或加 --no-write）"}, ensure_ascii=False))
        return 3

    headers = {}
    for h in args.auth_header:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    call_start = time.time()
    start_wall = call_start
    if args.since:
        try:
            start_wall = min(call_start, datetime.fromisoformat(args.since).timestamp())
        except ValueError:
            sys.stderr.write(f"⚠️ --since 不是 ISO 时间（{args.since}）→ 按本次调用起算\n")
    if not args.health_url:
        args.health_url, src = derive_health_url(".", args.version, args.baseline)
        if not args.health_url:
            sys.stderr.write(f"⛔ 未给 --health-url 且推导失败（{src}）→ 无法做就绪探针。\n"
                             f"   补法：① 传 --health-url ② 在 PRD autopilot_decisions.deployment 配 "
                             f"cloud_ready_api_url / local_backend_url ③ 按约定 38 把后端地址归档进 "
                             f"docs/testing/{args.version}/研发自测/01_测试环境与账号.md\n")
            return 3
        sys.stderr.write(f"ℹ️ --health-url 缺省 → 推导为 {args.health_url}（来源：{src}）\n")

    health_ready = False
    auth_ok_count = 0
    last_reason = ""

    while True:
        elapsed = time.time() - start_wall
        if elapsed > args.timeout:
            out = {"ok": False, "ready": False, "elapsed": round(elapsed, 1),
                   "reason": f"就绪探针超时（{args.timeout}s 内未就绪）：{last_reason}"}
            print(json.dumps(out, ensure_ascii=False))
            sys.stderr.write(f"⛔ 部署就绪探针超时：{last_reason}（部署可能成功但服务未就绪/登录不通，走人工介入，勿重跑流水线）\n")
            return 2
        if time.time() - call_start > args.max_seconds:
            out = {"ok": False, "ready": False, "pending": True, "elapsed": round(elapsed, 1),
                   "since": datetime.fromtimestamp(start_wall).astimezone().isoformat(timespec="seconds"),
                   "reason": f"单次调用已到 {args.max_seconds}s 上限、总超时 {args.timeout}s 未到：{last_reason}"}
            print(json.dumps(out, ensure_ascii=False))
            sys.stderr.write("⏳ 就绪探针本次调用到上限，下个 tick 带同一 --since 续探（不记失败）\n")
            return 4

        if not health_ready:
            st, body = _http_get(args.health_url, headers)
            if _health_ok(st, body):
                health_ready = True
                sys.stderr.write(f"✅ health 就绪（{args.health_url} → {st}），elapsed={elapsed:.0f}s\n")
            else:
                in_cold = elapsed <= args.cold_start_seconds
                cold_ok = st in COLD_START_HTTP or st is None
                last_reason = f"health 未就绪（status={st}）" + ("；冷启动窗口内属正常" if (in_cold and cold_ok) else "")
                sys.stderr.write(f"… 等待 health（status={st}, elapsed={elapsed:.0f}s{'，冷启动窗口内' if in_cold else ''}）\n")
                time.sleep(args.interval)
                continue

        # health 已就绪；若无 auth-url 则判就绪
        if not args.auth_url:
            break

        st, body = _http_get(args.auth_url, headers)
        if _data_nonempty(st, body):
            auth_ok_count += 1
            sys.stderr.write(f"✅ 鉴权接口取到数据（第 {auth_ok_count}/2 次，{args.auth_url} → {st}）\n")
            if auth_ok_count >= 2:
                break
            time.sleep(args.interval)
        else:
            auth_ok_count = 0  # 需连续 2 次，中断则清零
            last_reason = f"鉴权接口未取到数据（status={st}）"
            sys.stderr.write(f"… 等待鉴权接口取数（status={st}, elapsed={elapsed:.0f}s）\n")
            time.sleep(args.interval)

    elapsed = time.time() - start_wall
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    result = {"ok": True, "ready": True, "elapsed": round(elapsed, 1),
              "health_url": args.health_url, "auth_checked": bool(args.auth_url)}
    if not args.no_write:
        try:
            _write_last_deployed(args.baseline, args.version, ts)
            result["last_deployed_at"] = ts
            result["version"] = args.version
            sys.stderr.write(f"✅ 已写 baseline versions.{args.version}.last_deployed_at={ts}（放行测试链路）\n")
        except BaseException as e:      # ★ BaseException：LockedBaseline 解析失败抛 SystemExit
            result["ok"] = False
            result["reason"] = f"就绪但写 last_deployed_at 失败：{e}"
            print(json.dumps(result, ensure_ascii=False))
            # ⛔ 绝不与「超时未就绪」共用 2：命令端据 2 递增 push_probe_fail_streak、≥3 冻
            #    freeze_reason=probe-timeout，而该 reason 的**解冻证据正是 last_deployed_at**
            #    —— 这一轮失败的恰恰就是写它。诊断方向与恢复路径会被同时带偏。
            return 5
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
