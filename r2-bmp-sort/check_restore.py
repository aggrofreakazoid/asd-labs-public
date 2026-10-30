#!/usr/bin/env python3
"""
Чекер для check.py (compare=checker): сравнивает восстановленное решением
изображение с эталоном через bmpshuffle check.

Вызывается как:  check_restore.py <shuffled.bmp> <source.bmp> <restored>
(shuffled.bmp — сам вход, не используется; source.bmp — эталон/expected;
restored — то, что записало решение).

При отсутствии собранного bmpshuffle собирает его один раз (go build).
Размер группы фиксирован и должен совпадать с тем, что использовался при
генерации tests/public (см. task.md/io-format.md) — отдельного канала для
передачи -group через check.py нет, в этом нет нужды, пока он один для всех
публичных фикстур.
"""
import subprocess
import sys
from pathlib import Path

GROUP = 8

def main():
    _shuffled, source, restored = sys.argv[1:4]

    here = Path(__file__).resolve().parent
    tool_dir = here / "tools" / "bmpshuffle"
    binary = tool_dir / "bmpshuffle"

    if not binary.exists():
        build = subprocess.run(["go", "build", "-o", str(binary), "."],
                                cwd=tool_dir, capture_output=True, text=True)
        if build.returncode != 0:
            sys.stderr.write(build.stderr)
            sys.exit(1)

    r = subprocess.run(
        [str(binary), "check", "-orig", source, "-got", restored, "-group", str(GROUP)],
        capture_output=True, text=True,
    )
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    sys.exit(r.returncode)

if __name__ == "__main__":
    main()
