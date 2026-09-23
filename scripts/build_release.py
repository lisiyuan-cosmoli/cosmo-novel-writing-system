#!/usr/bin/env python3
"""Build a checked public ZIP and byte hashes with Python 3.9+ standard library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

from check_public_release import ReleaseError, check_repository, verify_snapshot


VERSION = "6.0"
PREFIX = "cosmo-novel-writing-system-" + VERSION
ZIP_NAME = PREFIX + ".zip"
HASH_NAME = PREFIX + ".files.json"
SUMS_NAME = "SHA256SUMS"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(repo, output_dir, deny_file=None):
    root = Path(repo).resolve(strict=True)
    output = Path(output_dir).resolve()
    if os.path.commonpath([str(root), str(output)]) == str(root):
        raise ReleaseError("output: must-be-outside-repository")
    names = (ZIP_NAME, HASH_NAME, SUMS_NAME)
    if any(os.path.lexists(str(output / name)) for name in names):
        raise ReleaseError("output: release-file-already-exists")
    snapshot = check_repository(root, deny_file)
    try:
        manifest = json.loads(snapshot["files"]["system-manifest.json"]["data"].decode("utf-8"))
        if manifest.get("system_version") != VERSION:
            raise ReleaseError("release: system-version-mismatch")
    except (KeyError, ValueError, UnicodeError, AttributeError):
        raise ReleaseError("release: invalid-or-missing-system-manifest") from None
    verify_snapshot(snapshot)
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir() or output.resolve() != output:
        raise ReleaseError("output: changed-or-invalid-directory")
    output_identity = (output.stat().st_dev, output.stat().st_ino)
    published = []
    try:
        with tempfile.TemporaryDirectory(prefix=".cosmo-release-", dir=str(output)) as temporary:
            stage = Path(temporary)
            records = []
            with zipfile.ZipFile(stage / ZIP_NAME, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for rel, entry in sorted(snapshot["files"].items()):
                    info = zipfile.ZipInfo(PREFIX + "/" + rel, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = (stat.S_IFREG | entry["mode"]) << 16
                    archive.writestr(info, entry["data"])
                    records.append({"path": rel, "bytes": len(entry["data"]),
                                    "mode": "%04o" % entry["mode"], "sha256": entry["sha256"]})
            hashes = {"format": "cosmo-release-hashes-v1", "system_version": VERSION,
                      "archive": ZIP_NAME, "top_level": PREFIX, "files": records}
            (stage / HASH_NAME).write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
            (stage / SUMS_NAME).write_text("".join("%s  %s\n" % (digest(stage / name), name)
                                                   for name in (ZIP_NAME, HASH_NAME)), encoding="ascii")
            # All archive bytes and per-file hashes came from one checked read.
            # Refuse publication if files or directory membership changed while packing.
            verify_snapshot(snapshot)
            if (output.resolve() != output or
                    (output.stat().st_dev, output.stat().st_ino) != output_identity):
                raise ReleaseError("output: changed-during-build")
            # Hard-link creation is exclusive: unlike replace(), it cannot overwrite
            # a destination created after our initial existence check.
            for name in names:
                final = output / name
                source_info = (stage / name).stat()
                os.link(str(stage / name), str(final))
                published.append((final, source_info.st_dev, source_info.st_ino))
        return [output / name for name in names]
    except BaseException:
        for path, device, inode in reversed(published):
            try:
                current = path.lstat()
                if current.st_dev == device and current.st_ino == inode:
                    path.unlink()
            except FileNotFoundError:
                pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", required=True, help="Destination directory outside the repository.")
    parser.add_argument("--deny-file", help="External UTF-8 deny list; one phrase per line.")
    args = parser.parse_args(argv)
    try:
        paths = build(args.repo, args.output_dir, args.deny_file)
    except (ReleaseError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(str(exc) if isinstance(exc, ReleaseError) else "build: filesystem-or-input-error", file=sys.stderr)
        return 1
    for path in paths:
        print("WROTE " + path.name)
    print("Checks cover known patterns; review the public file list and release contents before publishing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
