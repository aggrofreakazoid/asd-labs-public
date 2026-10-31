#!/usr/bin/env python3
"""
Чекер для check.py (compare=checker): сравнивает восстановленное решением
изображение с эталоном.

Вызывается как:  check_restore.py <shuffled.bmp> <source.bmp> <restored>
(shuffled.bmp — сам вход, не используется; source.bmp — эталон/expected;
restored — то, что записало решение).

Код возврата 0 — изображение восстановлено точно, 1 — нет (или файл не
читается). Сообщение печатается в stdout.

При расхождении дополнительно проверяется, совпадают ли блоки по GROUP
пикселей по составу: если да, нарушен только порядок внутри блоков — это
след неустойчивой сортировки. Размер группы фиксирован и должен совпадать
с тем, что использовался при генерации tests/public (см. task.md).

Только стандартная библиотека Python — ничего собирать не нужно.
"""
import struct
import sys

GROUP = 8

FILE_HEADER = 14
INFO_HEADER = 40


class BMPError(Exception):
    pass


def read_bmp(path):
    """Возвращает (w, h, pixels), где pixels — список троек (B, G, R) в
    порядке следования строк в файле."""
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < FILE_HEADER + INFO_HEADER:
        raise BMPError("файл короче заголовка BMP")
    if raw[0:2] != b"BM":
        raise BMPError("отсутствует сигнатура BM")
    off_bits = struct.unpack_from("<I", raw, 10)[0]
    bi_size = struct.unpack_from("<I", raw, 14)[0]
    if bi_size < INFO_HEADER:
        raise BMPError(f"неподдерживаемый информационный заголовок размера {bi_size}")
    w, h = struct.unpack_from("<ii", raw, 18)
    bit_count = struct.unpack_from("<H", raw, 28)[0]
    compression = struct.unpack_from("<I", raw, 30)[0]
    if bit_count != 24:
        raise BMPError(f"поддерживается только 24 бита на пиксель, в файле {bit_count}")
    if compression != 0:
        raise BMPError(f"поддерживается только BI_RGB без сжатия, в файле код {compression}")
    if w <= 0 or h == 0:
        raise BMPError(f"некорректные размеры {w}x{h}")
    h = abs(h)  # сверху вниз; порядок строк в файле от этого не меняется

    stride = (w * 3 + 3) // 4 * 4
    need = off_bits + stride * h
    if len(raw) < need:
        raise BMPError(f"файл усечён: нужно {need} байт, доступно {len(raw)}")

    pix = []
    for row in range(h):
        start = off_bits + row * stride
        data = raw[start:start + w * 3]
        pix.extend(data[i:i + 3] for i in range(0, w * 3, 3))
    return w, h, pix


def check_images(orig, got, group):
    (ow, oh, op), (gw, gh, gp) = orig, got
    if (ow, oh) != (gw, gh):
        return f"размеры не совпадают: ожидалось {ow}x{oh}, получено {gw}x{gh}", False

    n = len(op)
    diff = sum(1 for a, b in zip(op, gp) if a != b)
    if diff == 0:
        return "изображение восстановлено точно", True

    blocks_match = all(
        sorted(op[s:s + group]) == sorted(gp[s:s + group])
        for s in range(0, n, group)
    )
    pct = 100 * diff / n
    if blocks_match:
        return (f"расходится {diff} пикселей ({pct:.2f}%); внутри блоков по {group} "
                f"состав совпадает, нарушен только порядок — признак неустойчивой "
                f"сортировки"), False
    return (f"расходится {diff} пикселей ({pct:.2f}%); блоки не совпадают по составу — "
            f"перестановка применена неверно"), False


def main():
    if len(sys.argv) < 4:
        print("использование: check_restore.py <shuffled.bmp> <source.bmp> <restored>")
        sys.exit(2)
    _shuffled, source, restored = sys.argv[1:4]
    try:
        orig = read_bmp(source)
    except (OSError, BMPError) as e:
        print(f"чтение эталона {source}: {e}")
        sys.exit(1)
    try:
        got = read_bmp(restored)
    except (OSError, BMPError) as e:
        print(f"чтение результата решения: {e}")
        sys.exit(1)
    msg, ok = check_images(orig, got, GROUP)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
