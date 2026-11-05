#!/usr/bin/env python
"""Compare the current Data/ folder against the reference zip of original data files.

Usage (from anywhere):
    python Data/check_data.py                      # uses the single *.zip next to this script
    python Data/check_data.py --zip other.zip
    python Data/check_data.py --ignore "Results/*" --ignore "*.log"
    python Data/check_data.py --show-new           # also list files not in the zip
    python Data/check_data.py --show-same        # also list identical files

Files are compared by size first, then by CRC32 (the zip stores the CRC32 of
every member, so the zip never needs to be extracted).

Categories:
    CHANGED  file exists in both, content differs
    MISSING  file is in the zip but not on disk
    NEW      file is on disk but not in the zip (only shown with --show-new)

Exit code: 0 = identical, 1 = differences found, 2 = usage / zip error.
"""
import argparse
import fnmatch
import sys
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Always skipped (OS junk and this script's own artefacts)
DEFAULT_IGNORE = [".DS_Store", "Thumbs.db", "desktop.ini", "__MACOSX/*", "__pycache__/*", "*.pyc",
                  "manifest.json", ".gitignore", "README.md"]


def crc32_of(path, chunk=1 << 20):
    crc = 0
    with open(path, "rb") as f:
        while block := f.read(chunk):
            crc = zlib.crc32(block, crc)
    return crc & 0xFFFFFFFF


def ignored(rel, patterns):
    name = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns)


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def zip_date(dt):
    """Zip member timestamp (local time, 2 s resolution) as text."""
    return datetime(*dt).strftime("%Y-%m-%d %H:%M")


def disk_date(path):
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def find_zip():
    zips = sorted(HERE.glob("*.zip"))
    if len(zips) == 1:
        return zips[0]
    sys.exit(f"Expected exactly one .zip in {HERE} (found {len(zips)}); use --zip.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", type=Path, help="reference zip (default: the only .zip next to this script)")
    ap.add_argument("--root", type=Path, default=HERE, help="folder to check (default: folder of this script)")
    ap.add_argument("--ignore", action="append", default=[], metavar="PATTERN",
                    help="extra glob pattern to ignore (matched on relative path and file name); repeatable")
    ap.add_argument("--show-new", action="store_true",
                    help="also report files on disk that are not in the zip "
                         "(hidden by default; then they do not count as differences)")
    ap.add_argument("--show-same", action="store_true", help="also list unchanged files")
    args = ap.parse_args()

    zip_path = (args.zip or find_zip()).resolve()
    root = args.root.resolve()
    if not zip_path.is_file():
        sys.exit(f"Zip not found: {zip_path}")
    patterns = DEFAULT_IGNORE + args.ignore

    # Reference: relative posix path -> (size, crc)
    ref = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            rel = info.filename.replace("\\", "/")
            if info.is_dir() or ignored(rel, patterns):
                continue
            ref[rel] = (info.file_size, info.CRC, zip_date(info.date_time))

    # Current files on disk (excluding the zip itself and this script)
    skip = {zip_path, Path(__file__).resolve()}
    cur = {}
    for p in root.rglob("*"):
        if p.is_file() and p.resolve() not in skip:
            rel = p.relative_to(root).as_posix()
            if not ignored(rel, patterns):
                cur[rel] = p

    changed, same = [], []
    for rel in sorted(ref.keys() & cur.keys()):
        size, crc, zdate = ref[rel]
        p = cur[rel]
        disk_size = p.stat().st_size
        if disk_size != size or crc32_of(p) != crc:
            changed.append((rel, size, disk_size, zdate, disk_date(p)))
        else:
            same.append(rel)
    missing = sorted(ref.keys() - cur.keys())
    new = sorted(cur.keys() - ref.keys())

    print(f"Zip:    {zip_path.name}  ({len(ref)} files)")
    print(f"Folder: {root}  ({len(cur)} files)\n")

    if changed:
        print(f"CHANGED ({len(changed)}):")
        for rel, zs, ds, zd, dd in changed:
            print(f"  ~ {rel}")
            print(f"      original (zip): {fmt_size(zs):>9}  {zd}")
            print(f"      current (disk): {fmt_size(ds):>9}  {dd}  (last changed)")
    if missing:
        print(f"MISSING from disk ({len(missing)}):")
        for rel in missing:
            print(f"  - {rel}   [{fmt_size(ref[rel][0])}, original {ref[rel][2]}]")
    if new and args.show_new:
        print(f"NEW, not in zip ({len(new)}):")
        for rel in new:
            print(f"  + {rel}   [{fmt_size(cur[rel].stat().st_size)}, last changed {disk_date(cur[rel])}]")
    if args.show_same and same:
        print(f"UNCHANGED ({len(same)}):")
        for rel in same:
            print(f"    {rel}")

    hidden = f" ({len(new)} new files not shown, use --show-new)" if new and not args.show_new else ""
    if changed or missing or (new and args.show_new):
        new_txt = f"{len(new)} new" if args.show_new else f"{len(new)} new not shown (use --show-new)"
        print(f"\nSummary: {len(changed)} changed, {len(missing)} missing, {new_txt}, {len(same)} unchanged.")
        return 1
    print(f"No differences: all {len(same)} zip files match{hidden}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
