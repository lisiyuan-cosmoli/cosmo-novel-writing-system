#!/usr/bin/env python3
"""Check an explicitly maintained public file list. Python 3.9+, standard library.

This checks known paths and content patterns, not the absence of every possible
secret or unpublished passage. Git metadata and Python caches are not inspected
or released. Keep any private deny list outside the repository.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


PUBLIC_LIST = "scripts/public-files.json"
LIST_FORMAT = "cosmo-public-files-v1"
IGNORED_DIRS = {"__pycache__", ".pytest_cache"}
FORBIDDEN_DIRS = {
    ".novel", "_候选", "_读取包", "_快照", "_备份", "_to_delete", "_候选存根",
    ".ssh", ".aws", ".gnupg", ".azure", ".venv", "venv", ".idea", ".vscode",
}
PRIVATE_TABLES = {
    "_工具/专名表.txt", "_工具/AI腔词表_本项目.txt", "_工具/允许AI腔.txt",
    "_工具/允许重复.txt", "_工具/母版禁词.txt",
}
PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("access-token", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
        r"|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|sk_live_[A-Za-z0-9]{20,}"
        r"|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}"
        r"|AIza[0-9A-Za-z_-]{35})\b")),
    ("credential-assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
        r"\s*[=:]\s*[\"'][A-Za-z0-9_+/.=-]{16,}[\"']")),
    ("credential-url", re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]+:[^\s/@]+@")),
    ("private-home-path", re.compile(
        r"/(?:Users|home)/[^/\s<>\"'`]+|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s<>\"'`]+")),
    ("personal-email", re.compile(
        r"(?i)[A-Z0-9._%+-]+@(?:gmail|googlemail|qq|163|126|icloud|outlook|hotmail|yahoo)\.com\b")),
)


class ReleaseError(Exception):
    """Messages contain locations/categories only, never matched content."""


def location(rel, category, line=None):
    name = json.dumps(str(rel), ensure_ascii=False)
    return "%s%s: %s" % (name, ":%d" % line if line else "", category)


def signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def ignored(rel, is_dir):
    parts = PurePosixPath(rel).parts
    return (parts[0] == ".git" or any(p in IGNORED_DIRS for p in parts)
            or (not is_dir and parts[-1].endswith((".pyc", ".pyo"))))


def forbidden(rel):
    parts = PurePosixPath(rel).parts
    name = parts[-1]
    if any(p in FORBIDDEN_DIRS or p.startswith(".新建项目-") for p in parts):
        return True
    if (name in {".DS_Store", "Thumbs.db", "desktop.ini", ".netrc", ".npmrc",
                 "credentials.json", "service-account.json", "id_rsa", "id_ed25519"}
            or name == "project.json" or name.startswith("project.json.")
            or name.startswith((".env", "._"))
            or name.lower().endswith((".pem", ".key", ".p12", ".pfx", ".kdbx",
                                      ".zip", ".tar", ".tgz", ".gz", ".7z", ".rar",
                                      ".bak", ".backup"))):
        return True
    if len(parts) > 1 and parts[0] == "05_正文":
        return len(parts) != 2 or (name != "README.md" and not name.endswith("_空白模板.md"))
    if len(parts) > 1 and parts[0] == "06_归档":
        return len(parts) != 2 or (name not in {"README.md", "开书决策记录.md", "流程审计.md"}
                                  and not name.endswith("_空白模板.md"))
    return bool(re.fullmatch(r"K\d{4}(?:-K\d{4})?(?:[_.-].*)?", name))


def valid_relative(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and not value.startswith("/") and ":" not in value
            and all(p not in {"", ".", ".."} for p in value.split("/")))


def tree_state(root):
    """Record directories too, so added/deleted files and directories are noticed."""
    state, errors = {}, []

    def walk(directory, prefix=""):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            errors.append(location(prefix or ".", "unreadable-directory"))
            return
        for entry in entries:
            rel = prefix + entry.name
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                errors.append(location(rel, "unreadable-entry"))
                continue
            if stat.S_ISLNK(info.st_mode):
                errors.append(location(rel, "symbolic-link"))
                continue
            is_dir = stat.S_ISDIR(info.st_mode)
            if ignored(rel, is_dir):
                continue
            if not valid_relative(rel) or forbidden(rel):
                errors.append(location(rel, "unsafe-or-private-path"))
                continue
            if not is_dir and not stat.S_ISREG(info.st_mode):
                errors.append(location(rel, "non-regular-file"))
                continue
            if info.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
                errors.append(location(rel, "special-file-mode"))
            state[rel] = signature(info)
            if is_dir:
                walk(entry.path, rel + "/")

    walk(root)
    if errors:
        raise ReleaseError("\n".join(errors))
    return state


def read_stable(path, expected, rel):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        with os.fdopen(os.open(str(path), flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or signature(before) != expected:
                raise ReleaseError(location(rel, "file-changed-before-read"))
            data = handle.read()
            after = os.fstat(handle.fileno())
        if signature(after) != expected or signature(path.lstat()) != expected:
            raise ReleaseError(location(rel, "file-changed-during-read"))
        return data
    except OSError:
        raise ReleaseError(location(rel, "cannot-read-stable-file")) from None


def read_deny_file(path, root):
    if path is None:
        return [], None
    try:
        original = Path(path).absolute()
        if original.is_symlink():
            raise ReleaseError("external-deny-file: symbolic-link")
        source = original.resolve(strict=True)
        if os.path.commonpath([str(root), str(source)]) == str(root):
            raise ReleaseError("external-deny-file: must-be-outside-repository")
        sig = signature(source.lstat())
        raw = read_stable(source, sig, "external-deny-file")
        words = [line.strip() for line in raw.decode("utf-8-sig").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        return words, (source, sig, hashlib.sha256(raw).hexdigest())
    except (OSError, UnicodeError, ValueError):
        raise ReleaseError("external-deny-file: unreadable-or-invalid") from None


def scan_content(rel, data, deny_words):
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = data.decode(encoding, errors="replace")
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        for category, pattern in PATTERNS:
            if pattern.search(line):
                errors.append(location(rel, category, number))
        if any(word in line for word in deny_words):
            errors.append(location(rel, "external-deny-match", number))
        if rel in PRIVATE_TABLES and line.strip() and not line.lstrip().startswith("#"):
            errors.append(location(rel, "nonempty-project-private-table", number))
    return errors


def check_repository(repo, deny_file=None):
    root = Path(repo).resolve(strict=True)
    if not root.is_dir():
        raise ReleaseError("repository: not-a-directory")
    state = tree_state(root)
    if PUBLIC_LIST not in state or not stat.S_ISREG(state[PUBLIC_LIST][2]):
        raise ReleaseError(location(PUBLIC_LIST, "missing-file-list"))
    list_data = read_stable(root / PUBLIC_LIST, state[PUBLIC_LIST], PUBLIC_LIST)
    try:
        config = json.loads(list_data.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ReleaseError(location(PUBLIC_LIST, "invalid-json")) from None
    if (not isinstance(config, dict) or config.get("format") != LIST_FORMAT
            or not isinstance(config.get("files"), list)):
        raise ReleaseError(location(PUBLIC_LIST, "invalid-file-list-format"))
    allowed = config["files"]
    if (any(not valid_relative(p) or forbidden(p) or ignored(p, False) for p in allowed)
            or len(set(allowed)) != len(allowed) or PUBLIC_LIST not in allowed):
        raise ReleaseError(location(PUBLIC_LIST, "unsafe-duplicate-or-unlisted-self"))
    actual = {p for p, sig in state.items() if stat.S_ISREG(sig[2])}
    errors = [location(p, "unlisted-file") for p in sorted(actual - set(allowed))]
    errors += [location(p, "listed-file-missing") for p in sorted(set(allowed) - actual)]
    if errors:
        raise ReleaseError("\n".join(errors))
    words, deny_state = read_deny_file(deny_file, root)
    files = {}
    for rel in sorted(allowed):
        data = list_data if rel == PUBLIC_LIST else read_stable(root / rel, state[rel], rel)
        errors.extend(scan_content(rel, data, words))
        files[rel] = {"data": data, "mode": stat.S_IMODE(state[rel][2]),
                      "sha256": hashlib.sha256(data).hexdigest()}
    if tree_state(root) != state:
        errors.append("repository: changed-during-check")
    if errors:
        raise ReleaseError("\n".join(errors))
    result = {"root": root, "state": state, "files": files, "deny_state": deny_state}
    verify_snapshot(result)
    return result


def verify_snapshot(snapshot):
    """Recheck identities, modes, byte hashes, and directory membership."""
    root, state = snapshot["root"], snapshot["state"]
    if tree_state(root) != state:
        raise ReleaseError("repository: changed-since-check")
    for rel, entry in snapshot["files"].items():
        data = read_stable(root / rel, state[rel], rel)
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ReleaseError(location(rel, "content-changed-since-check"))
    if tree_state(root) != state:
        raise ReleaseError("repository: changed-during-recheck")
    if snapshot["deny_state"]:
        source, sig, digest = snapshot["deny_state"]
        if hashlib.sha256(read_stable(source, sig, "external-deny-file")).hexdigest() != digest:
            raise ReleaseError("external-deny-file: changed-since-check")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--deny-file", help="External UTF-8 deny list; one phrase per line.")
    args = parser.parse_args(argv)
    try:
        result = check_repository(args.repo, args.deny_file)
    except (ReleaseError, OSError, ValueError) as exc:
        print(str(exc) if isinstance(exc, ReleaseError) else "check: filesystem-or-input-error", file=sys.stderr)
        return 1
    print("PASS: %d listed files; known path/content checks passed." % len(result["files"]))
    print("Scope: no Git history/cache scan; this does not prove absence of all private content.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
