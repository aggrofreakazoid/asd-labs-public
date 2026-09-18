#!/usr/bin/env python3
"""
check.py — единый проверочный скрипт для лабораторных работ курса АиСД.

Скрипт не знает языка, на котором написано решение. Он читает манифест
solution.json (его заполняет студент), собирает программу указанной командой и
прогоняет её через тесты, сравнивая вывод с эталоном. Один и тот же скрипт
обслуживает все шесть работ; отличия каждой работы описаны в её lab.json.

Использование:
    python3 check.py r1-session-log                 # публичные тесты + устойчивость
    python3 check.py r1-session-log --public         # только публичные тесты
    python3 check.py r1-session-log --robustness      # только устойчивость к битому вводу
    python3 check.py r1-session-log --bench           # прикидочные замеры роста
    python3 check.py r1-session-log --tests /path      # свой каталог тестов (скрытые)

Коды возврата: 0 — всё пройдено, 1 — есть провалы, 2 — ошибка конфигурации.
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

# ------------------------------------------------------------------ оформление

class C:
    ok = "\033[32m"; bad = "\033[31m"; warn = "\033[33m"
    dim = "\033[2m"; bold = "\033[1m"; off = "\033[0m"
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        ok = bad = warn = dim = bold = off = ""

def head(t): print(f"\n{C.bold}{t}{C.off}")
def passed(t): print(f"  {C.ok}PASS{C.off} {t}")
def failed(t): print(f"  {C.bad}FAIL{C.off} {t}")
def note(t): print(f"  {C.dim}{t}{C.off}")

# ------------------------------------------------------------------ конфигурация

def die(msg):
    print(f"{C.bad}Ошибка конфигурации:{C.off} {msg}", file=sys.stderr)
    sys.exit(2)

def load_json(path, what):
    if not path.exists():
        die(f"не найден {what}: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{what} содержит некорректный JSON: {e}")

# ------------------------------------------------------------------ кроссплатформенный запуск процессов

def split_cmd(s):
    return shlex.split(s, posix=(os.name != "nt"))

def is_crash(returncode):
    if returncode < 0:
        return True  # POSIX: завершён сигналом
    if os.name == "nt" and returncode >= 0x80000000:
        return True  # Windows: NTSTATUS-код исключения (например, access violation)
    return False

def run_argv(argv, **kw):
    """subprocess.run с общими для проекта настройками (без shell=True)."""
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(argv, **kw)

def resolve_local_exe(argv, workdir):
    """Если argv[0] указывает на файл, реально лежащий в workdir (в том
    числе относительным именем вроде "solution.exe" или "./solution"),
    подставляет абсолютный путь.

    Нужно из-за особенности Windows: CreateProcess ищет имя программы без
    явного пути в текущей директории ПРОЦЕССА-РОДИТЕЛЯ (то есть самого
    check.py), а не в workdir, который мы передаём дочернему процессу
    параметром cwd — тот определяет только откуда стартует уже найденный
    процесс. """
    if not argv:
        return argv
    candidate = Path(workdir) / argv[0]
    if candidate.is_file():
        return [str(candidate.resolve())] + argv[1:]
    return argv

# ------------------------------------------------------------------ сборка

def build(manifest, workdir):
    cmd = manifest.get("build", "").strip()
    if not cmd:
        note("шаг сборки не задан (интерпретируемый язык?), пропускаю")
        return True
    print(f"  сборка: {C.dim}{cmd}{C.off}")
    try:
        argv = resolve_local_exe(split_cmd(cmd), workdir)
        r = run_argv(argv, cwd=workdir, capture_output=True,
                     text=True, timeout=manifest.get("build_timeout_sec", 120))
    except subprocess.TimeoutExpired:
        failed("сборка не уложилась в лимит времени")
        return False
    except FileNotFoundError as e:
        failed(f"команда сборки не найдена: {e}")
        return False
    if r.returncode != 0:
        failed("сборка завершилась с ошибкой")
        if r.stderr.strip():
            print(C.dim + "\n".join("    " + l for l in r.stderr.strip().splitlines()[:20]) + C.off)
        return False
    return True

# ------------------------------------------------------------------ запуск одного теста

def run_once(manifest, lab, workdir, in_path, out_path, timeout):
    """Запускает решение на одном входе. Возвращает (status, detail).
    status: 'ok' | 'crash' | 'timeout' | 'runerror'."""
    run_tmpl = manifest.get("run", "").strip()
    if not run_tmpl:
        die("в solution.json не задана команда run")

    io = lab.get("io", "args")
    argv = resolve_local_exe(split_cmd(run_tmpl), workdir)
    try:
        if io == "args":
            r = run_argv(argv + [str(in_path), str(out_path)], cwd=workdir,
                         capture_output=True, text=True, timeout=timeout)
            produced = out_path
        elif io == "stdio":
            with open(in_path, "rb") as fin:
                r = subprocess.run(argv, cwd=workdir, stdin=fin,
                                   capture_output=True, timeout=timeout)
            out_path.write_bytes(r.stdout)
            produced = out_path
        else:
            die(f"неизвестный режим io={io!r} в lab.json (ожидается args или stdio)")
    except subprocess.TimeoutExpired:
        return "timeout", f"превышен лимит {timeout} с"
    except FileNotFoundError as e:
        return "runerror", f"команда не найдена: {e}"
    if is_crash(r.returncode):
        detail = f"сигналом {-r.returncode}" if r.returncode < 0 else f"код {r.returncode:#x}"
        return "crash", f"аварийное завершение ({detail})"
    if r.returncode != 0:
        return "runerror", f"код возврата {r.returncode}"
    return "ok", produced

# ------------------------------------------------------------------ сравнение вывода

def norm_tokens(text):
    return text.split()

def compare(expected_path, produced_path, mode, checker, workdir, in_path):
    """Возвращает (ok, detail)."""
    if mode == "checker":
        if not checker:
            die("compare=checker, но путь к чекеру не задан в lab.json")
        argv = checker + [str(in_path), str(expected_path), str(produced_path)]
        try:
            r = run_argv(argv, cwd=workdir, capture_output=True, text=True)
        except FileNotFoundError as e:
            return False, f"чекер не найден: {e}"
        return (r.returncode == 0), (r.stdout.strip() or r.stderr.strip())

    exp = Path(expected_path).read_text(encoding="utf-8", errors="replace")
    got = Path(produced_path).read_text(encoding="utf-8", errors="replace")

    if mode == "exact":
        e = "\n".join(l.rstrip() for l in exp.rstrip("\n").splitlines())
        g = "\n".join(l.rstrip() for l in got.rstrip("\n").splitlines())
        if e == g:
            return True, ""
        return False, first_diff_line(e.splitlines(), g.splitlines())

    # mode == "tokens" (по умолчанию)
    et, gt = norm_tokens(exp), norm_tokens(got)
    if et == gt:
        return True, ""
    return False, first_diff_token(et, gt)

def first_diff_token(exp, got):
    n = max(len(exp), len(got))
    for i in range(n):
        e = exp[i] if i < len(exp) else "<нет>"
        g = got[i] if i < len(got) else "<нет>"
        if e != g:
            return f"токен #{i+1}: ожидалось {e!r}, получено {g!r}"
    return "различие в длине вывода"

def first_diff_line(exp, got):
    n = max(len(exp), len(got))
    for i in range(n):
        e = exp[i] if i < len(exp) else "<нет строки>"
        g = got[i] if i < len(got) else "<нет строки>"
        if e != g:
            return f"строка {i+1}: ожидалось {e!r}, получено {g!r}"
    return "различие в числе строк"

# ------------------------------------------------------------------ прогоны

def collect_cases(tests_dir):
    """Пары NN.in / NN.out в каталоге, по возрастанию имени."""
    cases = []
    for inp in sorted(Path(tests_dir).glob("*.in")):
        out = inp.with_suffix(".out")
        if out.exists():
            cases.append((inp, out))
    return cases

def run_public(manifest, lab, root, workdir, tests_dir, tmp):
    cases = collect_cases(tests_dir)
    if not cases:
        note(f"в {tests_dir} нет тестов вида NN.in/NN.out")
        return 0, 0
    head(f"Публичные тесты ({len(cases)})")
    ok = 0
    timeout = lab.get("run_timeout_sec", 10)
    mode = lab.get("compare", "tokens")
    checker = lab.get("checker")
    if checker:
        checker = split_cmd(checker)
        checker[0] = str((root / checker[0]).resolve())
    timeouts = 0
    for inp, exp in cases:
        if timeouts >= 3:
            note("три таймаута подряд — прекращаю прогон, вероятно бесконечный цикл")
            break
        produced = tmp / (inp.stem + ".produced")
        status, detail = run_once(manifest, lab, workdir, inp, produced, timeout)
        if status != "ok":
            failed(f"{inp.name}: {detail}")
            timeouts = timeouts + 1 if status == "timeout" else 0
            continue
        timeouts = 0
        good, why = compare(exp, produced, mode, checker, workdir, inp)
        if good:
            passed(inp.name); ok += 1
        else:
            failed(f"{inp.name}: {why}")
    return ok, len(cases)

def run_robustness(manifest, lab, workdir, rob_dir, tmp):
    inputs = sorted(Path(rob_dir).glob("*.in"))
    if not inputs:
        note(f"в {rob_dir} нет входов устойчивости")
        return 0, 0
    head(f"Устойчивость к враждебному вводу ({len(inputs)})")
    note("программа обязана не падать и не зависать: допустим любой аккуратный выход,")
    note("недопустимы аварийное завершение сигналом и превышение лимита времени.")
    ok = 0
    timeout = lab.get("run_timeout_sec", 10)
    for inp in inputs:
        produced = tmp / (inp.stem + ".produced")
        status, detail = run_once(manifest, lab, workdir, inp, produced, timeout)
        if status in ("ok", "runerror"):
            passed(f"{inp.name}: пережила ({detail if status=='runerror' else 'штатно'})")
            ok += 1
        else:
            failed(f"{inp.name}: {detail}")
    return ok, len(inputs)

def run_bench(manifest, lab, root, workdir, tmp):
    bench = lab.get("bench")
    if not bench:
        note("для этой работы замеры в конфиге не описаны")
        return
    gen = bench.get("generator")
    sizes = bench.get("sizes", [])
    expected = bench.get("expected", "n")
    if not gen or not sizes:
        note("в bench не хватает generator или sizes")
        return
    gen_path = (root / gen).resolve()
    head("Прикидочные замеры роста")
    note("это грубая проверка формы кривой по времени всего процесса, включая старт;")
    note("она не заменяет замеров внутри программы по протоколу курса.")
    timeout = lab.get("run_timeout_sec", 10) * 6
    print(f"\n  {'n':>10}  {'время, с':>10}  {'t/f(n)':>12}")
    prev = None
    import math
    def f(n):
        return {"n": n, "nlogn": n*math.log2(n), "n2": n*n}.get(expected, n)
    for n in sizes:
        inp = tmp / f"bench_{n}.in"
        try:
            r = run_argv([sys.executable, str(gen_path), str(n)],
                         cwd=workdir, capture_output=True, text=True)
        except FileNotFoundError as e:
            note(f"генератор не найден: {e}")
            continue
        inp.write_text(r.stdout, encoding="utf-8")
        best = None
        for _ in range(3):
            out = tmp / f"bench_{n}.produced"
            t0 = time.perf_counter()
            status, _d = run_once(manifest, lab, workdir, inp, out, timeout)
            dt = time.perf_counter() - t0
            if status != "ok":
                print(f"  {n:>10}  {C.warn}{status}{C.off}")
                best = None
                break
            best = dt if best is None else min(best, dt)
        if best is None:
            continue
        ratio = best / f(n) * 1e6
        print(f"  {n:>10}  {best:>10.4f}  {ratio:>12.3f}")
    note(f"\nгипотеза роста f(n) = {expected}: если столбец t/f(n) примерно постоянен,")
    note("гипотеза согласуется с замером; если растёт или падает — не согласуется.")

# ------------------------------------------------------------------ главное

def main():
    ap = argparse.ArgumentParser(description="Проверка лабораторной работы курса АиСД.")
    ap.add_argument("lab_dir", help="каталог работы, например r1-session-log")
    ap.add_argument("--public", action="store_true", help="только публичные тесты")
    ap.add_argument("--robustness", action="store_true", help="только устойчивость")
    ap.add_argument("--bench", action="store_true", help="только замеры")
    ap.add_argument("--tests", help="свой каталог тестов (для скрытых)")
    ap.add_argument("--manifest", default="solution.json", help="путь к манифесту решения")
    args = ap.parse_args()

    root = Path(args.lab_dir).resolve()
    if not root.is_dir():
        die(f"каталог работы не найден: {root}")

    lab = load_json(root / "lab.json", "lab.json работы")
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest = load_json(manifest_path, "solution.json")

    workdir = manifest_path.parent
    tmp = root / ".check_tmp"
    tmp.mkdir(exist_ok=True)

    print(f"{C.bold}Работа:{C.off} {lab.get('id','?')} — {lab.get('title','')}")
    print(f"{C.bold}Автор:{C.off}  {manifest.get('author','(не указан)')}")
    print(f"{C.bold}Язык:{C.off}   {manifest.get('language','(не указан)')}")

    if not build(manifest, workdir):
        print(f"\n{C.bad}Сборка не удалась, тесты не запускались.{C.off}")
        sys.exit(1)

    run_all = not (args.public or args.robustness or args.bench)
    total_ok = total = 0

    if args.bench:
        run_bench(manifest, lab, root, workdir, tmp)
        sys.exit(0)

    if args.public or run_all:
        tests_dir = args.tests or (root / lab.get("tests_public", "tests/public"))
        o, t = run_public(manifest, lab, root, workdir, tests_dir, tmp)
        total_ok += o; total += t

    if args.robustness or run_all:
        rob = root / lab.get("tests_robustness", "tests/robustness")
        if Path(rob).is_dir():
            o, t = run_robustness(manifest, lab, workdir, rob, tmp)
            total_ok += o; total += t

    head("Итог")
    mark = C.ok if total_ok == total else C.bad
    print(f"  пройдено {mark}{total_ok}/{total}{C.off}")
    if run_all:
        note("скрытые тесты преподавателя здесь не показаны; они запускаются при приёмке.")
    sys.exit(0 if total_ok == total else 1)

if __name__ == "__main__":
    main()
