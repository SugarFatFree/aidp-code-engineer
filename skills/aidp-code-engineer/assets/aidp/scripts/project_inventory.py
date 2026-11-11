#!/usr/bin/env python3
"""共享主仓、嵌套 gitlink 与运行时边界发现；不执行项目代码。"""
from pathlib import Path, PurePosixPath
import os
import subprocess
import re
import stat
import sys

# 只排除工具缓存、构建产物和安装依赖；显式必要输入可覆盖此默认过滤。
GENERATED_DIRS = frozenset(('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.cache', '.tox', '.nox', '.venv', 'venv', 'node_modules', '.next', '.nuxt',
    'dist', 'build', 'target', '.gradle', '.idea', '.vscode'))
GENERATED_SUFFIXES = frozenset(('.pyc', '.pyo', '.class', '.o', '.obj'))


def generated_excluded(rel):
    path = PurePosixPath(rel)
    return bool(set(path.parts) & GENERATED_DIRS) or path.suffix in GENERATED_SUFFIXES


def installed_skill_package(root, rel):
    """只识别约定安装根且带SKILL.md的包，不把业务同名目录当工具包。"""
    path = PurePosixPath(rel)
    for home in ('.', '.aidp', '.agents', '.claude', '.codex', '.dsh'):
        base = PurePosixPath(home) / 'skills'
        if not path.is_relative_to(base):
            continue
        parts = path.relative_to(base).parts
        if parts:
            package = base / parts[0]
            if (Path(root) / package / 'SKILL.md').is_file():
                return package.as_posix()
    return None


def _stat_identity(path):
    """保留链接本体及真实目标身份；不存在也是可比较的观测值。"""
    def values(value):
        return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns]
    try:
        own = path.lstat()
    except FileNotFoundError:
        return {'missing': True}
    result = {'stat': values(own)}
    if stat.S_ISLNK(own.st_mode):
        result['link'] = os.readlink(path)
        result['target'] = str(path.resolve())
        try:
            result['target_stat'] = values(path.stat())
        except FileNotFoundError:
            result['target_stat'] = None
    return result


def fingerprint_metadata():
    """每个取证阶段只读取一次挂载/启动元数据；调用方不得跨执行阶段保留。"""
    if sys.platform != 'linux':
        return None
    try:
        mounts = []
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            left, right = line.split(' - ', 1)
            fields, filesystem = left.split(), right.split()[0]
            mount = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4]))
            mounts.append((mount, filesystem, fields[:6]))
        return {'mounts': mounts, 'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, ValueError, IndexError):
        return None


def fingerprint_token(path, *, metadata=None):
    """仅可信 Linux 本地纳秒 ctime 文件系统允许跳过内容读取。

    前提是内核维护 inode/ctime，非特权进程不能恢复 ctime；不支持特权篡改、
    文件系统快照回滚或网络/FUSE 元数据缓存。未知平台/文件系统必须返回 None。
    每阶段重读 mountinfo/boot_id，禁止跨重启、换挂载或仅凭 mtime 复用。
    """
    metadata = fingerprint_metadata() if metadata is None else metadata
    if not metadata:
        return None
    path = Path(path).absolute()
    try:
        def reliable(target):
            candidates = [item for item in metadata['mounts'] if target.is_relative_to(item[0])]
            selected = max(candidates, key=lambda item: len(item[0].parts))
            if selected[1] not in ('ext4', 'xfs', 'btrfs', 'tmpfs'):
                return None
            return selected[2]
        resolved = path.resolve()
        mount = reliable(resolved)
        own_mount = reliable(path.parent.resolve() / path.name)
        if mount is None or own_mount is None:
            return None
        state = _stat_identity(path)
        identities = [state.get('stat'), state.get('target_stat')]
        # 秒级时间精度/无真实 inode 的文件系统不具备本优化的可靠前提。
        if any(item is not None and (not item[1] or not item[5] % 1_000_000_000) for item in identities):
            return None
        return {'policy': 'linux-local-ctime-v1', 'boot': metadata['boot'],
                'mount': mount, 'own_mount': own_mount, 'path': str(path), 'resolved': str(resolved), **state}
    except (OSError, ValueError, IndexError):
        return None


def fingerprint_file(path, previous=None, reader=None, *, metadata=None):
    """复用稳定内容摘要；未命中时实际读取，并拒绝读取过程中发生的 ABA/替换。"""
    path = Path(path)
    before_state = _stat_identity(path)
    before = fingerprint_token(path, metadata=metadata)
    if (before is not None and isinstance(previous, dict) and previous.get('token') == before
            and 'hash' in previous):
        if _stat_identity(path) != before_state:
            raise InventoryError('TREE_CHANGED：指纹复用期间文件变化：' + str(path))
        return {'hash': previous['hash'], 'token': before, 'read': False, 'observation': before_state}
    if before_state.get('missing'):
        value, read = None, False
    else:
        if reader is None:
            from test_ledger import file_hash
            reader = file_hash
        value, read = reader(path), True
    after = fingerprint_token(path, metadata=metadata)
    if _stat_identity(path) != before_state or before != after:
        raise InventoryError('TREE_CHANGED：读取期间文件变化，不能复用旧证据：' + str(path))
    return {'hash': value, 'token': after, 'read': read, 'observation': before_state}

class InventoryError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.status = "BUDGET_EXCEEDED" if message.startswith("BUDGET_EXCEEDED") else "UNVERIFIED"

def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)

def runtime_excluded(rel):
    parts = PurePosixPath(rel).parts
    if ".git" in parts:
        return True
    # 仅工具自有目录，不排除任意名为 memory/docs 的业务目录。
    for i, part in enumerate(parts):
        if part == ".aidp" and i and parts[i - 1] == "memory":
            return True
        if part in (".aidp", ".agents", ".claude", ".codex", ".dsh") and i + 1 < len(parts) and parts[i + 1] in ("runtime", "test-ledger", "test-scopes"):
            return True
    return False

def default_excluded(rel, repositories=(".",)):
    if runtime_excluded(rel) or generated_excluded(rel):
        return True
    path = PurePosixPath(rel)
    for repo in repositories:
        base = PurePosixPath(repo)
        if path.is_relative_to(base):
            parts = path.relative_to(base).parts
            if parts and (parts[0] in ("docs", "memory") or
                          len(parts) == 1 and parts[0] in ("CLAUDE.md", "AGENTS.md", "README.md")):
                return True
    return False

def classify_changes(paths, inputs=(), repositories=(".",)):
    """将观察到的变化按真实输入/源码/默认忽略运行态分组；不把业务嵌套 docs 当运行态。"""
    groups = {"source": [], "input": [], "runtime_only": []}
    for path in sorted(set(paths)):
        explicit = any(path == item or path.startswith(item + "/") for item in inputs)
        kind = "runtime_only" if runtime_excluded(path) else ("input" if explicit else
                "runtime_only" if default_excluded(path, repositories) else "source")
        groups[kind].append(path)
    return groups


def git_worktree_inventory(root, since=None, max_files=None):
    """递归列出主仓和已初始化子模块的文件及既有脏改动，路径相对主仓。

    gitlinks 单独保留父仓 HEAD/索引 pin 和子仓 HEAD；目录绝不伪装文件摘要。
    尚未初始化、不可读取的 pin 或冲突索引均明确未核验，不返回不完整快照。
    """
    root = Path(root).resolve()
    files, dirty, gitlinks = set(), set(), {}
    repositories = []

    def command(repo, *args):
        result = _git(repo, *args)
        if result.returncode:
            rel = repo.relative_to(root).as_posix()
            raise InventoryError(f"UNVERIFIED：无法完整读取 Git 工作树/子模块或 pin：{rel}")
        return result.stdout

    def relative(repo, value):
        name = PurePosixPath(value)
        if not value or name.is_absolute() or ".." in name.parts or ".git" in name.parts:
            raise InventoryError(f"UNVERIFIED：Git 文件清单含非法路径：{value}")
        path = repo / value
        if runtime_excluded(path.relative_to(root).as_posix()):
            return None
        return path.relative_to(root).as_posix()

    def tree_links(repo, revision):
        links = {}
        if revision:
            for row in command(repo, "ls-tree", "-r", "-z", revision).split(b"\0"):
                if row:
                    metadata, name = row.split(b"\t", 1)
                    mode, _, oid = metadata.split()
                    if mode == b"160000":
                        links[os.fsdecode(name)] = oid.decode("ascii")
        return links

    def visit(repo, inherited_pin=None, new_module=False):
        if repo != root:
            if not repo.resolve().is_relative_to(root):
                raise InventoryError("UNVERIFIED：子模块越出 root")
            if not os.path.lexists(repo / ".git"):
                raise InventoryError(f"UNVERIFIED：子模块未初始化或代码缺失：{repo.relative_to(root)}")
        observed = command(repo, "rev-parse", "--show-toplevel")
        if Path(os.fsdecode(observed).strip()).resolve() != repo:
            raise InventoryError(f"UNVERIFIED：子模块未初始化：{repo.relative_to(root)}")
        head_probe = _git(repo, "rev-parse", "--verify", "HEAD^{commit}")
        head = head_probe.stdout.decode().strip() if head_probe.returncode == 0 else None
        if repo != root and head is None:
            raise InventoryError(f"UNVERIFIED：子模块 HEAD 不可读：{repo.relative_to(root)}")
        repositories.append(repo.relative_to(root).as_posix())
        index_links = {}
        for row in command(repo, "ls-files", "--stage", "-z").split(b"\0"):
            if not row:
                continue
            metadata, name = row.split(b"\t", 1)
            mode, oid, stage = metadata.split()
            if stage != b"0":
                raise InventoryError(f"UNVERIFIED：Git 索引尚有未解决冲突：{repo.relative_to(root)}")
            if mode == b"160000":
                index_links[os.fsdecode(name)] = oid.decode("ascii")
        committed_links = tree_links(repo, head)
        # 祖先 gitlink 仍指旧提交时，其内部子模块的旧 pin 也要继续向下传递。
        prior_links = tree_links(repo, inherited_pin) if inherited_pin else committed_links
        all_links = set(index_links) | set(committed_links) | set(prior_links)
        names = {os.fsdecode(name) for name in command(
            repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0") if name}
        local_dirty = set()
        rows = iter(command(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                            "--ignore-submodules=none").split(b"\0"))
        for row in rows:
            if not row:
                continue
            local_dirty.add(os.fsdecode(row[3:]))
            if b"R" in row[:2] or b"C" in row[:2]:
                original = next(rows, None)
                if not original:
                    raise InventoryError("UNVERIFIED：Git 重命名状态记录不完整")
                local_dirty.add(os.fsdecode(original))
        if inherited_pin and inherited_pin != head:
            local_dirty.update(os.fsdecode(name) for name in command(
                repo, "diff", "--name-only", "--no-renames", "-z", inherited_pin, "HEAD", "--").split(b"\0") if name)
        if new_module:
            local_dirty.update(names)
        names.update(local_dirty)
        for name in sorted(names - all_links):
            rel = relative(repo, name.rstrip("/"))
            if rel is None:
                continue
            path = root / rel
            if path.is_dir() and not path.is_symlink():
                # 未登记的嵌套 Git 工作树也不能被目录占位吞掉。
                if os.path.lexists(path / ".git"):
                    visit(path, new_module=True)
                    continue
                raise InventoryError(f"UNVERIFIED：无法枚举 Git 目录条目：{rel}")
            files.add(rel)
            if max_files is not None and len(files) > max_files:
                raise InventoryError("BUDGET_EXCEEDED：文件发现超出扫描预算")
            if name in local_dirty or new_module:
                dirty.add(rel)
        for name in sorted(all_links):
            rel = relative(repo, name)
            if rel is None:
                raise InventoryError("UNVERIFIED：子模块不能位于运行时目录")
            child = repo / name
            pin = prior_links.get(name) or committed_links.get(name) or index_links.get(name)
            visit(child, inherited_pin=pin, new_module=new_module or name not in prior_links)
            child_head = command(child, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
            gitlinks[rel] = {"index": index_links.get(name), "committed": committed_links.get(name),
                             "head": child_head}
        return head

    visit(root, inherited_pin=since)
    return {"files": sorted(files), "preexisting_dirty": sorted(dirty), "gitlinks": gitlinks,
            "repositories": sorted(repositories),
            "source_roots": sorted({str(parent) for p in files for parent in PurePosixPath(p).parents if parent.name in ("src", "lib")}),
            "test_roots": sorted({str(parent) for p in files for parent in PurePosixPath(p).parents if parent.name in ("tests", "test", "__tests__")})}


# 简短公共入口，兼容调用方命名。
inventory = git_worktree_inventory
