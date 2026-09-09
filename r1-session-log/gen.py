#!/usr/bin/env python3
"""
Генератор входа для замеров Р1. Печатает в stdout журнал из N корректно вложенных
пар LOGIN/LOGOUT (сбалансированные скобки), время обработки которого линейно по N.

    python3 gen.py 10000 [seed]

Проверяющий скрипт вызывает генератор сам; ручной запуск нужен, только если вы
хотите свои файлы для отчёта.
"""
import random
import sys

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rng = random.Random(seed)
    out = []
    stack = []
    events = n
    for _ in range(events):
        # открываем новую сессию либо закрываем последнюю, сохраняя вложенность
        if stack and (len(stack) > 30 or rng.random() < 0.5):
            name = stack.pop()
            out.append(f"LOGOUT {name}")
        else:
            name = f"u{rng.randrange(1_000_000)}"
            stack.append(name)
            out.append(f"LOGIN {name}")
    while stack:
        out.append(f"LOGOUT {stack.pop()}")
    sys.stdout.write("\n".join(out) + "\n")

if __name__ == "__main__":
    main()
