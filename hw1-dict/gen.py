#!/usr/bin/env python3
"""
Вход для прикидочных замеров ДЗ1 (python3 ../check.py hw1-dict --bench):
N команд INSERT случайных ключей, затем N команд FIND тех же ключей.

    python3 gen.py N [seed]

Для отчёта этого мало: бенчмарк по протоколу С2 вы пишете сами (task.md, п. 4).
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keygen import keys  # noqa: E402


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ks = keys(n, seed)
    rng = random.Random(seed + 1)
    out = [f"INSERT {k} {rng.randrange(-10**9, 10**9)}" for k in ks]
    rng.shuffle(ks)
    out += [f"FIND {k}" for k in ks]
    print("\n".join(out))


if __name__ == "__main__":
    main()
