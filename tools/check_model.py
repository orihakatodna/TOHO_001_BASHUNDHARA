# -*- coding: utf-8 -*-
"""住戸モデル（models/*.html）の検図スクリプト。

照合する内容:
  1. 各 HTML のページ内スクリプトに構文エラーがないか（node がある場合のみ。無ければ「未照合」）
  2. 家具の初期配置（INIT）が、家具の一覧（CAT）に登録された種類だけでできているか
  3. 家具の初期配置が、外壁の内側（内法）に収まっているか
  4. 同じ高さの層（床・天井・壁）の中で、家具どうしが平面上で重ならないか
  5. 表題欄の版（Rev.）が、ファイル内で1つに決まっているか

照合していない内容（未照合）:
  - 画面での見た目、ドラッグ操作、スマートフォン幅・ダークモードの表示
  - 寸法の前提（壁厚 250 mm、スラブ 125 mm、天井扇の高さなど）と原典・構造計算との照合

使い方:  python tools/check_model.py
終了コード: 検出 0 件なら 0、1 件以上なら 1。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
FT = 0.3048
TOL = 0.01  # ft


def parse_dims(js):
    m = re.search(r"M=\{W:([\d.]+),D:([\d.]+),H:([\d.]+),T:([\d.]+)", js)
    if not m:
        return None
    w, d, h, t = map(float, m.groups())
    iw = (w * FT - 2 * t) / FT
    idp = (d * FT - 2 * t) / FT
    return w, d, h, t, iw, idp


def parse_cat(js):
    cat = {}
    for m in re.finditer(
        r"(\w+):\{en:'[^']*',ja:'[^']*',w:([\d.]+),d:([\d.]+)([^}]*)\}", js
    ):
        mm = re.search(r"mount:'(\w+)'", m.group(4))
        cat[m.group(1)] = (float(m.group(2)), float(m.group(3)), mm.group(1) if mm else "floor")
    return cat


def parse_init(js):
    m = re.search(r"const INIT=\[(.*?)\];", js, re.S)
    if not m:
        return None
    return [
        (k, float(x), float(v), int(r))
        for k, x, v, r in re.findall(r"\['(\w+)',(-?[\d.]+),(-?[\d.]+),(-?\d+)\]", m.group(1))
    ]


def snap_wall(x, v, w, d, iw, idp):
    ds = [x, iw - x, v, idp - v]
    i = ds.index(min(ds))
    if i == 0:
        x = d / 2
    elif i == 1:
        x = iw - d / 2
    elif i == 2:
        v = d / 2
    else:
        v = idp - d / 2
    return x, v, i < 2


def check_file(path):
    found = []
    notes = []
    html = path.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    js = scripts[-1] if scripts else ""

    # 1. 構文
    node = shutil.which("node")
    if not js:
        found.append("ページ内スクリプトが見つからない")
    elif node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(js)
            tmp = f.name
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True, encoding="utf-8")
        Path(tmp).unlink(missing_ok=True)
        if r.returncode != 0:
            found.append("スクリプトの構文エラー: " + r.stderr.strip().splitlines()[-1])
    else:
        notes.append("構文: 未照合（node が見つからない）")

    # 5. 版
    revs = set(re.findall(r'data-i="kRev">Rev\.</b><span>([A-Z][\w-]*)</span>', html))
    if len(revs) != 1:
        found.append(f"表題欄の版が1つに決まらない: {sorted(revs)}")

    dims = parse_dims(js)
    init = parse_init(js)
    if init is None:
        notes.append("家具: 初期配置なし（照合対象外）")
        return found, notes, revs
    if dims is None:
        found.append("寸法（M=）が読めない")
        return found, notes, revs
    _, _, _, _, iw, idp = dims
    cat = parse_cat(js)

    boxes = []
    for k, x, v, r in init:
        # 2. 種類
        if k not in cat:
            found.append(f"一覧にない種類: {k}")
            continue
        w, d, mount = cat[k]
        if mount == "wall":
            x, v, side = snap_wall(x, v, w, d, iw, idp)
            bw, bd = (d, w) if side else (w, d)
        else:
            bw, bd = (d, w) if r % 180 else (w, d)
        b = (x - bw / 2, x + bw / 2, v - bd / 2, v + bd / 2)
        # 3. 内法
        if b[0] < -TOL or b[1] > iw + TOL or b[2] < -TOL or b[3] > idp + TOL:
            found.append(f"外壁の外にはみ出す: {k} ({x}, {v})")
        boxes.append((k, x, v, mount, b))

    # 4. 重なり
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[3] != b[3]:
                continue
            A, B = a[4], b[4]
            if A[0] < B[1] - TOL and B[0] < A[1] - TOL and A[2] < B[3] - TOL and B[2] < A[3] - TOL:
                found.append(f"重なり（{a[3]}）: {a[0]} ({a[1]}, {a[2]}) と {b[0]} ({b[1]}, {b[2]})")

    from collections import Counter
    c = Counter(m for *_, m, _ in boxes)
    notes.append(f"家具 {len(init)} 点（床 {c.get('floor', 0)}・天井 {c.get('ceiling', 0)}・壁 {c.get('wall', 0)}）、一覧 {len(cat)} 種、内法 {iw:.2f} × {idp:.2f} ft")
    return found, notes, revs


def main():
    files = sorted(MODELS.glob("*.html"))
    if not files:
        print("models/ に HTML がない")
        return 1
    total = 0
    for p in files:
        found, notes, revs = check_file(p)
        total += len(found)
        rev = ",".join(sorted(revs)) or "?"
        print(f"■ {p.relative_to(ROOT).as_posix()}  Rev.{rev}  検出 {len(found)}")
        for n in notes:
            print("   ・" + n)
        for f in found:
            print("   ✗ " + f)
    print(f"合計 検出 {total}（{len(files)} ファイル）")
    print("未照合: 画面表示・操作、寸法の前提と原典の照合")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
