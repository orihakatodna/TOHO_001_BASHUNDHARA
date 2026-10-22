# -*- coding: utf-8 -*-
"""住戸モデル（models/*.html）の検図スクリプト。

照合する内容:
  1. 各 HTML のページ内スクリプトに構文エラーがないか（node がある場合のみ。無ければ「未照合」）
  2. 家具の初期配置（INIT）が、家具の一覧（CAT）に登録された種類だけでできているか
  3. 家具の初期配置が、外壁の内側（内法）に収まっているか
  4. 同じ高さの層（床・天井・壁）の中で、家具どうしが平面上で重ならないか
  5. 表題欄の版（Rev.）が、ファイル内で1つに決まっているか
  6. 開口（扉・窓）の寸法が壁の範囲に収まり、室内の扉が間仕切りの上にあるか
  7. 開口が、直交する間仕切りの取り合いにかからないか
  8. 同じ壁の線の開口どうしが重ならないか
  9. 床置きの家具が、間仕切りや扉の開き（扉幅の正方形）と重ならないか
 10. 壁付けの機器（間仕切りに付くものを含む）が、同じ壁の開口の上端より上にあるか
 11. 外壁の窓の前に、腰高より高い床置きの家具がないか（高さ h を持つ種類のみ）
 12. 両モデルの間仕切り・扉・窓のデータが同じか

照合していない内容（未照合）:
  - 画面での見た目、ドラッグ操作、スマートフォン幅・ダークモードの表示
  - 寸法の前提（壁厚 250 mm、スラブ 125 mm、天井扇の高さなど）と原典・構造計算との照合
  - 扉・窓の寸法（高さ 7′、幅、腰高）と法規（BNBC など）・採光・換気の基準との照合

使い方:  python tools/check_model.py
終了コード: 検出 0 件なら 0、1 件以上なら 1。
"""
import json
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


def parse_extra(js):
    """家具の高さ h（m）と種類 type。高さの無い種類は None。"""
    ex = {}
    for m in re.finditer(r"(\w+):\{en:'[^']*',ja:'[^']*',w:[\d.]+,d:[\d.]+([^}]*)\}", js):
        h = re.search(r",h:([\d.]+)", m.group(2))
        t = re.search(r"type:'(\w+)'", m.group(2))
        ex[m.group(1)] = (float(h.group(1)) if h else None, t.group(1) if t else None)
    return ex


def parse_open(js):
    """間仕切り PART・扉 DOORS・窓 WINS・寸法 OP。無ければ None。"""
    out = {}
    for name in ("PART", "DOORS", "WINS"):
        m = re.search(r"const %s=(\[\[.*?\]\]);" % name, js)
        if not m:
            return None
        out[name] = json.loads(m.group(1).replace("'", '"'))
    m = re.search(r"const OP=\{PT:([\d.]+),DH:([\d.]+)\}", js)
    if not m:
        return None
    out["PT"], out["DH"] = float(m.group(1)), float(m.group(2))
    return out


def parse_init(js):
    m = re.search(r"const INIT=\[(.*?)\];", js, re.S)
    if not m:
        return None
    return [
        (k, float(x), float(v), int(r))
        for k, x, v, r in re.findall(r"\['(\w+)',(-?[\d.]+),(-?[\d.]+),(-?\d+)\]", m.group(1))
    ]


def parts(op, iw, idp):
    """間仕切りを (横向きか, 位置, 始点, 終点) に。横向き＝v 一定。"""
    out = []
    for x1, v1, x2, v2 in op["PART"] if op else []:
        hz = v1 == v2
        a, b = (x1, x2) if hz else (v1, v2)
        out.append((hz, v1 if hz else x1, min(a, b), max(a, b)))
    return out


def wall_faces(op, iw, idp):
    """壁付けの機器が付く面。(軸, 面の位置, 始点, 終点, 室内側の向き, 壁の線)。モデルの wallFaces() と同じ順。"""
    f = [("x", 0, 0, idp, 1, "L"), ("x", iw, 0, idp, -1, "R"), ("v", 0, 0, iw, 1, "F"), ("v", idp, 0, iw, -1, "B")]
    if op:
        h = op["PT"] / FT / 2
        for hz, c, lo, hi in parts(op, iw, idp):
            ax = "v" if hz else "x"
            f += [(ax, c - h, lo, hi, -1, (hz, c)), (ax, c + h, lo, hi, 1, (hz, c))]
    return f


def snap_wall(x, v, w, d, faces):
    """モデルの snapWall() と同じ規則で、最も近い壁の面に付ける。"""
    best, bd = faces[0], 1e9
    for fc in faces:
        p, q = (x, v) if fc[0] == "x" else (v, x)
        if q < fc[2] or q > fc[3] or (p - fc[1]) * fc[4] < -0.5:
            continue
        if abs(p - fc[1]) < bd:
            bd, best = abs(p - fc[1]), fc
    ax, c, lo, hi, n, line = best
    p = c + n * d / 2
    if ax == "x":
        return p, max(lo + w / 2, min(hi - w / 2, v)), True, best
    return max(lo + w / 2, min(hi - w / 2, x)), p, False, best


def overlap(A, B):
    return A[0] < B[1] - TOL and B[0] < A[1] - TOL and A[2] < B[3] - TOL and B[2] < A[3] - TOL


def openings(op, iw, idp):
    """開口を壁の線ごとに。(id, 線, 始点, 終点, 下端 ft, 上端 ft, 種類, 扉の向き)。線は F/B/L/R か (横向きか, 位置)。"""
    out = []
    for i, s, a, b, lo, hi in op["WINS"]:
        out.append((i, s, a, b, lo, hi, "vent" if i[0] == "V" else "win", 0))
    for i, ax, c, a, b, sw in op["DOORS"]:
        hz = ax == "h"
        s = None
        if hz and abs(c) < 1e-4:
            s = "F"
        elif hz and abs(c - idp) < 0.01:
            s = "B"
        elif not hz and abs(c) < 1e-4:
            s = "L"
        elif not hz and abs(c - iw) < 0.01:
            s = "R"
        out.append((i, s or (hz, c), a, b, 0.0, op["DH"], "door", sw))
    return out


def line_geom(line, iw, idp):
    """壁の線を (横向きか, 位置, 長さ) に。"""
    if line in ("F", "B"):
        return True, 0 if line == "F" else idp, iw
    if line in ("L", "R"):
        return False, 0 if line == "L" else iw, idp
    return line[0], line[1], None


def check_open(op, iw, idp, h_ft, boxes, cat, ex, wall_y, found, notes):
    ht = op["PT"] / FT / 2
    pts = parts(op, iw, idp)
    ops = openings(op, iw, idp)
    # 6. 開口の範囲と、扉が間仕切りの上にあるか
    for i, line, a, b, lo, hi, kind, sw in ops:
        hz, c, length = line_geom(line, iw, idp)
        if not (a < b and lo < hi <= h_ft + TOL):
            found.append(f"開口の寸法が不正: {i}")
        if length is not None:
            if a < -TOL or b > length + TOL:
                found.append(f"開口が外壁の範囲外: {i}")
        elif not any(p[0] == hz and abs(p[1] - c) < 1e-4 and p[2] - TOL <= a and b <= p[3] + TOL for p in pts):
            found.append(f"扉が間仕切りの上にない: {i}")
        # 7. 開口が、直交する間仕切りの取り合い（厚さの範囲）にかからないか
        for phz, k, plo, phi in pts:
            if phz == hz or not (plo - ht - TOL <= c <= phi + ht + TOL):
                continue
            if a - ht < k - TOL and k + TOL < b + ht:
                found.append(f"開口が間仕切りの取り合いにかかる: {i}（間仕切り {'v' if phz else 'x'}={k}）")
    # 8. 同じ壁の線の開口どうしの重なり
    for x in range(len(ops)):
        for y in range(x + 1, len(ops)):
            p, q = ops[x], ops[y]
            if line_geom(p[1], iw, idp)[:2] == line_geom(q[1], iw, idp)[:2] and p[2] < q[3] - TOL and q[2] < p[3] - TOL:
                found.append(f"開口どうしが重なる: {p[0]} と {q[0]}")
    # 9. 床置きの家具と、間仕切り・扉の開き
    rects = []
    for hz, c, lo, hi in pts:
        rects.append((f"間仕切り {'v' if hz else 'x'}={c}", (lo - ht, hi + ht, c - ht, c + ht) if hz else (c - ht, c + ht, lo - ht, hi + ht)))
    for i, line, a, b, lo, hi, kind, sw in ops:
        if kind != "door":
            continue
        hz, c, length = line_geom(line, iw, idp)
        hp = c + sw * ht if length is None else c
        s0, s1 = sorted((hp, hp + sw * (b - a)))
        rects.append((f"扉 {i} の開き", (a, b, s0, s1) if hz else (s0, s1, a, b)))
    for k, x, v, mount, B, *_ in boxes:
        if mount != "floor":
            continue
        for name, A in rects:
            if overlap(A, B):
                found.append(f"家具と{name}が重なる: {k} ({x}, {v})")
    # 10. 壁付けの機器と、同じ壁の開口の上端
    gaps = []
    for k, x, v, mount, B, face in boxes:
        if mount != "wall":
            continue
        y0 = wall_y.get(ex.get(k, (None, None))[1])
        if y0 is None:
            notes.append(f"開口との離れ: 未照合（{k} の取付け高さが読めない）")
            continue
        ax, fc, flo, fhi, n, line = face
        along = (B[2], B[3]) if ax == "x" else (B[0], B[1])
        for i, oline, a, b, lo, hi, kind, sw in ops:
            if line_geom(oline, iw, idp)[:2] != line_geom(line, iw, idp)[:2] or not (a < along[1] - TOL and along[0] < b - TOL):
                continue
            g = y0 - hi * FT
            gaps.append(g)
            if g < 0:
                found.append(f"壁付けの機器が開口にかかる: {k} ({x:.2f}, {v:.2f}) と {i}（離れ {g * 1000:.0f} mm）")
    if gaps:
        notes.append(f"壁付けの機器と下の開口の上端の離れ: 最小 {min(gaps) * 1000:.0f} mm（{len(gaps)} か所）")
    # 11. 外壁の窓の前に、腰高より高い床置きの家具がないか
    for i, line, a, b, lo, hi, kind, sw in ops:
        if kind == "door" or line not in ("F", "B", "L", "R"):
            continue
        for k, x, v, mount, B, *_ in boxes:
            h = ex.get(k, (None, None))[0]
            if mount != "floor" or h is None or h < lo * FT:
                continue
            near = {"F": B[2] < 0.5, "B": B[3] > idp - 0.5, "L": B[0] < 0.5, "R": B[1] > iw - 0.5}[line]
            along = (B[0], B[1]) if line in ("F", "B") else (B[2], B[3])
            if near and a < along[1] - TOL and along[0] < b - TOL:
                found.append(f"窓の前に腰高より高い家具: {k} ({x}, {v}) と {i}")
    notes.append(f"間仕切り {len(pts)} 本・扉 {sum(o[6] == 'door' for o in ops)} か所・窓 {sum(o[6] != 'door' for o in ops)} か所")


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
    op = parse_open(js)
    if dims is None:
        found.append("寸法（M=）が読めない")
        return found, notes, revs, op
    _, _, h_ft, _, iw, idp = dims
    if op is None:
        found.append("間仕切り・扉・窓（PART・DOORS・WINS・OP）が読めない")
    init = parse_init(js)
    cat = parse_cat(js)
    ex = parse_extra(js)
    wall_y = {t: float(y) for t, y in re.findall(r"type==='(\w+)'\)\{box\(w,[\d.]+,[\w.]+,0,([\d.]+)", js)}
    if init is None:
        notes.append("家具: 初期配置なし（家具の照合は対象外）")
        if op:
            check_open(op, iw, idp, h_ft, [], cat, ex, wall_y, found, notes)
        return found, notes, revs, op
    faces = wall_faces(op, iw, idp)

    boxes = []
    for k, x, v, r in init:
        # 2. 種類
        if k not in cat:
            found.append(f"一覧にない種類: {k}")
            continue
        w, d, mount = cat[k]
        face = None
        if mount == "wall":
            x, v, side, face = snap_wall(x, v, w, d, faces)
            bw, bd = (d, w) if side else (w, d)
        else:
            bw, bd = (d, w) if r % 180 else (w, d)
        b = (x - bw / 2, x + bw / 2, v - bd / 2, v + bd / 2)
        # 3. 内法
        if b[0] < -TOL or b[1] > iw + TOL or b[2] < -TOL or b[3] > idp + TOL:
            found.append(f"外壁の外にはみ出す: {k} ({x}, {v})")
        boxes.append((k, x, v, mount, b, face))
    if op:
        check_open(op, iw, idp, h_ft, boxes, cat, ex, wall_y, found, notes)

    # 4. 重なり
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[3] != b[3]:
                continue
            if overlap(a[4], b[4]):
                found.append(f"重なり（{a[3]}）: {a[0]} ({a[1]}, {a[2]}) と {b[0]} ({b[1]}, {b[2]})")

    from collections import Counter
    c = Counter(bx[3] for bx in boxes)
    notes.append(f"家具 {len(init)} 点（床 {c.get('floor', 0)}・天井 {c.get('ceiling', 0)}・壁 {c.get('wall', 0)}）、一覧 {len(cat)} 種、内法 {iw:.2f} × {idp:.2f} ft")
    return found, notes, revs, op


def main():
    files = sorted(MODELS.glob("*.html"))
    if not files:
        print("models/ に HTML がない")
        return 1
    total = 0
    ops = {}
    for p in files:
        found, notes, revs, op = check_file(p)
        ops[p.name] = op
        total += len(found)
        rev = ",".join(sorted(revs)) or "?"
        print(f"■ {p.relative_to(ROOT).as_posix()}  Rev.{rev}  検出 {len(found)}")
        for n in notes:
            print("   ・" + n)
        for f in found:
            print("   ✗ " + f)
    # 12. 両モデルの間仕切り・扉・窓が同じか
    names = [n for n, o in ops.items() if o]
    diff = [n for n in names[1:] if ops[n] != ops[names[0]]]
    print(f"■ モデル間の間仕切り・扉・窓の一致  検出 {len(diff)}（{len(names)} ファイルを照合）")
    for n in diff:
        print(f"   ✗ {n} が {names[0]} と異なる")
    total += len(diff)
    print(f"合計 検出 {total}（{len(files)} ファイル）")
    print("未照合: 画面表示・操作、寸法の前提と原典の照合、扉・窓の寸法と法規（BNBC など）の照合")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
