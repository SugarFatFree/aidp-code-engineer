"""命令分片的定向测试读取器；显式声明所需片，不递归聚合整条流程。"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPRINT_DEV_PARTS = (
    "formal-preflight", "formal-existing", "formal-increment", "formal-docs",
    "formal-reversal", "formal-development", "formal-writeback", "formal-completion",
    "output-examples",
)


def sprint_dev_text(*parts):
    """读取测试明确依赖的权威片；拼写/缺文件立即失败，不回退旧命令正文。"""
    if not parts or any(part not in SPRINT_DEV_PARTS for part in parts):
        raise ValueError(f"必须明确指定 sprint-dev 分片：{parts!r}")
    return "\n".join((REPO / ".aidp/flows/sprint-dev" / f"{part}.md").read_text(
        encoding="utf-8") for part in parts)
