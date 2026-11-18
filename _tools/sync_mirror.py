# -*- coding: utf-8 -*-
"""把 novel-scan 仓库镜像到 ~/.workbuddy/skills/novel-scan 并逐字节校验。"""
import filecmp
import os
import shutil

SRC = r"C:\Users\guohuiyuan\code\aiwork\novel-scan"
DST = os.path.expanduser("~/.workbuddy/skills/novel-scan")
SKIP_DIRS = {".git", "__pycache__"}
SKIP_FILES = {".gitignore", "LICENSE"}
SKIP_EXT = (".docx",)


def main():
    copied, same = [], 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, SRC)
        for f in files:
            if f in SKIP_FILES or f.startswith("~$") or f.endswith(SKIP_EXT):
                continue
            s = os.path.join(root, f)
            r = os.path.normpath(os.path.join(DST, rel, f))
            os.makedirs(os.path.dirname(r), exist_ok=True)
            if os.path.exists(r) and filecmp.cmp(s, r, shallow=False):
                same += 1
                continue
            shutil.copy2(s, r)
            copied.append(os.path.join(rel, f))
    print(f"[mirror] 复制 {len(copied)} 个文件，{same} 个已一致")

    # 反查：目标目录里多出来的文件（源里已删）
    extra = []
    for root, dirs, files in os.walk(DST):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, DST)
        for f in files:
            if f in SKIP_FILES or f.startswith("~$") or f.endswith(SKIP_EXT):
                continue
            if not os.path.exists(os.path.join(SRC, rel, f)):
                extra.append(os.path.join(rel, f))
    for x in extra:
        p = os.path.normpath(os.path.join(DST, x))
        os.remove(p)
        print(f"[mirror] 删除镜像多余文件 {x}")

    # 逐字节复核
    bad = []
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, SRC)
        for f in files:
            if f in SKIP_FILES or f.startswith("~$") or f.endswith(SKIP_EXT):
                continue
            s = os.path.join(root, f)
            r = os.path.join(DST, rel, f)
            if not (os.path.exists(r) and filecmp.cmp(s, r, shallow=False)):
                bad.append(os.path.join(rel, f))
    print("[mirror] 不一致：" + ("无  ✅" if not bad else str(bad)))


if __name__ == "__main__":
    main()
