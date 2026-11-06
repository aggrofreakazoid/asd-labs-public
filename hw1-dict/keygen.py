#!/usr/bin/env python3
"""
Генератор ключей для бенчмарка ДЗ1 (нагрузки А и Б). Печатает в stdout N
различных ключей, по одному на строку.

    python3 keygen.py random N [seed]   # нагрузка А: случайный порядок
    python3 keygen.py sorted N [seed]   # нагрузка Б: те же ключи по возрастанию

Ключ — 8–16 символов из [a-z0-9]. При одинаковых N и seed режим sorted
выдаёт ровно те же ключи, что random, только упорядоченные побайтово —
так нагрузки А и Б отличаются только порядком. Нагрузку В (подобранные
коллизии) вы строите сами (task.md, п. 5).
"""
import random
import sys

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def keys(n, seed):
    rng = random.Random(seed)
    seen, out = set(), []
    while len(out) < n:
        k = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(8, 16)))
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("random", "sorted"):
        sys.exit("usage: keygen.py random|sorted N [seed]")
    n = int(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    ks = keys(n, seed)
    if sys.argv[1] == "sorted":
        ks.sort(key=lambda s: s.encode())
    sys.stdout.write("\n".join(ks) + ("\n" if ks else ""))


if __name__ == "__main__":
    main()
