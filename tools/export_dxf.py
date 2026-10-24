# -*- coding: utf-8 -*-
"""住戸モデル（models/unit_brick.html）から、修正指示用の平面図 DXF を書き出す。

- 単位は mm。原点は外壁の外面の左下（正面＝入口側の仮定を下にする）。
- 内法の左下が、モデルの家具の座標 (x, v) = (0, 0) ft にあたる。1 ft グリッドの番号はその座標。
- 平面の切断高さは 1,200 mm。腰高 3′・3′-6″ の窓は開口として、下端 6′ の換気窓は破線で描く。
- 文字は Shift_JIS（cp932）、DXF R12（AC1009）。JW-CAD などで読める形にしている。
- 間仕切り・扉・窓は両モデルで同じデータなので、CM-01（レンガ）から作る。家具・器具は CM-01 のもの。

使い方:  python tools/export_dxf.py            → dxf/unit_plan_CM-01_Rev<版>_<YYMMDD>.dxf（受け取った DXF と名前が紛れないよう図番を入れる）
         python tools/export_dxf.py --svg 出力.svg   （確認用の SVG も書く）
"""
import datetime
import json
import math
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_model as cm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "models" / "unit_brick.html"
OUT = ROOT / "dxf"
MM = cm.FT * 1000
CUT = 1200  # 平面の切断高さ mm

# 画層: 名前 → (色番号, 内容)
LAYERS = {
    "A-WALL": (7, "外壁・間仕切り（切断面の輪郭）"),
    "A-DOOR": (1, "扉（扉と開きの円弧）"),
    "A-GLAZ": (5, "窓・換気窓（換気窓は破線）"),
    "A-FURN": (8, "床置きの家具・衛生器具"),
    "A-EQPM": (6, "壁付けの機器（エアコン）"),
    "A-CLNG": (8, "天井扇・天井照明（破線）"),
    "A-CORE": (8, "共用コア（CM-03 の階段・EV・ホール）の網掛け"),
    "A-TEXT": (7, "部屋名"),
    "A-TEXT-ID": (3, "扉・窓の記号"),
    "A-GRID1": (9, "1 ft グリッド（内法基準）"),
    "A-GRID5": (8, "5 ft グリッドと番号"),
    "A-DIM": (2, "寸法"),
    "A-TITL": (7, "表題・注記"),
}
EXTRA_ROOMS = []  # 部屋名はモデルの ZONES だけから取る


def fmt_ft(f):
    ft = int(f + 1e-6)
    inch = round((f - ft) * 12)
    if inch == 12:
        ft, inch = ft + 1, 0
    return f"{ft}′-{inch}″"


def union_edges(rects):
    """軸に平行な長方形の和の輪郭を、線分の一覧で返す（座標を圧縮した格子で求める）。"""
    rects = [tuple(round(v, 3) for v in r) for r in rects]
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})
    fill = [[False] * (len(ys) - 1) for _ in range(len(xs) - 1)]
    for i in range(len(xs) - 1):
        cx = (xs[i] + xs[i + 1]) / 2
        for j in range(len(ys) - 1):
            cy = (ys[j] + ys[j + 1]) / 2
            fill[i][j] = any(r[0] < cx < r[2] and r[1] < cy < r[3] for r in rects)
    f = lambda i, j: 0 <= i < len(xs) - 1 and 0 <= j < len(ys) - 1 and fill[i][j]
    segs = []
    for i in range(len(xs)):  # 縦の辺
        run = None
        for j in range(len(ys) - 1):
            on = f(i - 1, j) != f(i, j)
            if on and run is None:
                run = ys[j]
            if run is not None and (not on or j == len(ys) - 2):
                end = ys[j + 1] if on else ys[j]
                segs.append((xs[i], run, xs[i], end))
                run = None
    for j in range(len(ys)):  # 横の辺
        run = None
        for i in range(len(xs) - 1):
            on = f(i, j - 1) != f(i, j)
            if on and run is None:
                run = xs[i]
            if run is not None and (not on or i == len(xs) - 2):
                end = xs[i + 1] if on else xs[i]
                segs.append((run, ys[j], end, ys[j]))
                run = None
    return segs


def build():
    """図形の一覧を作る。要素は ('line'|'arc'|'circle'|'text', 画層, ...)。"""
    html = SRC.read_text(encoding="utf-8")
    js = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
    w_ft, d_ft, h_ft, t_m, iw, idp = cm.parse_dims(js)
    op = cm.parse_open(js)
    cat, init, ex = cm.parse_cat(js), cm.parse_init(js), cm.parse_extra(js)
    zones = json.loads(re.search(r"const ZONES=(\[\[.*?\]\]);", js).group(1).replace("'", '"'))
    rev = re.search(r'data-i="kRev">Rev\.</b><span>([A-Z][\w-]*)</span>', html).group(1)
    date = re.search(r'data-i="kDate">Date</b><span>([\d-]+)</span>', html).group(1)
    T = t_m * 1000
    W, D = w_ft * MM, d_ft * MM
    X = lambda x: T + x * MM
    Y = lambda v: T + v * MM
    ht = op["PT"] * 1000 / 2
    E = []
    line = lambda ly, x1, y1, x2, y2, lt=None: E.append(("line", ly, x1, y1, x2, y2, lt))
    text = lambda ly, x, y, h, s, al="c": E.append(("text", ly, x, y, h, s, al))
    rect = lambda ly, x0, y0, x1, y1, lt=None: [line(ly, a, b, c, d, lt) for a, b, c, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0))]

    # 壁: 外壁と間仕切りの長方形から開口を抜き、和の輪郭を描く
    ops = cm.openings(op, iw, idp)
    cut = {s: [(X(a) if s in "FB" else Y(a), X(b) if s in "FB" else Y(b)) for i, l, a, b, lo, hi, k, sw in ops if l == s and lo * MM < CUT]
           for s in "FBLR"}
    co, ba, tf = op["CORE"], op["BAL"], op["TF"]
    cut["F"].append((X(ba["x0"] - tf), X(ba["x1"] + tf)))
    rects = []

    def pieces(a0, a1, holes):
        cur = a0
        for h0, h1 in sorted(holes):
            if h0 > cur:
                yield cur, h0
            cur = max(cur, h1)
        if cur < a1:
            yield cur, a1

    for s, (fixed, along) in {"F": ((0, T), (0, W)), "B": ((D - T, D), (0, W)), "L": ((0, T), (0, D)), "R": ((W - T, W), (0, D))}.items():
        for a0, a1 in pieces(*along, cut[s]):
            rects.append((a0, fixed[0], a1, fixed[1]) if s in "FB" else (fixed[0], a0, fixed[1], a1))
    # バルコニーのくぼみ（左右の壁と奥の壁）、共用コアの壁
    rects += [(X(ba["x0"] - tf), 0, X(ba["x0"]), Y(ba["d"] + tf)), (X(ba["x1"]), 0, X(ba["x1"] + tf), Y(ba["d"] + tf))]
    holes = [(X(a), X(b)) for i, l, a, b, lo, hi, k, sw in ops if l == "K" and lo * MM < CUT]
    rects += [(p0, Y(ba["d"]), p1, Y(ba["d"] + tf)) for p0, p1 in pieces(X(ba["x0"] - tf), X(ba["x1"] + tf), holes)]
    ct = co["t"] * MM
    holes = [(Y(a), Y(b)) for i, l, a, b, lo, hi, k, sw in ops if l == "C"]
    rects += [(X(co["x0"]), p0, X(co["x0"]) + ct, p1) for p0, p1 in pieces(Y(co["v0"]), D - T, holes)]
    rects.append((X(co["x0"]), Y(co["v0"]), W - T, Y(co["v0"]) + ct))
    for hz, c, lo, hi in cm.parts(op, iw, idp):
        holes = [(X(a) if hz else Y(a), X(b) if hz else Y(b)) for i, l, a, b, lo2, hi2, k, sw in ops
                 if k == "door" and l == (hz, c)]
        a0, a1 = (X(lo) - ht, X(hi) + ht) if hz else (Y(lo) - ht, Y(hi) + ht)
        for p0, p1 in pieces(a0, a1, holes):
            rects.append((p0, Y(c) - ht, p1, Y(c) + ht) if hz else (X(c) - ht, p0, X(c) + ht, p1))
    for s in union_edges(rects):
        line("A-WALL", *s)

    # 扉と窓
    for i, l, a, b, lo, hi, kind, sw in ops:
        hz, c, length = cm.line_geom(l, iw, idp, op)
        if kind == "door":
            w = (b - a) * MM
            hpf = cm.hinge(l, c, sw, op, length)
            hp = Y(hpf) if hz else X(hpf)
            if hz:
                hx, hy = X(a), hp
                line("A-DOOR", hx, hy, hx, hy + sw * w)
                E.append(("arc", "A-DOOR", hx, hy, w, *((0, 90) if sw > 0 else (270, 360))))
                text("A-TEXT-ID", X((a + b) / 2), hp + sw * w * 0.45, 180, i)
            else:
                hx, hy = hp, Y(a)
                line("A-DOOR", hx, hy, hx + sw * w, hy)
                E.append(("arc", "A-DOOR", hx, hy, w, *((0, 90) if sw > 0 else (90, 180))))
                text("A-TEXT-ID", hp + sw * w * 0.55, Y((a + b) / 2), 180, i)
            continue
        vent = lo * MM >= CUT
        lt = "DASHED" if vent else None
        if l == "K":
            y0, y1 = Y(ba["d"]), Y(ba["d"] + tf)
            for y in [y0, y1, (y0 + y1) / 2 - 30, (y0 + y1) / 2 + 30]:
                line("A-GLAZ", X(a), y, X(b), y, lt)
            text("A-TEXT-ID", X((a + b) / 2), y0 - 1100, 180, i)
        elif l in ("F", "B"):
            y0, y1 = (0, T) if l == "F" else (D - T, D)
            x0, x1 = X(a), X(b)
            offs = [y0 + T / 2 - 30, y0 + T / 2 + 30] + ([] if vent else [y0, y1])
            for y in offs:
                line("A-GLAZ", x0, y, x1, y, lt)
            text("A-TEXT-ID", (x0 + x1) / 2, -450 if l == "F" else D + 450, 180, i)
        else:
            x0, x1 = (0, T) if l == "L" else (W - T, W)
            y0, y1 = Y(a), Y(b)
            offs = [x0 + T / 2 - 30, x0 + T / 2 + 30] + ([] if vent else [x0, x1])
            for x in offs:
                line("A-GLAZ", x, y0, x, y1, lt)
            text("A-TEXT-ID", -450 if l == "L" else W + 450, (y0 + y1) / 2, 180, i)

    # 共用コアの網掛け（45°、@600）
    hx0, hy0, hx1, hy1 = X(co["x0"]) + ct, Y(co["v0"]) + ct, W - T, D - T
    k = hy0 - hx1
    while k < hy1 - hx0:
        pts = [(x, x + k) for x in (hx0, hx1) if hy0 <= x + k <= hy1] + [(y - k, y) for y in (hy0, hy1) if hx0 <= y - k <= hx1]
        if len(pts) >= 2:
            (p0, p1) = sorted(pts)[0], sorted(pts)[-1]
            if p0 != p1:
                line("A-CORE", p0[0], p0[1], p1[0], p1[1])
        k += 600

    # 家具・器具（壁付けはモデルと同じ規則で壁に寄せる）
    faces = cm.wall_faces(op, iw, idp)
    for k, x, v, r in init:
        w, d, mount = cat[k]
        if mount == "wall":
            x, v, side, _ = cm.snap_wall(x, v, w, d, faces)
            bw, bd = (d, w) if side else (w, d)
            rect("A-EQPM", X(x - bw / 2), Y(v - bd / 2), X(x + bw / 2), Y(v + bd / 2))
        elif mount == "ceiling":
            E.append(("circle", "A-CLNG", X(x), Y(v), w * MM / 2))
        else:
            bw, bd = (d, w) if r % 180 else (w, d)
            if ex.get(k, (None, None))[1] == "plant":
                E.append(("circle", "A-FURN", X(x), Y(v), w * MM / 2))
            else:
                rect("A-FURN", X(x - bw / 2), Y(v - bd / 2), X(x + bw / 2), Y(v + bd / 2))

    # 部屋名
    for z in [z[:6] for z in zones] + EXTRA_ROOMS:
        x0, v0, zw, zd, en, ja = z
        cx, cy = X(x0 + zw / 2), Y(v0 + zd / 2)
        h = 220 if zw >= 6 else 160
        text("A-TEXT", cx, cy + h * 0.7, h, ja)
        text("A-TEXT", cx, cy - h * 0.7, h * 0.7, en)

    # グリッド（内法基準 ft）
    for i in range(int(iw) + 1):
        line("A-GRID5" if i % 5 == 0 else "A-GRID1", X(i), T, X(i), D - T)
        if i % 5 == 0:
            text("A-GRID5", X(i), -1000, 180, f"x={i}")
    for j in range(int(idp) + 1):
        line("A-GRID5" if j % 5 == 0 else "A-GRID1", T, Y(j), W - T, Y(j))
        if j % 5 == 0:
            text("A-GRID5", -1150, Y(j), 180, f"v={j}")

    # 寸法（外形・内法）
    def dim(x1, y1, x2, y2, s, dy=0):
        line("A-DIM", x1, y1, x2, y2)
        for px, py in ((x1, y1), (x2, y2)):
            line("A-DIM", px - 120, py - 120, px + 120, py + 120)
        hz = y1 == y2
        text("A-DIM", (x1 + x2) / 2 + (0 if hz else 250), (y1 + y2) / 2 + (200 if hz else dy), 200, s, "c" if hz else "l")

    dim(0, -1700, W, -1700, f"{fmt_ft(w_ft)}（{W:,.0f}）外形")
    dim(T, -1450, W - T, -1450, f"{fmt_ft(iw)}（{W - 2 * T:,.0f}）内法")
    dim(W + 1300, 0, W + 1300, D, f"{fmt_ft(d_ft)}（{D:,.0f}）外形", 600)
    dim(W + 900, T, W + 900, D - T, f"{fmt_ft(idp)}（{D - 2 * T:,.0f}）内法", -600)

    # 表題・注記
    text("A-TITL", W / 2, -2300, 220, "正面（入口側の仮定・未確認）")
    notes = [
        f"TOHO_001 Bashundhara 住戸平面（修正指示用）  CM-01／CM-02  Rev.{rev}  {date}  単位 mm  縮尺なし",
        "概念モデルから書き出した協議用の図。施工用ではない。",
        "座標: 内法の左下を (x, v) = (0, 0) ft とする。グリッドの番号はモデルの家具の座標と同じ。",
        "未確認の前提: 外壁 250・間仕切り 125（レンガ長手積み）・扉高さ 7′・窓の腰高 3′（台所 3′-6″）・上端 7′・換気窓 6′〜7′。法規との照合は未実施。",
        "右奥の網掛けは共用コア（CM-03 の階段・EV・ホール、壁 200）で、住戸の外。正面中央はバルコニーのくぼみ。",
        "切断高さ 1,200。換気窓（下端 6′）は破線。天井扇・照明は破線の円（A-CLNG）。家具・器具の寸法は代表値。",
        "画層: " + "、".join(f"{k} {v[1]}" for k, v in LAYERS.items()),
    ]
    for n, s in enumerate(notes):
        text("A-TITL", 0, -2900 - n * 380, 200 if n == 0 else 160, s, "l")
    return E, {"rev": rev, "date": date, "W": W, "D": D, "doors": len(op["DOORS"]), "wins": len(op["WINS"])}


def to_dxf(E):
    o = []
    g = lambda c, v: o.extend([str(c), v if isinstance(v, str) else (f"{v:.3f}" if isinstance(v, float) else str(v))])
    g(0, "SECTION"); g(2, "HEADER"); g(9, "$ACADVER"); g(1, "AC1009"); g(9, "$DWGCODEPAGE"); g(3, "ANSI_932"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES")
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 2)
    for name, desc, pat in (("CONTINUOUS", "Solid line", []), ("DASHED", "__ __ __", [200.0, -100.0])):
        g(0, "LTYPE"); g(2, name); g(70, 0); g(3, desc); g(72, 65); g(73, len(pat)); g(40, float(sum(abs(p) for p in pat)))
        for p in pat:
            g(49, p)
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, len(LAYERS))
    for name, (col, _) in LAYERS.items():
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, col); g(6, "DASHED" if name == "A-CLNG" else "CONTINUOUS")
    g(0, "ENDTAB"); g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for e in E:
        k, ly = e[0], e[1]
        if k == "line":
            g(0, "LINE"); g(8, ly)
            if e[6]:
                g(6, e[6])
            g(10, float(e[2])); g(20, float(e[3])); g(30, 0.0); g(11, float(e[4])); g(21, float(e[5])); g(31, 0.0)
        elif k == "arc":
            g(0, "ARC"); g(8, ly); g(10, float(e[2])); g(20, float(e[3])); g(30, 0.0); g(40, float(e[4])); g(50, float(e[5])); g(51, float(e[6]))
        elif k == "circle":
            g(0, "CIRCLE"); g(8, ly); g(10, float(e[2])); g(20, float(e[3])); g(30, 0.0); g(40, float(e[4]))
        else:
            x, y, h, s, al = e[2:]
            g(0, "TEXT"); g(8, ly); g(10, float(x)); g(20, float(y)); g(30, 0.0); g(40, float(h)); g(1, s)
            if al == "c":
                g(72, 1); g(11, float(x)); g(21, float(y)); g(31, 0.0); g(73, 2)
    g(0, "ENDSEC"); g(0, "EOF")
    return "\n".join(o) + "\n"


def to_svg(E, info):
    pad = 3500
    x0, y0, w, h = -pad, -7000, info["W"] + 2 * pad, info["D"] + 7000 + pad
    col = {"A-WALL": "#111", "A-DOOR": "#c0392b", "A-GLAZ": "#1f6fd1", "A-FURN": "#888", "A-EQPM": "#8e44ad", "A-CLNG": "#bbb", "A-CORE": "#999",
           "A-TEXT": "#111", "A-TEXT-ID": "#1e8449", "A-GRID1": "#eee", "A-GRID5": "#ccc", "A-DIM": "#b7950b", "A-TITL": "#111"}
    Yf = lambda y: -y
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {-(y0 + h)} {w} {h}" width="900" style="background:#fff">']
    for e in E:
        c = col[e[1]]
        sw = 30 if e[1] == "A-WALL" else 12
        if e[0] == "line":
            da = ' stroke-dasharray="120 80"' if e[6] or e[1] == "A-CLNG" else ""
            s.append(f'<line x1="{e[2]:.0f}" y1="{Yf(e[3]):.0f}" x2="{e[4]:.0f}" y2="{Yf(e[5]):.0f}" stroke="{c}" stroke-width="{sw}"{da}/>')
        elif e[0] == "circle":
            s.append(f'<circle cx="{e[2]:.0f}" cy="{Yf(e[3]):.0f}" r="{e[4]:.0f}" fill="none" stroke="{c}" stroke-width="{sw}"/>')
        elif e[0] == "arc":
            cx, cy, r, a0, a1 = e[2:]
            p = lambda a: (cx + r * math.cos(math.radians(a)), Yf(cy + r * math.sin(math.radians(a))))
            (sx, sy), (ex_, ey) = p(a0), p(a1)
            s.append(f'<path d="M{sx:.0f} {sy:.0f} A{r:.0f} {r:.0f} 0 0 0 {ex_:.0f} {ey:.0f}" fill="none" stroke="{c}" stroke-width="{sw}" stroke-dasharray="80 60"/>')
        else:
            x, y, hh, t, al = e[2:]
            anc = "middle" if al == "c" else "start"
            bl = ' dominant-baseline="central"' if al == "c" else ""
            t = t.replace("&", "&amp;").replace("<", "&lt;")
            s.append(f'<text x="{x:.0f}" y="{Yf(y):.0f}" font-size="{hh:.0f}" text-anchor="{anc}"{bl} fill="{c}" font-family="sans-serif">{t}</text>')
    s.append("</svg>")
    return "\n".join(s)


def stats(dxf_text):
    """書き出した DXF を読み戻して、画層ごと・種類ごとの数と、壁の輪郭が閉じているかを返す。"""
    lines = dxf_text.split("\n")
    pairs = list(zip(lines[0::2], lines[1::2]))
    ents, cur = [], None
    start = next(i for i, p in enumerate(pairs) if p == ("2", "ENTITIES"))
    for c, v in pairs[start + 1:]:
        if c == "0":
            if cur:
                ents.append(cur)
            cur = {"type": v} if v not in ("ENDSEC", "EOF") else None
        elif cur is not None:
            cur.setdefault(c, v)
    from collections import Counter
    cnt = Counter((e["type"], e.get("8")) for e in ents)
    deg = Counter()
    for e in ents:
        if e["type"] == "LINE" and e.get("8") == "A-WALL":
            for a, b in (("10", "20"), ("11", "21")):
                deg[(round(float(e[a]), 1), round(float(e[b]), 1))] += 1
    odd = [p for p, n in deg.items() if n % 2]
    return cnt, odd


def main():
    E, info = build()
    dxf = to_dxf(E)
    dxf.encode("cp932")  # 符号化できない文字があればここで止める
    if "--svg" in sys.argv:
        Path(sys.argv[sys.argv.index("--svg") + 1]).write_text(to_svg(E, info), encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    path = OUT / f"unit_plan_CM-01_Rev{info['rev']}_{datetime.date.today():%y%m%d}.dxf"
    if path.exists():
        print(f"既にある: {path.relative_to(ROOT).as_posix()}（上書きしない。消すか日付を変えること）")
        return 1
    path.write_text(dxf, encoding="cp932", newline="\r\n")
    cnt, odd = stats(dxf)
    print(f"書き出し: {path.relative_to(ROOT).as_posix()}  図形 {len(E)}  壁の輪郭の端点の不一致 {len(odd)}")
    for (t, ly), n in sorted(cnt.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print(f"   {ly:10s} {t:7s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
