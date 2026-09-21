#!/usr/bin/env python3
"""
Генератор входа для Р1, расширение «транзакции аудита» (контракт — см.
io-format-advanced.md): вложенный журнал (как gen.py), со случайно
расставленными BEGIN/COMMIT/ROLLBACK. Транзакции не вложены, как того
требует контракт.

В отличие от первой версии этого генератора, поток строится «вживую»:
каждое решение (открыть сессию, закрыть верхнюю, начать транзакцию,
закрыть её commit'ом или rollback'ом) принимается по фактическому текущему
состоянию стека, а не по заранее заготовленному плану. Это принципиально:
ROLLBACK может вернуть на стек сессию, уже считавшуюся закрытой раньше
(«воскресить» её) — если бы события ниже по потоку были спланированы
заранее в предположении, что эта сессия ушла навсегда, они перестали бы
совпадать с вершиной стека и генератор производил бы ложные order_violation
на собственном, безошибочном по замыслу входе.

    python3 gen_tx.py N [seed] [--rollback-rate R]

N — примерное число событий LOGIN/LOGOUT в основном цикле (без учёта
BEGIN/COMMIT/ROLLBACK и без учёта финального слива стека — как в gen.py).
R — вероятность, что открытая транзакция закроется ROLLBACK, а не COMMIT
(по умолчанию 0.3).

Вход генерируется безошибочным по построению: стек всегда сходится к
пустому (все сессии в итоге закрыты), поэтому в stderr печатается только
итоговое число завершённых сессий — для сверки со своей реализацией.
"""
import random
import sys

def main():
    args = sys.argv[1:]
    rollback_rate = 0.3
    if "--rollback-rate" in args:
        idx = args.index("--rollback-rate")
        rollback_rate = float(args[idx + 1])
        del args[idx:idx + 2]
    n = int(args[0]) if len(args) > 0 else 2000
    seed = int(args[1]) if len(args) > 1 else 1
    rng = random.Random(seed)

    out = []
    stack = []          # (имя, номер_строки_login) — фактическое состояние
    counter = 0
    sessions = 0
    tx_open = False
    orig_count = None
    buf = []
    tx_steps = 0

    while sessions < n:
        if tx_open:
            tx_steps += 1
            new_open = len(stack) - orig_count
            # закрыть транзакцию можно в любой момент — commit безопасен
            # всегда; rollback безопасен, только если внутри транзакции не
            # осталось "новых" незакрытых сессий (иначе после отката для
            # них не окажется LOGIN, а разбор будет ждать LOGOUT)
            if rng.random() < 0.25 or tx_steps > 200:
                if new_open == 0 and rng.random() < rollback_rate:
                    del stack[orig_count:]
                    for item in reversed(buf):
                        stack.append(item)
                    out.append("ROLLBACK")
                else:
                    out.append("COMMIT")
                tx_open = False
                orig_count = None
                buf = []
                continue
        elif rng.random() < 0.03:
            out.append("BEGIN")
            tx_open = True
            orig_count = len(stack)
            buf = []
            tx_steps = 0
            continue

        want_close = stack and (len(stack) > 30 or rng.random() < 0.5)
        if want_close:
            was_orig = tx_open and (len(stack) == orig_count)
            name, ln = stack.pop()
            out.append(f"LOGOUT {name}")
            sessions += 1
            if was_orig:
                orig_count -= 1
                buf.append((name, ln))
        else:
            counter += 1
            name = f"u{counter}"
            ln = len(out) + 1
            out.append(f"LOGIN {name}")
            stack.append((name, ln))

    if tx_open:
        out.append("COMMIT")  # commit всегда безопасен, чем бы транзакция ни закончилась

    while stack:
        name, _ln = stack.pop()
        out.append(f"LOGOUT {name}")
        sessions += 1

    sys.stdout.write("\n".join(out) + "\n")
    print(f"# ground truth: sessions={sessions} unclosed_lines=[]", file=sys.stderr)

if __name__ == "__main__":
    main()
