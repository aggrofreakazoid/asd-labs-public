#!/usr/bin/env python3
"""
Генератор входа для Р1, повышенный уровень: настоящий журнал с
пересекающимися сессиями (один пользователь вошёл раньше другого, но вышел
позже). В отличие от gen.py, LOGOUT закрывает случайную из уже открытых
сессий, а не обязательно последнюю — сессии специально не вложены.

Вход полностью корректен в терминах io-format.md: имена уникальны (каждый
пользователь логинится и разлогинивается ровно один раз), поэтому
правильное решение (словарь стеков по пользователям) должно вернуть 0
ошибок и ровно N завершённых сессий. Наивная модель с одним общим стеком
на этом входе, наоборот, почти всегда даёт поток order_violation, хотя
ничего некорректного не произошло — это и есть демонстрация границы
применимости.

    python3 gen_overlap.py N [seed] [--timestamps]

Печатает журнал (2*N строк) в stdout. В stderr отдельно печатает эталонный
пик одновременно активных сессий и строку, на которой он впервые достигнут
— для расширения «статистика активности»: пик считается по тем же LOGIN/
LOGOUT, без изменения формата входа, так что сверить свою реализацию с этим
числом можно уже сейчас.

--timestamps переключает вывод на диалект с отметками времени из
io-format-advanced.md (LOGIN/LOGOUT <имя> <время>, третий токен — целые
неубывающие такты) и дополнительно печатает в stderr эталонную среднюю
длительность сессии.
"""
import random
import sys

def main():
    args = sys.argv[1:]
    timestamps = "--timestamps" in args
    args = [a for a in args if a != "--timestamps"]
    n = int(args[0]) if len(args) > 0 else 10000
    seed = int(args[1]) if len(args) > 1 else 1
    rng = random.Random(seed)
    out = []
    open_users = []      # username -> line index (peak-момент) в порядке открытия
    login_tick = {}
    counter = 0
    to_open = n
    to_close = n
    active = 0
    peak = 0
    peak_line = 0
    line_no = 0
    tick = 0
    duration_sum = 0
    while to_close > 0:
        # держим не меньше двух открытых сессий, когда возможно — иначе
        # закрывать нечего кроме последней, и вход выродится в вложенный
        want_open = to_open > 0 and (len(open_users) < 2 or rng.random() < 0.5)
        line_no += 1
        tick += rng.randint(0, 3)  # неубывающий, допускает одновременные события
        suffix = f" {tick}" if timestamps else ""
        if want_open:
            counter += 1
            name = f"u{counter}"
            open_users.append(name)
            out.append(f"LOGIN {name}{suffix}")
            login_tick[name] = tick
            to_open -= 1
            active += 1
            if active > peak:
                peak, peak_line = active, line_no
        else:
            idx = rng.randrange(len(open_users))  # не обязательно последний — здесь и есть пересечение
            name = open_users.pop(idx)
            out.append(f"LOGOUT {name}{suffix}")
            duration_sum += tick - login_tick.pop(name)
            to_close -= 1
            active -= 1
    sys.stdout.write("\n".join(out) + "\n")
    print(f"# ground truth: peak_concurrent={peak} at line={peak_line}", file=sys.stderr)
    if timestamps:
        avg = duration_sum / n
        print(f"# ground truth: avg_duration={avg:.3f}", file=sys.stderr)

if __name__ == "__main__":
    main()
