#!/usr/bin/env python3
"""Verify declared frontend feature strings in assets referenced by the deployed HTML."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import sys
import urllib.parse
import urllib.request

from autopilot_decisions_merge import resolve, dig_path
from baseline_edit import LockedBaseline


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "script" and attr.get("src"):
            self.urls.append(attr["src"])
        elif tag == "link" and attr.get("rel") == "stylesheet" and attr.get("href"):
            self.urls.append(attr["href"])


def fetch(url):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urllib.request.urlopen(req, timeout=12) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}: {url}")
        data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError(f"asset exceeds 8 MiB: {url}")
        return data.decode("utf-8", "replace")


def record_ready(version, build_id, commit, verified, baseline):
    """Publish build and version deployment evidence in one locked write."""
    with LockedBaseline(baseline, write=True) as state:
        version_node = (state.data.get("versions") or {}).get(version)
        if not isinstance(version_node, dict):
            raise ValueError(f"version not found: {version}")
        build_nodes = version_node.get("builds") or []
        matches = [node for node in build_nodes if isinstance(node, dict) and node.get("build") == build_id]
        if len(matches) != 1:
            raise ValueError(f"current build not found or ambiguous: {build_id}")
        if version_node.get("current_build") != build_id:
            raise ValueError(f"current build changed: {build_id}")
        if commit and matches[0].get("push_commit") != commit:
            raise ValueError(f"push commit changed: {build_id}")
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        matches[0].update(frontend_deploy_verified=verified, probe_passed=True, probe_at=now)
        if commit:
            matches[0]["probe_commit"] = commit
        else:
            matches[0].pop("probe_commit", None)
        version_node["last_deployed_at"] = now
        version_node["phase_beta_done_at"] = now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--prd-root", default="docs/requirements")
    parser.add_argument("--fallback", default="memory/aidp-config.yaml")
    parser.add_argument("--record-ready", action="store_true")
    parser.add_argument("--build")
    parser.add_argument("--commit", default="")
    parser.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    args = parser.parse_args()
    result = {"verified": False, "skipped": False, "missing": [], "reason": ""}
    try:
        config = resolve(args.version, args.prd_root, args.fallback)["merged"]
        frontend = dig_path(config, "deployment.deploy_ends.frontend")
        if not isinstance(frontend, dict) or frontend.get("trigger") == "none":
            result.update(skipped=True, reason="frontend deployment not declared")
        else:
            probe = frontend.get("ready_asset_probe") or {}
            features = probe.get("must_contain") if isinstance(probe, dict) else None
            if features in (None, [], "[]"):
                result.update(skipped=True, reason="no frontend feature strings declared")
            elif not isinstance(features, list) or not features or not all(isinstance(x, str) and x for x in features):
                result["reason"] = "must_contain must be a nonempty list of nonempty strings"
            elif not probe.get("url"):
                result["reason"] = "ready_asset_probe.url missing"
            else:
                url = probe["url"]
                html = fetch(url)
                assets = Assets()
                assets.feed(html)
                origin = urllib.parse.urlsplit(url)
                urls = [urllib.parse.urljoin(url, name) for name in assets.urls]
                urls = [name for name in urls if urllib.parse.urlsplit(name).netloc == origin.netloc
                        and urllib.parse.urlsplit(name).scheme == origin.scheme]
                if not urls:
                    result["reason"] = "no same-origin JS/CSS assets referenced by HTML"
                else:
                    bodies = [fetch(name) for name in urls]
                    result["missing"] = [feature for feature in features
                                         if not any(feature in body for body in bodies)]
                    result["verified"] = not result["missing"]
                    result["assets"] = urls
                    if result["missing"]:
                        result["reason"] = "frontend feature strings absent from deployed assets"
    except (OSError, ValueError, KeyError) as exc:
        result["reason"] = str(exc)
    if not result["verified"] and not result["skipped"]:
        print(json.dumps(result, ensure_ascii=False))
        return 1
    if args.record_ready:
        try:
            if not args.build:
                raise ValueError("--record-ready requires --build")
            record_ready(args.version, args.build, args.commit, result["verified"], args.baseline)
            result["recorded"] = True
        except (OSError, ValueError, TypeError) as exc:
            result.update(recorded=False, reason=f"deployment evidence write failed: {exc}")
            print(json.dumps(result, ensure_ascii=False))
            return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
