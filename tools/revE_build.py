# -*- coding: utf-8 -*-
"""ユーザー提供の平面 DXF（dxf/unit_plan_RevE_261024-1.dxf）から、住戸の3Dモデルのデータを作る。

DXF から取るもの（座標は DXF のブロック内の mm。X1 通り = x 0、Y1 通り = y 0、y は奥へ増える）:
  画層 5  部屋の内法の長方形（両辺 400 mm 以上）。外形と、コアの外形は除く
  画層 4  柱
  画層 8  開口（外壁にあれば窓・掃出し窓、内側なら扉・通路）
  画層 6  EPS（箱として立てる）
  画層 7  バルコニー（閉じた多角形）と階段の矢印
  画層 3  部屋名・面積の文字
壁 = 外形の長方形から部屋を除いた残り。

DXF に無いので、ここで仮定するもの（ユーザーの了承前は「案」）: 階高、開口の高さ、扉の開き勝手、家具。

使い方:
  python tools/revE_build.py --preview 出力.html   確認用の平面図（SVG）
  python tools/revE_build.py --json 出力.json      モデルに埋め込むデータ
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dxf" / "unit_plan_RevE_261024-1.dxf"
FT = 304.8  # mm

# ---- 仮定（DXF に無いもの）
H = 10 * FT                      # 階高 10′（CM-01/02 と同じ）
DOOR_H = 7 * FT                  # 扉・通路・掃出し窓の上端 7′
WIN = (3 * FT, 7 * FT)           # 窓の下端・上端
WIN_KITCHEN = (3.5 * FT, 7 * FT)
WIN_BATH = (6 * FT, 7 * FT)      # 浴室の窓は換気窓
WIN_STAIR = (6 * FT, 7 * FT)
PASSAGE_W = 1500                 # これより広い内側の開口は扉なしの通路
# 扉の開く向き（仮定）: 開口の中心 (x, y) → 開く側。+1 は x／y の増える側、-1 は減る側。"ev" は引き戸（扉を描かない）
SWING = {
    (3114, 1850): -1,    # 寝室2 の扉: 寝室2 へ
    (7264, 1850): -1,    # 主寝室の扉: 居間へ（主寝室のベッドを避ける）
    (9759, 3811): -1,    # 主寝室浴室の扉: 主寝室へ（外開き）
    (3114, 4500): -1,    # 収納の扉: 収納へ
    (3114, 7225): -1,    # 寝室3 の扉: 寝室3 へ
    (7264, 5325): -1,    # 共用浴室の扉: 食堂・ホールへ（外開き）
    (7264, 8175): 1,     # 台所の扉: 台所へ
    (3114, 11950): -1,   # 寝室4 の扉: 寝室4 へ
    (6544, 9550): -1,    # 住戸の玄関: 住戸へ
    (7944, 10250): -1,   # 階段室の扉: EV ホールへ
    (6619, 11750): "ev", # EV の扉
}
# 家具・器具（仮定）: [種類, x, y, 回転°]。座標は DXF の mm。回転 0 はベッドの頭・ソファの背が奥（+y）
FURN = [
    ["double", 1350, 2797, 0], ["side", 2300, 3500, 0], ["desk", 1925, 255, 0],
    ["tv", 4250, 180, 180], ["sofa", 4250, 2500, 0], ["coffee", 4250, 1300, 0], ["arm", 6300, 2900, -90],
    ["king", 8290, 2733, 0],
    ["queen", 1280, 6267, 180], ["ward", 1815, 8895, 0],
    ["plantL", 3600, 8600, 0],
    ["dtable", 6197, 7000, 0], ["dchair", 5740, 6223, 180], ["dchair", 6650, 6223, 180], ["dchair", 5740, 7777, 0], ["dchair", 6650, 7777, 0],
    ["shower", 8393, 4332, 0], ["wc", 8500, 5600, -90], ["basin", 7800, 6546, 0],
    ["wc", 10193, 4350, -90], ["basin", 10315, 5005, -90], ["shower", 9432, 5693, 0],
    ["counter", 9100, 7205, 180], ["counter", 8870, 9145, 0], ["fridge", 7706, 7266, 0],
    ["double", 1550, 10403, 180], ["ward", 2745, 13515, -90],
    ["sofa", 4612, 11950, -90], ["coffee", 3700, 11950, 90],
    ["plantS", 10300, -800, 0], ["plantS", 400, 15100, 0],
    ["fan", 1550, 1850, 0], ["fan", 4250, 1600, 0], ["fan", 8500, 1700, 0], ["fan", 1550, 7225, 0], ["fan", 1550, 11950, 0], ["fan", 4122, 11950, 0],
    ["pendant", 6197, 7000, 0], ["clight", 4122, 6500, 0], ["clight", 1550, 4500, 0], ["clight", 8088, 5300, 0], ["clight", 9760, 5000, 0], ["clight", 8934, 8200, 0],
    ["ac", 1550, 3700, 180], ["ac", 3200, 3000, 90], ["ac", 7350, 3200, 90], ["ac", 1550, 9150, 180], ["ac", 1550, 14400, 180],
]
# 家具の寸法（ft、CM-01 の CAT と同じ値）。mount: f 床・c 天井・w 壁
CATD = {"sofa": (7, 3, "f"), "arm": (2.6, 2.6, "f"), "coffee": (4, 2, "f"), "tv": (6, 1.5, "f"), "dtable": (6, 3.5, "f"), "dchair": (1.5, 1.6, "f"),
        "king": (6.33, 6.67, "f"), "queen": (5, 6.67, "f"), "double": (4.5, 6.25, "f"), "side": (1.5, 1.5, "f"), "ward": (6, 2, "f"), "desk": (4, 2, "f"),
        "counter": (6, 2, "f"), "fridge": (2.5, 2.4, "f"), "wc": (1.3, 2.3, "f"), "basin": (2, 1.5, "f"), "shower": (3, 3, "f"),
        "plantL": (1.6, 1.6, "f"), "plantS": (1.1, 1.1, "f"), "fan": (4.67, 4.67, "c"), "clight": (1.2, 1.2, "c"), "pendant": (1.3, 1.3, "c"), "ac": (3.1, 0.8, "w")}


def read_block(path):
    raw = path.read_bytes().decode("utf-8")
    lines = [l.strip() for l in raw.replace("\r\n", "\n").split("\n")]
    pairs = list(zip(lines[0::2], lines[1::2]))
    j = next(k for k, p in enumerate(pairs) if p == ("2", "BLOCKS"))
    blocks, name, cur = defaultdict(list), None, None
    for c, v in pairs[j + 1:]:
        if c == "0" and v == "ENDSEC":
            break
        if c == "0":
            if cur and name:
                blocks[name].append(cur)
            cur = {"type": v, "g": []}
            if v == "BLOCK":
                name = None
        elif cur is not None:
            cur["g"].append((c, v))
            if cur["type"] == "BLOCK" and c == "2":
                name = v
    big = max((b for b in blocks if not b.startswith("_")), key=lambda b: len(blocks[b]))
    return blocks[big]


def get(e, code):
    for c, v in e["g"]:
        if c == code:
            return v
    return None


def rect(e):
    xs = [float(v) for c, v in e["g"] if c == "10"]
    ys = [float(v) for c, v in e["g"] if c == "20"]
    return (round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1))


def extract():
    ents = read_block(SRC)
    polys = [(get(e, "8"), rect(e), int(get(e, "70") or 0) & 1, e) for e in ents if e["type"] == "LWPOLYLINE"]
    l5 = [r for ly, r, cl, e in polys if ly == "5"]
    outline = max(l5, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    rooms = [r for r in l5 if r != outline and min(r[2] - r[0], r[3] - r[1]) >= 400]
    core = max((r for r in rooms if any(o != r and o[0] >= r[0] and o[1] >= r[1] and o[2] <= r[2] and o[3] <= r[3] for o in rooms)),
               key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), default=None)
    rooms = [r for r in rooms if r != core]
    cols = [r for ly, r, cl, e in polys if ly == "4"]
    opens = [r for ly, r, cl, e in polys if ly == "8"]
    eps = [r for ly, r, cl, e in polys if ly == "6"]
    bal = [r for ly, r, cl, e in polys if ly == "7" and cl and (r[1] >= outline[3] - 1 or r[3] <= outline[1] + 1)]
    texts = [(get(e, "1"), float(get(e, "10")), float(get(e, "20"))) for e in ents if e["type"] == "TEXT" and get(e, "8") == "3"]
    return {"outline": outline, "rooms": rooms, "core": core, "cols": cols, "opens": opens, "eps": eps, "bal": bal, "texts": texts}


def room_names(d):
    """部屋の長方形ごとに、中に入る文字（名前・面積）をまとめる。"""
    out = []
    for r in d["rooms"]:
        ts = sorted([t for t in d["texts"] if r[0] < t[1] < r[2] and r[1] < t[2] < r[3]], key=lambda t: -t[2])
        name = "".join(t[0] for t in ts if "㎡" not in t[0] and t[0] not in ("UP", "EPS") and "kg" not in t[0])
        area = next((t[0] for t in ts if "㎡" in t[0]), "")
        out.append({"r": r, "name": name, "area": area})
    return out


def classify(d):
    """開口を、外壁の窓・掃出し窓／内側の扉・通路に分ける。"""
    ox0, oy0, ox1, oy1 = d["outline"]
    T = 250
    rn = room_names(d)
    res = []
    for o in d["opens"]:
        cx, cy = (o[0] + o[2]) / 2, (o[1] + o[3]) / 2
        w = max(o[2] - o[0], o[3] - o[1])
        side = "F" if o[1] <= oy0 + 1 and o[3] <= oy0 + 351 else "B" if o[3] >= oy1 - 1 and o[1] >= oy1 - 351 else \
               "L" if o[0] <= ox0 + 1 and o[2] <= ox0 + 351 else "R" if o[2] >= ox1 - 1 and o[0] >= ox1 - 351 else None
        if side:
            inner = {"F": (cx, oy0 + T + 50), "B": (cx, oy1 - T - 50), "L": (ox0 + T + 50, cy), "R": (ox1 - T - 50, cy)}[side]
            room = next((q for q in rn if q["r"][0] <= inner[0] <= q["r"][2] and q["r"][1] <= inner[1] <= q["r"][3]), None)
            nm = room["name"] if room else ""
            onbal = side in "FB" and any(min(o[2], b[2]) - max(o[0], b[0]) >= 0.8 * (o[2] - o[0])
                                         and (abs(b[3] - oy0) < 2 if side == "F" else abs(b[1] - oy1) < 2) for b in d["bal"])
            if onbal:
                kind, z = "sl", (0, DOOR_H)
            elif "浴室" in nm:
                kind, z = "vent", WIN_BATH
            elif "台所" in nm:
                kind, z = "win", WIN_KITCHEN
            elif "階段" in nm:
                kind, z = "vent", WIN_STAIR
            else:
                kind, z = "win", WIN
            res.append({"r": o, "side": side, "kind": kind, "z": z, "room": nm, "w": w})
        else:
            kind = "pass" if w > PASSAGE_W else "door"
            res.append({"r": o, "side": None, "kind": kind, "z": (0, DOOR_H), "room": "", "w": w})
    return res


FH = {"coffee": 0.42, "tv": 0.5, "dtable": 0.75, "side": 0.55, "ward": 2.1, "desk": 0.75, "counter": 0.9, "fridge": 1.8, "wc": 0.75,
      "basin": 0.85, "shower": 0.06, "plantL": 1.6, "plantS": 0.8}  # 高さ m（CM-01 の CAT と同じ）
AC_Y = 2300  # エアコンの下端 mm（CM-01 と同じ）
PARAPET = {"h": 1100, "brick": 125, "concrete": 150}  # バルコニーの手すり壁（仮定）: 高さ、厚さ（レンガ案はブロック積み、打ち放し案は RC）
TOL = 3      # mm


def walls(d, ops):
    """壁の箱 [x0, y0, x1, y1, z0, z1]（mm）。外形から部屋を除き、開口の範囲は下端より下と上端より上だけ残す。"""
    o = d["outline"]
    rs = d["rooms"] + ([d["core"]] if False else [])
    xs = sorted({o[0], o[2]} | {v for r in rs for v in (r[0], r[2])} | {v for p in ops for v in (p["r"][0], p["r"][2])})
    ys = sorted({o[1], o[3]} | {v for r in rs for v in (r[1], r[3])} | {v for p in ops for v in (p["r"][1], p["r"][3])})
    xs = [x for x in xs if o[0] <= x <= o[2]]
    ys = [y for y in ys if o[1] <= y <= o[3]]
    inside = lambda r, x, y: r[0] < x < r[2] and r[1] < y < r[3]
    out = []
    for j in range(len(ys) - 1):
        cy = (ys[j] + ys[j + 1]) / 2
        run = None
        for i in range(len(xs) - 1):
            cx = (xs[i] + xs[i + 1]) / 2
            if any(inside(r, cx, cy) for r in rs):
                segs = None
            else:
                op = next((p for p in ops if inside(p["r"], cx, cy)), None)
                segs = ((0, H),) if not op else tuple(s for s in ((0, op["z"][0]), (op["z"][1], H)) if s[1] - s[0] > 1)
            if run and segs == run[2] and abs(run[1] - xs[i]) < 1e-6:
                run[1] = xs[i + 1]
            else:
                if run and run[2]:
                    out += [[run[0], ys[j], run[1], ys[j + 1], s[0], s[1]] for s in run[2]]
                run = [xs[i], xs[i + 1], segs] if segs is not None else None
        if run and run[2]:
            out += [[run[0], ys[j], run[1], ys[j + 1], s[0], s[1]] for s in run[2]]
    return out


def doors(ops):
    """扉: 開口・吊り元の面・開く向き・幅。SWING に無い扉は ValueError。"""
    out = []
    for p in ops:
        if p["kind"] != "door":
            continue
        r = p["r"]
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        key = min(SWING, key=lambda k: (k[0] - cx) ** 2 + (k[1] - cy) ** 2)
        if (key[0] - cx) ** 2 + (key[1] - cy) ** 2 > 200 ** 2:
            raise ValueError(f"扉の開く向きが決まっていない: 中心 ({cx:.0f}, {cy:.0f})")
        sw = SWING[key]
        vert = (r[2] - r[0]) < (r[3] - r[1])  # 壁が y 方向に伸びる（扉は ±x に開く）
        a0, a1 = (r[1], r[3]) if vert else (r[0], r[2])
        if sw == "ev":
            out.append({"r": r, "vert": vert, "a0": a0, "a1": a1, "sw": 0, "plane": None})
            continue
        plane = (r[2] if sw > 0 else r[0]) if vert else (r[3] if sw > 0 else r[1])
        out.append({"r": r, "vert": vert, "a0": a0, "a1": a1, "sw": sw, "plane": plane})
    return out


def swing_rect(dr):
    w = dr["a1"] - dr["a0"]
    s0, s1 = sorted((dr["plane"], dr["plane"] + dr["sw"] * w))
    return (s0, dr["a0"], s1, dr["a1"]) if dr["vert"] else (dr["a0"], s0, dr["a1"], s1)


def furniture(d):
    """家具の平面の範囲（mm）。壁付けは、点を含む部屋のいちばん近い辺に寄せる（モデルと同じ規則）。"""
    out = []
    for k, x, y, r in FURN:
        w, dp, m = CATD[k]
        w, dp = w * FT, dp * FT
        if m == "w":
            room = next((q for q in d["rooms"] if q[0] <= x <= q[2] and q[1] <= y <= q[3]), None)
            if room is None:
                out.append((k, x, y, r, m, None))
                continue
            ds = [x - room[0], room[2] - x, y - room[1], room[3] - y]
            e = ds.index(min(ds))
            if e < 2:
                x = room[0] + dp / 2 if e == 0 else room[2] - dp / 2
                y = max(room[1] + w / 2, min(room[3] - w / 2, y))
                r, bw, bd = (90 if e == 0 else -90), dp, w
            else:
                y = room[1] + dp / 2 if e == 2 else room[3] - dp / 2
                x = max(room[0] + w / 2, min(room[2] - w / 2, x))
                r, bw, bd = (180 if e == 2 else 0), w, dp
        else:
            bw, bd = (dp, w) if r % 180 else (w, dp)
        out.append((k, x, y, r, m, (x - bw / 2, y - bd / 2, x + bw / 2, y + bd / 2)))
    return out


def ov(a, b):
    return a[0] < b[2] - TOL and b[0] < a[2] - TOL and a[1] < b[3] - TOL and b[1] < a[3] - TOL


def check(d=None):
    """検図: (検出の一覧, 注記の一覧)。"""
    d = d or extract()
    ops = classify(d)
    found, notes = [], []
    try:
        drs = doors(ops)
    except ValueError as e:
        return [str(e)], notes
    fs = furniture(d)
    spaces = d["rooms"] + d["bal"]
    o, t = d["outline"], max(PARAPET["brick"], PARAPET["concrete"])
    parapets = []
    for b in d["bal"]:
        front = b[3] <= o[1] + 1
        parapets += [(b[0], b[1], b[2], b[1] + t) if front else (b[0], b[3] - t, b[2], b[3]),
                     (b[0], b[1], b[0] + t, b[3]), (b[2] - t, b[1], b[2], b[3])]
    swings = [swing_rect(q) for q in drs if q["sw"]]
    for i, (k, x, y, r, m, b) in enumerate(fs):
        if b is None:
            found.append(f"壁付けの機器が部屋の中にない: {k} ({x}, {y})")
            continue
        if not any(s[0] - TOL <= b[0] and b[2] <= s[2] + TOL and s[1] - TOL <= b[1] and b[3] <= s[3] + TOL for s in spaces):
            found.append(f"家具が部屋・バルコニーに収まらない: {k} ({x:.0f}, {y:.0f})")
        if m == "f":
            for c in d["cols"] + d["eps"]:
                if ov(b, c):
                    found.append(f"家具が柱・EPS と重なる: {k} ({x:.0f}, {y:.0f})")
            for c in parapets:
                if ov(b, c):
                    found.append(f"家具がバルコニーの手すり壁と重なる: {k} ({x:.0f}, {y:.0f})")
            for s in swings:
                if ov(b, s):
                    found.append(f"家具が扉の開きと重なる: {k} ({x:.0f}, {y:.0f})")
            h = FH.get(k) if any(q[0] - TOL <= b[0] and b[2] <= q[2] + TOL and q[1] - TOL <= b[1] and b[3] <= q[3] + TOL for q in d["rooms"]) else None
            for p in ops:
                if p["side"] and h and h * 1000 > p["z"][0]:
                    pr = p["r"]
                    near = {"F": b[1] < pr[3] + 150, "B": b[3] > pr[1] - 150, "L": b[0] < pr[2] + 150, "R": b[2] > pr[0] - 150}[p["side"]]
                    along = (b[0], b[2], pr[0], pr[2]) if p["side"] in "FB" else (b[1], b[3], pr[1], pr[3])
                    if near and along[0] < along[3] - TOL and along[2] < along[1] - TOL:
                        found.append(f"窓の前に下端より高い家具: {k} ({x:.0f}, {y:.0f})")
        if m == "w":
            for p in ops:
                if p["kind"] != "pass" and ov((b[0] - 300, b[1] - 300, b[2] + 300, b[3] + 300), p["r"]) and p["z"][1] > AC_Y:
                    found.append(f"壁付けの機器が開口にかかる: {k} ({x:.0f}, {y:.0f})")
        for k2, x2, y2, r2, m2, b2 in fs[i + 1:]:
            if b2 and m2 == m and ov(b, b2):
                found.append(f"重なり（{m}）: {k} ({x:.0f}, {y:.0f}) と {k2} ({x2:.0f}, {y2:.0f})")
    # 階段（CM-03 と同じ規定値。出典は check_model.LAW）
    st = next((r for r in d["rooms"] if r[3] - r[1] > 4000 and r[0] > d["core"][0] - 1 and r[1] > d["core"][1] - 1), None)
    n = -(-H // 175)
    n += n % 2
    r_ = H / n
    run = (n / 2 - 1) * 250
    if st is None or st[2] - st[0] < 2 * 1150 + 150 - TOL or st[3] - st[1] < 1150 + run + 1150 - TOL:
        found.append("階段室に 1.15 m×2 の折返し階段が収まらない")
    notes.append(f"部屋 {len(d['rooms'])}・開口 {len(ops)}（扉 {len(drs)}・窓 {sum(1 for p in ops if p['side'])}）・柱 {len(d['cols'])}・家具 {len(fs)}、"
                 f"階段 {n}段×{r_:.1f} mm・踏面 250 mm")
    return found, notes


def preview(path):
    d = extract()
    ops = classify(d)
    ws, drs, fs = walls(d, ops), doors(ops), furniture(d)
    o = d["outline"]
    Y = lambda y: -y
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{o[0] - 1800} {-(o[3] + 1800)} {o[2] - o[0] + 3600} {o[3] - o[1] + 4400}" width="100%" style="background:#fff;font-family:sans-serif">']
    for r in d["rooms"]:
        s.append(f'<rect x="{r[0]}" y="{Y(r[3])}" width="{r[2] - r[0]}" height="{r[3] - r[1]}" fill="#f6f1e6"/>')
    for b in d["bal"]:
        s.append(f'<rect x="{b[0]}" y="{Y(b[3])}" width="{b[2] - b[0]}" height="{b[3] - b[1]}" fill="#e3efd8" stroke="#6a8f4e" stroke-width="20"/>')
    for w in ws:
        full = w[4] == 0 and w[5] == H
        s.append(f'<rect x="{w[0]}" y="{Y(w[3])}" width="{w[2] - w[0]}" height="{w[3] - w[1]}" fill="{"#222" if full else "#9aa"}"/>')
    for c in d["cols"]:
        s.append(f'<rect x="{c[0]}" y="{Y(c[3])}" width="{c[2] - c[0]}" height="{c[3] - c[1]}" fill="none" stroke="#a32d2d" stroke-width="30"/>')
    for p in ops:
        if p["side"]:
            r = p["r"]
            col = {"win": "#378add", "vent": "#1d9e75", "sl": "#185fa5"}[p["kind"]]
            s.append(f'<rect x="{r[0]}" y="{Y(r[3])}" width="{r[2] - r[0]}" height="{r[3] - r[1]}" fill="#fff" stroke="{col}" stroke-width="35"/>')
    for q in drs:
        if not q["sw"]:
            continue
        w, p0 = q["a1"] - q["a0"], q["plane"]
        if q["vert"]:
            hx, hy, ex, ey, cx, cy = p0, q["a0"], p0 + q["sw"] * w, q["a0"], p0, q["a1"]
        else:
            hx, hy, ex, ey, cx, cy = q["a0"], p0, q["a0"], p0 + q["sw"] * w, q["a1"], p0
        sweep = 1 if (q["vert"] and q["sw"] < 0) or (not q["vert"] and q["sw"] > 0) else 0
        s.append(f'<line x1="{hx}" y1="{Y(hy)}" x2="{ex}" y2="{Y(ey)}" stroke="#d85a30" stroke-width="30"/>')
        s.append(f'<path d="M{ex} {Y(ey)} A{w} {w} 0 0 {sweep} {cx} {Y(cy)}" fill="none" stroke="#d85a30" stroke-width="15" stroke-dasharray="60 40"/>')
    for k, x, y, r, m, b in fs:
        if not b:
            continue
        if m == "c":
            s.append(f'<circle cx="{x}" cy="{Y(y)}" r="{(b[2] - b[0]) / 2}" fill="none" stroke="#bbb" stroke-width="15" stroke-dasharray="60 40"/>')
        else:
            col = "#7f77dd" if m == "w" else "#666"
            s.append(f'<rect x="{b[0]:.0f}" y="{Y(b[3]):.0f}" width="{b[2] - b[0]:.0f}" height="{b[3] - b[1]:.0f}" fill="none" stroke="{col}" stroke-width="18"/>')
    for q in room_names(d):
        r = q["r"]
        s.append(f'<text x="{(r[0] + r[2]) / 2}" y="{Y((r[1] + r[3]) / 2)}" font-size="260" text-anchor="middle" fill="#111">{q["name"]}</text>')
        s.append(f'<text x="{(r[0] + r[2]) / 2}" y="{Y((r[1] + r[3]) / 2) + 320}" font-size="200" text-anchor="middle" fill="#555">{q["area"]}</text>')
    s.append(f'<text x="{(o[0] + o[2]) / 2}" y="{Y(o[1]) + 1500}" font-size="260" text-anchor="middle">正面（道路側）</text>')
    s.append("</svg>")
    legend = ('<div style="font:14px sans-serif;padding:8px">黒＝壁（床から天井まで）、灰＝開口の上下に残る壁、青＝窓（濃い青は掃出し窓）、緑＝換気窓、'
              '橙＝扉と開く向き、赤枠＝柱、灰の線＝家具、紫＝エアコン、破線の円＝天井扇・照明、緑の面＝バルコニー</div>')
    Path(path).write_text('<!doctype html><meta charset="utf-8"><title>RevE 案</title><body style="margin:0;background:#fff">' + legend + "\n".join(s) + "</body>", encoding="utf-8")


ROOM_EN = {"寝室2": "Bedroom 2", "居間": "Living", "主寝室": "Master bedroom", "収納": "Store", "寝室3": "Bedroom 3", "家族室・ホール": "Family hall",
           "食堂・ホール": "Dining hall", "共用浴室（障害者対応）": "Shared bath (accessible)", "主寝室浴室": "Master bath", "PS": "PS", "台所": "Kitchen",
           "寝室4": "Bedroom 4", "家族室2": "Family room 2", "階段・加圧": "Stair (pressurised)", "EVホール": "Lift hall", "EV": "Lift"}


def room_cat(name):
    return "W" if "浴室" in name else "B" if "寝室" in name else "K" if "台所" in name else \
           "C" if any(k in name for k in ("階段", "EV")) else "S" if name in ("収納", "PS") else "L"


def data():
    """モデルに埋め込むデータ。数値は mm、小数1桁に丸める。"""
    d = extract()
    ops = classify(d)
    o, co = d["outline"], d["core"]
    T = 250
    ws = []
    for w in walls(d, ops):
        extw = w[2] <= o[0] + T + 1 or w[0] >= o[2] - T - 61 or w[3] <= o[1] + T + 1 or w[1] >= o[3] - T - 1  # 外壁の帯の中にある箱
        incore = co[0] - 1 <= w[0] and w[2] <= co[2] + 1 and co[1] - 1 <= w[1] and w[3] <= co[3] + 1
        ws.append([round(v, 1) for v in w] + ["ext" if extw else "core" if incore else "int"])
    xs = [v for r in [o] + d["bal"] for v in (r[0], r[2])]
    ys = [v for r in [o] + d["bal"] for v in (r[1], r[3])]
    st = next(r for r in d["rooms"] if r[3] - r[1] > 4000 and r[0] > co[0] - 1 and r[1] > co[1] - 1)
    ev = next(r for r in d["rooms"] if r[0] > co[0] - 1 and r[1] > co[1] - 1 and r != st and "EV1" in "".join(t[0] for t in d["texts"] if r[0] < t[1] < r[2] and r[1] < t[2] < r[3]))
    n = int(-(-H // 175))
    n += n % 2
    drs = doors(ops)
    main = min(drs, key=lambda q: abs((q["r"][0] + q["r"][2]) / 2 - 6544) + abs((q["r"][1] + q["r"][3]) / 2 - 9550))
    rooms = [{"r": q["r"], "name": q["name"], "en": ROOM_EN.get(q["name"], q["name"]), "area": q["area"], "cat": room_cat(q["name"])} for q in room_names(d)]
    return {
        "H": H, "door_h": DOOR_H, "outline": o, "ext": [min(xs), min(ys), max(xs), max(ys)], "core": co,
        "rooms": rooms, "walls": ws, "cols": d["cols"], "eps": d["eps"], "bal": d["bal"], "ev": ev,
        "opens": [{"r": p["r"], "side": p["side"], "kind": p["kind"], "z": [round(p["z"][0], 1), round(p["z"][1], 1)]} for p in ops],
        "doors": [dict(q, main=q is main) for q in drs],
        "stair": {"r": st, "n": n, "tread": 250, "w": 1150, "land": 1150},
        "parapet": PARAPET, "furn": FURN, "eye": [6197, 8200], "person": [4250, 1800], "src": SRC.name,
    }


def html(material, rev="D", date="2026-10-24"):
    """モデルの HTML。CSS と家具（CAT・build）・床仕上げ（FIN・paint）は CM-01 から取る。"""
    b = (ROOT / "models" / "unit_brick.html").read_text(encoding="utf-8")
    cut = lambda a, z: b[b.index(a):b.index(z, b.index(a))]
    head = b[:b.index("</style>") + len("</style>")]
    head = head[head.index("<meta"):]
    fin = cut("const FIN=", "\n") + "\n"
    paint = cut("function rgb(", "function drawFloor(")
    mats = cut("const MAT=", "const CAT={")
    cat = cut("const CAT={", "\nconst INIT=") if "\nconst INIT=" in b[b.index("const CAT={"):] else cut("const CAT={", "};\n") + "};"
    if not cat.rstrip().endswith("};"):
        cat = cut("const CAT={", "}};") + "}};"
    build = cut("function build(k){", "  return g;}") + "  return g;}"
    d = data()
    dw = "CM-04" if material == "brick" else "CM-05"
    mname = {"brick": ("brick, English bond", "レンガ（イングリッシュボンド）"), "concrete": ("fair-faced concrete, 1,800 × 900 formwork", "コンクリート打ち放し（型枠 1,800 × 900）")}[material]
    W, Dd = d["outline"][2] - d["outline"][0], d["outline"][3] - d["outline"][1]
    out_s = f"{W:,.0f} × {Dd:,.0f} mm<span class=\"m\">{W / FT:.2f} × {Dd / FT:.2f} ft</span>"
    names = [q for q in d["rooms"] if q["cat"] != "C" and q["name"] != "PS"]
    lay_ja = "・".join(f"{q['name']} {q['area']}" for q in names)
    lay_en = ", ".join(f"{q['en']} {q['area'].replace('㎡', ' m²')}" for q in names)
    t = {
        "en": {"title": f"Dwelling unit (plan Rev.E) — {mname[0].split(',')[0]}", "sub": "3D model built from the user's plan DXF: four bedrooms, family rooms, kitchen, two baths; lift and stair core at the rear right. Concept model.",
               "layout": lay_en, "walls": f"Outer walls 250 mm, {mname[0]}. Partitions 125 mm, brick in stretcher bond (half-brick), exposed. Balcony parapets " + {"brick": "in brick block, 125 mm", "concrete": "in fair-faced RC, 150 mm"}[material] + ", 1,100 mm high (provisional).",
               "rc": {"brick": "RC frame — 11 columns (DXF layer 4) and the core walls around the stair and lift — finished in brick-block style.", "concrete": "RC columns (11, from DXF layer 4) shown in concrete, full height. Core walls around the stair and lift in concrete."}[material],
               "h": "Floor to floor 10′ (3,048 mm), open top (assumed, as CM-01/02).",
               "op": "Doors and passages 7′ high; windows sill 3′, head 7′ (kitchen 3′-6″); bath and stair vents 6′–7′; glazed doors to the balconies. Door swings assumed. All provisional.",
               "core": f"Stair 2 × 1.15 m flights, {d['stair']['n']} risers × {H / d['stair']['n']:.0f} mm, treads 250 mm; lift 1,600 kg; pressurised stair (from the DXF).",
               "note": "Concept model for discussion, not for construction. Walls, rooms, openings, RC columns and balconies come from the DXF; heights, door swings and furniture are assumptions. Furniture you move is kept only in your own browser."},
        "ja": {"title": f"住戸（平面 Rev.E）— {mname[1].split('（')[0]}", "sub": "ユーザー提供の平面 DXF から作った3Dモデル。4寝室・家族室・台所・浴室2、右奥に階段・EV のコア。概念モデル。",
               "layout": lay_ja, "walls": f"外壁 250 mm、{mname[1]}。間仕切り 125 mm はレンガブロックの長手積み（半枚積み）、現し。バルコニーの手すりは" + {"brick": "ブロック積み 125 mm", "concrete": "RC 打ち放し 150 mm"}[material] + "、高さ 1,100 mm（仮定）。",
               "rc": {"brick": "RC 躯体（柱 11 本〔DXF の画層 4〕と階段・EV まわりのコアの壁）は、レンガブロック調の仕上げ。", "concrete": "RC の柱 11 本（DXF の画層 4）をコンクリートで床から天井まで表示。階段・EV まわりのコアの壁もコンクリート。"}[material],
               "h": "階高 10′（3,048 mm）、天井なし（仮定。CM-01/02 と同じ）。",
               "op": "扉・通路の上端 7′、窓は腰高 3′・上端 7′（台所は腰高 3′-6″）、浴室・階段の換気窓 6′〜7′、バルコニーへは掃出し窓。扉の開き勝手は仮定。いずれも仮の値。",
               "core": f"階段は 1.15 m × 2 の折返し、{d['stair']['n']} 段 × {H / d['stair']['n']:.0f} mm、踏面 250 mm。EV 1,600 kg。階段は加圧（DXF による）。",
               "note": "協議用の概念モデルで、施工用ではありません。壁・部屋・開口・RC の柱・バルコニーは DXF から、高さ・扉の開き勝手・家具は仮定です。動かした家具の位置は、見ている方のブラウザーにだけ残ります。"},
    }
    ui = {"en": dict(kDrawing="Drawing", kScale="Scale", kDate="Date", kRev="Rev.", vPersp="Perspective", vTop="Top", vFront="Front", vInside="Inside, eye level", zoom="Distance", dims="Dimensions",
                     fix="Fans, lights, AC", fTag="Furniture", selNone="Nothing selected", rot="Rotate 90°", del_="Remove", add="Add", reset="Restore proposal", finTag="Floor finish",
                     bathL="Baths: anti-slip tile 300 × 300", bathSuf="; baths: anti-slip tile", grid="1 m grid", zones="Room names", csTag="For Clip Studio (GLB)", glbAll="Save the unit as GLB",
                     glbFL="Include furniture, fans, lights, AC", glbOne="Save the furniture chosen in the list as GLB",
                     glbErr="The GLB exporter could not be loaded. Check the internet connection and reload the page.",
                     hint="Drag a piece of furniture to move it; drag empty space to rotate the view. Right-drag or Shift-drag moves the view sideways (arrow keys too, after clicking the view); a view button resets it. The Top view is easiest for arranging. GLB files open in Clip Studio as 3D materials (1 unit = 1 m).",
                     specH="Specification", sSrc="Source", sSrcM="Plan read from the DXF (rooms, walls, openings, RC columns, balconies, core)", sOut="Outside", sL="Layout", sW="Walls", sRc="Structure",
                     sH="Height", sOp="Doors, windows", sCo="Core", sF="Floor"),
          "ja": dict(kDrawing="図番", kScale="縮尺", kDate="日付", kRev="版", vPersp="パース", vTop="上から", vFront="正面", vInside="室内・目線", zoom="距離", dims="寸法表示",
                     fix="天井扇・照明・エアコン", fTag="家具", selNone="未選択", rot="90° 回転", del_="削除", add="追加", reset="提案の配置に戻す", finTag="床仕上げ",
                     bathL="浴室は防滑タイル 300 × 300", bathSuf="、浴室は防滑タイル", grid="1 m グリッド", zones="部屋名", csTag="Clip Studio 用（GLB）", glbAll="住戸を GLB で保存",
                     glbFL="家具・天井扇・照明・エアコンを含める", glbOne="一覧で選んだ家具を GLB で保存",
                     glbErr="GLB の書き出し機能を読み込めませんでした。インターネット接続を確かめて、ページを読み込み直してください。",
                     hint="家具をドラッグすると移動、何もない所をドラッグすると視点が回ります。右ドラッグか Shift＋ドラッグで視点を平行移動します（画面をクリックしたあとは矢印キーでも動きます）。視点のボタンを押すと元に戻ります。配置は「上から」が操作しやすいです。GLB は Clip Studio に 3D 素材として読み込めます（1 単位 = 1 m）。",
                     specH="仕様", sSrc="元の図", sSrcM="DXF から読んだ平面（部屋・壁・開口・RC の柱・バルコニー・コア）", sOut="外形", sL="間取り", sW="壁", sRc="構造",
                     sH="高さ", sOp="扉・窓", sCo="コア", sF="床")}
    txt = {}
    for l in ("en", "ja"):
        u = {("del" if k == "del_" else k): v for k, v in ui[l].items()}
        u.update(title=t[l]["title"], sub=t[l]["sub"], sLv=t[l]["layout"], sWv=t[l]["walls"], sRcv=t[l]["rc"], sHv=t[l]["h"], sOpv=t[l]["op"], sCov=t[l]["core"], note=t[l]["note"])
        txt[l] = u
    tpl = (ROOT / "tools" / "revE_template.html").read_text(encoding="utf-8")
    rep = {"__MAT__JS": mats, "__CAT__": cat, "__BUILD__": build, "__FIN__": fin, "__PAINT__": paint,
           "__TXT__": json.dumps(txt, ensure_ascii=False), "__DATA__": json.dumps(d, ensure_ascii=False, separators=(",", ":")),
           "__MAT__": material, "__DRAWING__": dw, "__DATE__": date, "__REV__": rev, "__SRC__": d["src"], "__OUT__": out_s,
           "__TITLE_EN__": t["en"]["title"], "__SUB_EN__": t["en"]["sub"], "__LAYOUT_EN__": t["en"]["layout"], "__WALLS_EN__": t["en"]["walls"],
           "__RC_EN__": t["en"]["rc"], "__H_EN__": t["en"]["h"], "__OP_EN__": t["en"]["op"], "__CORE_EN__": t["en"]["core"], "__NOTE_EN__": t["en"]["note"]}
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    title = "Unit Rev.E — " + ("Brick" if material == "brick" else "Concrete")
    return f"<title>{title}</title>\n" + head + "\n\n" + tpl


def html_paths():
    return {"brick": ROOT / "models" / "revE_brick.html", "concrete": ROOT / "models" / "revE_concrete.html"}


if __name__ == "__main__":
    if "--html" in sys.argv:
        for m, p in html_paths().items():
            p.write_text(html(m), encoding="utf-8", newline="\n")
            print("書き出し:", p.relative_to(ROOT).as_posix())
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
    f, n = check()
    print(f"検出 {len(f)}")
    for t in n:
        print("・" + t)
    for t in f:
        print("✗ " + t)
    if "--list" not in sys.argv:
        sys.exit(0)
    d = extract()
    print("outline", d["outline"], "core", d["core"])
    for q in room_names(d):
        print("room", q["r"], q["name"], q["area"])
    for o in classify(d):
        print("open", o["r"], o["side"], o["kind"], o["room"], round(o["w"]))
    print("cols", d["cols"])
    print("bal", d["bal"], "eps", d["eps"])
