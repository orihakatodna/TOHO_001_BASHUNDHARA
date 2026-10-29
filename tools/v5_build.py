# -*- coding: utf-8 -*-
"""図面一式 v5 の G+8 の建物の3Dモデル CM-06（models/v5_g8.html）を、RevG の平面 DXF と v5 の変更点から作る。

元データ（どちらもユーザー提供）:
  RevG  dxf/unit_plan_RevG_261024-1.dxf（2026-10-24）。基準階の部屋（画層 5）・柱（4）・開口（8）・EPS（6）・文字（3）。
        要素はモデル空間に直接ある。画層 0 の、原点から左下へ伸びる線1本は図の一部でないとみなして無視する
  v5    pdf/261028/01_TOHO_BASHUNDHARA_v5_261028_A3.pdf（2026-10-29、2頁、300dpi の画像のみ）。p1 面積表、p2 平面・立面・断面
  読み取りの記録  前のセッションの共有メモ「v5_PDF読取メモ_261029.md」（記入値・縮尺読み・推定を区別）
v5 の基準階は RevG を下絵にしたと推定する（柱の位置で重ねて残差 最大 83 mm。ユーザーには未確認）。
そこで平面は RevG を基にし、v5 で変わった点を下の定数で上書きする。

定数の出典の書き方:
  記入値    v5 に書かれた値
  縮尺読み  v5 の図から縮尺で読んだ値（±0.1 m 程度）。平面は RevG の四隅の柱に合わせて読んだ
  RevG      DXF の値
  仮定      図に無いので決めた値（2026-10-29 ユーザー了承）

座標: RevG と同じ。mm、原点＝建物の南西の外面の角、x＝東、y＝北。z は1階（GF）の床から上。

使い方:
  python tools/v5_build.py --html                 models/v5_g8.html を書き出す（生成した HTML は手で直さない）
  python tools/v5_build.py --preview 出力.html    確認用の平面図（SVG、1階・2〜8階・屋上）
  python tools/v5_build.py                        検図の結果だけを表示
"""
import json
import math
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dxf" / "unit_plan_RevG_261024-1.dxf"
OUT = ROOT / "models" / "v5_g8.html"
TPL = ROOT / "tools" / "v5_template.html"
FT = 304.8  # mm
DRAWING, REV, DATE = "CM-06", "A", "2026-10-29"

# ---- 記入値（v5 p2。面積は p1 の表）
W_NOTE = 10995           # 建物の幅 10.995 m（各平面の下の寸法）
D_NOTE = 15000           # 建物の奥行 15 m（1階平面）
UNIT_NOTE = 9750         # 基準階の住戸 9.75 m（G+8 1〜8F 平面）
CORE_NOTE = 5250         # コア 5.25 m（G+6 1〜6F 平面の左の寸法。RevG の文字「コア 5.25」も同じ）
GF_H = 12 * FT           # GF 12′（断面の右の寸法。図は約 3.17 m だが記入値を採る、了承済み）
TYP_H = 10 * FT          # 1F〜8F 各 10′（同）
N_TYP = 8                # 1F〜8F
H_MAX = 33000            # H ≤ 33 m（断面）
SITE_W = 45 * FT         # 敷地の幅 45′（道路側。1階平面の赤字）
SITE_D = 64 * FT         # 敷地の奥行 64′（同。p1 の表 2,880 sft = 45 × 64）
ROAD_W = 25 * FT         # 前面道路 25′、建物の南（1階平面。方位記号の N が上）
AREA = {"plot": 267.56, "coverage": 164.92, "typical": 136.60}  # p1 の面積表 G+8（m²、小数2桁）

# ---- 仮定（図に無いもの。2026-10-29 ユーザー了承）
PL = 1.5 * FT            # 1階の床は道路から +1′-6″（CM-03 と同じ）
SITE_UP = 0.5 * FT       # 植栽の地盤は道路から +0′-6″（CM-03 と同じ）
SLAB = 125               # スラブ
BEAM = (250, 600)        # 梁 幅 × 成（スラブ込み）。中央の梁は RevG の通り芯 Ym（y 4,112.5）に置く
DOOR_H = 7 * FT          # 扉・掃出し窓・1階の開口の上端 7′（RevE と同じ。1階の南の開口は南立面の縮尺読み 床から約 2.11 m）
WIN = (3.5 * FT, 7 * FT)   # 窓 3′-6″〜7′（南立面の縮尺読み 床から 1.03〜2.12 m。東面・北面も同じとする）
VENT = (6 * FT, 7 * FT)    # 浴室・階段の換気窓（RevE と同じ）
PASSAGE_W = 1500         # これより広い内側の開口は扉ではなくガラス戸（テラスと居間の間。v5 の平面ではガラスの線）
WALL_T = 250             # 外壁の厚さ（RevG）
PARAPET_T = 125          # 植栽の煉瓦の手すりの厚さ（RevE の煉瓦の手すりと同じ）
ROAD_Z = -PL             # 道路の高さ（1階の床から）
BOUNDARY = (200, 1200)   # 敷地の塀 厚さ・高さ（植栽の地盤から）。v5 1階平面に灰色の帯（西・北・東）

# ---- 縮尺読み（立面・断面）
PARAPET_RF = 1140        # 屋上のパラペット: 屋根から約 1.14 m（西立面）
ROOF_ROOM = 2900         # 屋上の階段室: 屋根から約 2.9 m（断面）
PLANTER_H = 1250         # 植栽の煉瓦の手すり: 北 1.24 m（西立面）・南 1.25 m（南立面）
SB_FRONT = 2500          # 前面の後退 2.5 m（old/寸法図_PDF261027 の値。根拠は未確認。v5 1階平面の縮尺読み 2.42 m と 0.1 m 以内）

# ---- v5 で RevG から変わった点（G+8 の基準階 1〜8F。縮尺読みは v5 p2 の G+8 1〜8F 平面）
VOID = (0, 9750, 5393.8, 15000)  # 左奥: 1〜8F に無い。1階ではその上が「Roof」（面積表 136.60 = 164.92 − 5.394 × 5.25 と整合）
ROOM_EDIT = {  # RevG の部屋（外接の長方形）→ v5
    (250, 4175, 1687.5, 5425): (250, 4175, 1687.5, 6450),     # 浴室2: 北へ延びる（寝室3 との境の壁は v5 で y 6,467〜6,583）
    (1812.5, 4175, 3250, 5425): (1812.5, 4175, 3250, 6450),   # 浴室3: 同上
    (250, 5550, 3250, 9500): (250, 6575, 3250, 9500),         # 寝室3: 南の壁が北へ 1,025 mm
}
OPEN_DEL = [
    (3243.8, 4400, 3384.4, 5200),    # 居間→浴室3 の扉: v5 では壁が続く（浴室3 は寝室3 から入る）
    (5268.8, 10250, 5593.8, 11250),  # EV ホール→玄関ホールの扉: 玄関ホールが無い（コアの西の壁は外壁になる）
]
DOOR_ADD = [  # (x0, y0, x1, y1, 開く向き, 形)。開く向きは +1 で x／y の増える側。形 1 片開き・2 両開き
    (5900, 9500, 6800, 9950, -1, 2),   # ENT.（住戸の玄関）: EV ホールから入る両開き、幅 0.9 m（x 5,907〜6,779）。住戸の壁とコアの壁を貫く
    (450, 4050, 1050, 4175, 1, 1),     # 浴室2 の扉: 寝室2 から（弧 x 約 500〜880、幅 0.6 m）
    (2550, 6450, 3150, 6575, -1, 1),   # 浴室3 の扉: 寝室3 から（弧 x 約 2,656〜3,164、幅 0.6 m）
]
SWING = {  # RevG の扉の中心 (x, y) → 開く向き（仮定。v5 に弧が描かれているものはそれに合わせる）。"ev" は EV の扉
    (3314, 3550): -1,     # 寝室2: 寝室2 へ（v5）
    (6989, 3550): 1,      # 主寝室: 主寝室へ
    (9959, 4111): -1,     # 主寝室浴室: 主寝室へ（外開き、v5）
    (3314, 7525): -1,     # 寝室3: 寝室3 へ（v5）
    (6989, 6575): -1,     # 共用浴室（障害者対応）: 居間へ（外開き）
    (6989, 8475): 1,      # 台所: 台所へ
    (6989, 4675): 1,      # クローゼット: クローゼットへ
    (8144, 10550): 1,     # 階段室: 階段室へ（v5 基準階。1階は EV ホールへ、v5 1階平面）
    (6819, 12050): "ev",  # EV
}
# 外壁の窓・開口（1〜8F）: (x0, y0, x1, y1, 種類, 下端, 上端, ガラスの割り)。種類 win 窓・vent 換気窓・open 開口（ガラスなし）
WIN_TYP = [
    (0, 1200, 250, 8400, "win", 1250, 2150, 8),         # 西面の横長窓（西立面: ガラス y 1,250〜8,360・床から 1.37〜2.05 m、枠を含めて約 1.26〜2.15 m、8枚割り。平面の部屋ごとの窓ではなく立面を採る、了承済み）
    (1100, 0, 3150, 250, "win", *WIN, 2),               # 寝室2 の南（x は RevG、高さと2枚割りは南立面）
    (3375, 0, 5271.7, 250, "open", 1250, TYP_H - BEAM[1], 0),  # テラスの南（南立面 床から 1.26〜2.46 m、下は煉瓦の手すり壁。上端は梁の下端）
    (7693.8, 0, 9893.8, 250, "win", *WIN, 2),           # 主寝室の南（v5 平面 x 7,620〜9,920。左端は南の植栽の左端、右端は RevG の開口の右端）
    (10743.8, 1100, 10993.8, 3712.5, "win", *WIN, 3),   # 主寝室の東（RevG）
    (10743.8, 4512.5, 10993.8, 6350, "vent", *VENT, 1), # 主寝室浴室の東（RevG）
    (10743.8, 7450, 10993.8, 8650, "win", *WIN, 2),     # 台所の東（RevG）
    (10693.8, 13700, 10993.8, 14150, "vent", *VENT, 1), # 階段室の東（RevG）
    (1100, 9500, 3150, 9750, "win", *WIN, 2),           # 寝室3 の北、植栽へ（v5 平面 x 1,070〜3,140）
    (3850, 9500, 4450, 9750, "win", *WIN, 1),           # 居間の北（v5 平面 x 3,843〜4,450）
]
N_PLANTER = (0, 9750, 3375, 10720)        # 寝室3 の北の植栽（平面 y 9,750〜10,720 を採る、了承済み。東端は間仕切りの東の面）
S_PLANTER = (7693.8, -1000, 10993.8, 0)   # 主寝室の南の植栽（幅 3.3 m を採る、了承済み。RevG の寸法線 x 7,693.8〜10,993.8・奥行 1.00）
TERRACE_BEDS = [(3375, 300, 3725, 2750), (4921.7, 300, 5271.7, 2750)]  # テラスの両側の植栽（x 3,380〜3,736・4,843〜5,236）

# ---- 1階（v5 p2 G+8 1階平面・南立面の縮尺読み）
GF_SPACE = [(250, 250, 10743.8, 9750), (250, 9750, 5393.8, 14750)]  # 駐車場・車路。西・東・北に壁（No Soft Story の注記）
WIN_GF = [
    (1080, 0, 5250, 250, "open", 0, DOOR_H, 0),          # 車路の入口（南立面 x 1,080〜5,250）
    (5590, 0, 6660, 250, "open", 0, DOOR_H, 0),          # 歩行者の入口（同 x 5,590〜6,660）
    (6660, 0, 9893.8, 250, "open", 1170, DOOR_H, 0),     # 駐車 1 の前の高い開口（同 x 6,660〜9,950・床から約 1.17 m。右端は上階の窓にそろえる）
    (5593.8, 9750, 7000, 9950, "open", 0, DOOR_H, 0),    # EV ホールの南（1階平面: コアの南の壁が x 約 5,100〜7,000 で無い）
    (10693.8, 13700, 10993.8, 14150, "vent", *VENT, 1),  # 階段室の東（RevG）
]
GF_COL_ADD = [(4993.8, 8950, 5393.8, 9550)]   # RevG の柱のうち1階だけにあるもの（v5 1階平面で灰色。1〜8F 平面には描かれていない）
STOCK = {"r": (8243.8, 11200, 9393.8, 13600), "door": (8400, 11100, 9200, 11200), "h": 3150, "mid": 1650}  # 階段の下の Stock（1階平面: 西半分、南の端に扉）。r は室内、扉の壁は y 11,100〜11,200
PARK = [(7000, 800, 10743.8, 8650, 4, "y"), (250, 9750, 5393.8, 14750, 2, "x")]  # 駐車 1〜4（東、x 6,963〜10,740・y 794〜8,646）・5〜6（左奥の Roof の下）
DRIVE = (250, 250, 5130, 9750)                # 車路の煉瓦敷き（建物の中 x 165〜5,130）
DRIVE_OUT = (1080, 5250)                      # 前庭の車路（坂、道路から1階の床まで）
TACTILE = [(6200, 250, 6800, 9000), (5550, 9000, 7350, 9750)]  # 点字ブロック（帯 x 6,170〜6,870、EV の前 x 5,520〜7,350）
STEPS = {"x": (5527, 7392), "y": (-1783, -560), "n": 4}  # 歩行者の段（x 5,527〜7,392、段 y −1,783〜−560、その上は踊り場）。道路から 4 段
STAIR = {"w": 1150, "land": 1150, "tread": 250, "rmax": 175}  # 階段 幅・踊り場・踏面（CM-03・RevE と同じ。DBR 第57条の値は検図の LAW）

ROOM_EN = {"寝室2": ("B.R.2", "寝室2", "B"), "テラス": ("Terrace", "テラス", "T"), "主寝室": ("Master Bedroom", "主寝室", "B"),
           "浴室2": ("Bath", "浴室", "W"), "浴室3": ("Bath", "浴室", "W"), "寝室3": ("B.R.3", "寝室3", "B"),
           "リビング・ダイニング": ("Living Dining", "リビング・ダイニング", "L"), "共用浴室（障害者対応）": ("Bath (accessible)", "共用浴室（障害者対応）", "W"),
           "主寝室浴室": ("Master bath", "主寝室浴室", "W"), "PS": ("PS", "PS", "S"), "台所": ("Kitchen", "台所", "K"),
           "": ("Closet", "クローゼット", "S"), "階段・加圧": ("Stair", "階段（加圧）", "C"), "EVホール": ("Lift hall", "EV ホール", "C"), "EV": ("Lift", "EV", "C")}


# ======== DXF
def read_entities(path):
    raw = path.read_bytes().decode("utf-8")
    lines = [l.strip() for l in raw.replace("\r\n", "\n").split("\n")]
    pairs = list(zip(lines[0::2], lines[1::2]))
    j = next(k for k, p in enumerate(pairs) if p == ("2", "ENTITIES"))
    ents, cur = [], None
    for c, v in pairs[j + 1:]:
        if c == "0":
            if cur:
                ents.append(cur)
            if v == "ENDSEC":
                break
            cur = {"type": v, "g": []}
        elif cur is not None:
            cur["g"].append((c, v))
    return ents


def get(e, code):
    return next((v for c, v in e["g"] if c == code), None)


def pts(e):
    xs = [float(v) for c, v in e["g"] if c == "10"]
    ys = [float(v) for c, v in e["g"] if c == "20"]
    return [(round(x, 1), round(y, 1)) for x, y in zip(xs, ys)]


def bbox(p):
    return (min(q[0] for q in p), min(q[1] for q in p), max(q[0] for q in p), max(q[1] for q in p))


def rpoly(r):
    return [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]


def within(a, b, t=1):
    return a[0] >= b[0] - t and a[1] >= b[1] - t and a[2] <= b[2] + t and a[3] <= b[3] + t


def same(a, b, t=1):
    return all(abs(p - q) <= t for p, q in zip(a, b))


def inside(poly, x, y):
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def poly_area(p):
    return abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))) / 2


def revg():
    """RevG の DXF の基準階（v5 の変更を当てる前）。部屋は多角形のまま持つ（主寝室は L 字）。"""
    ents = read_entities(SRC)
    polys = [(get(e, "8"), pts(e)) for e in ents if e["type"] == "LWPOLYLINE" and int(get(e, "70") or 0) & 1]
    l5 = [p for ly, p in polys if ly == "5"]
    big = max(l5, key=lambda p: poly_area(p))
    rooms = [p for p in l5 if p is not big and min(bbox(p)[2] - bbox(p)[0], bbox(p)[3] - bbox(p)[1]) >= 400]
    core = max((p for p in rooms if any(q is not p and within(bbox(q), bbox(p)) for q in rooms)), key=poly_area)
    rooms = [p for p in rooms if p is not core]
    texts = [(get(e, "1"), float(get(e, "10")), float(get(e, "20"))) for e in ents if e["type"] == "TEXT" and get(e, "8") == "3"]
    named = []
    for p in rooms:
        ts = sorted([t for t in texts if inside(p, t[1], t[2])], key=lambda t: -t[2])
        name = "".join(t[0] for t in ts if "㎡" not in t[0] and t[0] not in ("UP", "EPS") and "kg" not in t[0])
        at = next(((t[1], t[2]) for t in ts if t[0] not in ("UP", "EPS") and "㎡" not in t[0] and "kg" not in t[0]), None)
        named.append({"poly": p, "name": name, "at": at})
    return {"outline": bbox(big), "core": bbox(core), "rooms": named,
            "cols": [bbox(p) for ly, p in polys if ly == "4"], "opens": [bbox(p) for ly, p in polys if ly == "8"],
            "eps": [bbox(p) for ly, p in polys if ly == "6"]}


# ======== 平面（v5）
def plan():
    """RevG に v5 の変更を当てた平面。1階・基準階・屋上で使う部屋・柱・開口。"""
    g = revg()
    ol, co = g["outline"], g["core"]
    W, D, UY, CX0 = ol[2], ol[3], co[1], co[0]
    rooms, core_rooms = [], []
    for q in g["rooms"]:
        b = bbox(q["poly"])
        if within(b, VOID):
            continue
        e = next((v for k, v in ROOM_EDIT.items() if same(k, b)), None)
        poly = rpoly(e) if e else q["poly"]
        en, ja, cat = ROOM_EN[q["name"]]
        at = q["at"] if q["at"] and inside(poly, *q["at"]) else ((bbox(poly)[0] + bbox(poly)[2]) / 2, (bbox(poly)[1] + bbox(poly)[3]) / 2)
        rm = {"poly": poly, "name": q["name"], "en": en, "ja": ja, "cat": cat, "at": at}
        (core_rooms if within(b, co) else rooms).append(rm)
    stair = next(bbox(r["poly"]) for r in core_rooms if r["name"] == "階段・加圧")
    ev = next(bbox(r["poly"]) for r in core_rooms if r["name"] == "EV")
    corners = [c for c in g["cols"] if (c[0] <= 1 or c[2] >= W - 1) and (c[1] <= 1 or abs(c[3] - UY) <= 1)]
    on_face = lambda r: (r[1] <= ol[1] + 1 and r[3] <= ol[1] + 351) or (r[3] >= ol[3] - 1 and r[1] >= ol[3] - 351) or \
        (r[0] <= ol[0] + 1 and r[2] <= ol[0] + 351) or (r[2] >= ol[2] - 1 and r[0] >= ol[2] - 351)
    inner = []
    for r in g["opens"]:
        if on_face(r) or within(r, VOID) or any(same(r, d) for d in OPEN_DEL):
            continue
        w = max(r[2] - r[0], r[3] - r[1])
        if w > PASSAGE_W:
            inner.append({"r": r, "kind": "sl", "z": (0, DOOR_H), "panes": 2})
            continue
        c = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        key = min(SWING, key=lambda k: (k[0] - c[0]) ** 2 + (k[1] - c[1]) ** 2)
        if (key[0] - c[0]) ** 2 + (key[1] - c[1]) ** 2 > 200 ** 2:
            raise ValueError(f"扉の開く向きが決まっていない: 中心 ({c[0]:.0f}, {c[1]:.0f})")
        sw = SWING[key]
        inner.append({"r": r, "kind": "door", "z": (0, DOOR_H), "sw": 1 if sw == "ev" else sw, "style": "ev" if sw == "ev" else 1,
                      "core": within(r, co), "stair": key == (8144, 10550)})
    for x0, y0, x1, y1, sw, st in DOOR_ADD:
        inner.append({"r": (x0, y0, x1, y1), "kind": "door", "z": (0, DOOR_H), "sw": sw, "style": st, "main": st == 2, "core": False})
    return {"W": W, "D": D, "UY": UY, "CX0": CX0, "core": co, "rooms": rooms, "core_rooms": core_rooms, "stair": stair, "ev": ev,
            "corners": corners, "inner": inner, "eps": g["eps"], "src_cols": g["cols"]}


def win_list(rows):
    return [{"r": r[:4], "kind": r[4], "z": (r[5], r[6]), "panes": r[7]} for r in rows]


# ======== 箱を作る
def rects_minus(base, holes):
    """長方形の集まり base から holes を除いた範囲を、重ならない長方形に分ける。"""
    xs = sorted({v for r in base + holes for v in (r[0], r[2])})
    ys = sorted({v for r in base + holes for v in (r[1], r[3])})
    hit = lambda rs, x, y: any(r[0] < x < r[2] and r[1] < y < r[3] for r in rs)
    runs = []
    for j in range(len(ys) - 1):
        cy, run = (ys[j] + ys[j + 1]) / 2, None
        for i in range(len(xs) - 1):
            cx = (xs[i] + xs[i + 1]) / 2
            if hit(base, cx, cy) and not hit(holes, cx, cy):
                if run:
                    run[2] = xs[i + 1]
                else:
                    run = [xs[i], ys[j], xs[i + 1], ys[j + 1]]
            elif run:
                runs.append(run)
                run = None
        if run:
            runs.append(run)
    return merge_v(runs)


def merge_v(rs, key=lambda r: ()):
    """x の範囲と key が同じで、上下に接する長方形を結合する。"""
    out = []
    for r in sorted(rs, key=lambda r: (r[0], r[2], key(r), r[1])):
        p = out[-1] if out else None
        if p and p[0] == r[0] and p[2] == r[2] and key(p) == key(r) and abs(p[3] - r[1]) < 1e-6:
            p[3] = r[3]
        else:
            out.append(list(r))
    return out


def wall_key(c, P):
    """壁の材料: brick 南面の煉瓦、conc 打ち放し（西・東・北の外壁とコア。東・北は仮定）、part 間仕切り（煉瓦の長手積み）。"""
    x0, y0, x1, y1 = c
    if y0 <= 1:
        return "brick"
    if x0 >= P["CX0"] - 1 and y0 >= P["UY"] - 1:
        return "conc"
    if x0 <= 1 or x1 >= P["W"] - 1 or y1 >= P["D"] - 1 or (y1 >= P["UY"] - 1 and x1 <= P["CX0"] + 1):
        return "conc"
    return "part"


def walls(P, outline, rooms, cols, opens, h):
    """壁の箱 [x0, y0, x1, y1, z0, z1, 材料]（z は階の床から）。外形の中で、部屋でも柱でもない範囲。
    開口の範囲は、下端より下と上端より上だけ残す。柱は別に描く。"""
    xs = sorted({p[0] for p in outline} | {p[0] for r in rooms for p in r} | {v for c in cols for v in (c[0], c[2])} | {v for o in opens for v in (o["r"][0], o["r"][2])})
    ys = sorted({p[1] for p in outline} | {p[1] for r in rooms for p in r} | {v for c in cols for v in (c[1], c[3])} | {v for o in opens for v in (o["r"][1], o["r"][3])})
    out = []
    for j in range(len(ys) - 1):
        cy, run = (ys[j] + ys[j + 1]) / 2, None
        for i in range(len(xs) - 1):
            cx, key = (xs[i] + xs[i + 1]) / 2, None
            if inside(outline, cx, cy) and not any(inside(r, cx, cy) for r in rooms) and not any(c[0] < cx < c[2] and c[1] < cy < c[3] for c in cols):
                op = next((o for o in opens if o["r"][0] < cx < o["r"][2] and o["r"][1] < cy < o["r"][3]), None)
                segs = ((0, h),) if not op else tuple(s for s in ((0, op["z"][0]), (op["z"][1], h)) if s[1] - s[0] > 1)
                key = (segs, wall_key((xs[i], ys[j], xs[i + 1], ys[j + 1]), P))
            if run and key is not None and key == run[2]:
                run[1] = xs[i + 1]
                continue
            if run:
                out += [[run[0], ys[j], run[1], ys[j + 1], s0, s1, run[2][1]] for s0, s1 in run[2][0]]
            run = [xs[i], xs[i + 1], key] if key is not None else None
        if run:
            out += [[run[0], ys[j], run[1], ys[j + 1], s0, s1, run[2][1]] for s0, s1 in run[2][0]]
    return merge_v(out, key=lambda r: (r[4], r[5], r[6]))


def frames(o):
    """窓・ガラス戸の枠とガラス（壁の厚さの中央）。開口（open）は何も描かない。"""
    r, (z0, z1), kind, n = o["r"], o["z"], o["kind"], max(1, o.get("panes", 1))
    if kind == "open":
        return []
    vert = (r[2] - r[0]) < (r[3] - r[1])
    c = (r[0] + r[2]) / 2 if vert else (r[1] + r[3]) / 2
    a, b = (r[1], r[3]) if vert else (r[0], r[2])
    f, dp = 50, 80
    fb = lambda a0, a1, b0, b1, key, t: [c - t / 2, a0, c + t / 2, a1, b0, b1, key] if vert else [a0, c - t / 2, a1, c + t / 2, b0, b1, key]
    out = [fb(a, b, z0, z0 + f, "fr", dp), fb(a, b, z1 - f, z1, "fr", dp), fb(a, a + f, z0 + f, z1 - f, "fr", dp), fb(b - f, b, z0 + f, z1 - f, "fr", dp)]
    for k in range(1, n):
        m = a + (b - a) * k / n
        out.append(fb(m - f / 2, m + f / 2, z0 + f, z1 - f, "fr", dp))
    out.append(fb(a + f, b - f, z0 + f, z1 - f, "vt" if kind == "vent" else "gl", 10))
    return out


def leaves(o):
    """扉の戸（開いた状態、RevE と同じ描き方）。EV は閉じた金属の戸。"""
    r, sw, st = o["r"], o["sw"], o["style"]
    vert = (r[2] - r[0]) < (r[3] - r[1])
    a0, a1 = (r[1], r[3]) if vert else (r[0], r[2])
    if st == "ev":
        c = (r[0] + r[2]) / 2 if vert else (r[1] + r[3]) / 2
        return [[c - 20, a0, c + 20, a1, 0, DOOR_H, "metal"] if vert else [a0, c - 20, a1, c + 20, 0, DOOR_H, "metal"]]
    plane = (r[2] if sw > 0 else r[0]) if vert else (r[3] if sw > 0 else r[1])
    hinges = [(a0, 1)] if st == 1 else [(a0, 1), (a1, -1)]
    w = (a1 - a0) / len(hinges) - 40
    s0, s1 = sorted((plane, plane + sw * w))
    out = []
    for hp, d in hinges:
        b0, b1 = (hp + 20, hp + 60) if d > 0 else (hp - 60, hp - 20)
        out.append([s0, b0, s1, b1, 0, DOOR_H - 20, "leafX" if o.get("main") else "leaf"] if vert else [b0, s0, b1, s1, 0, DOOR_H - 20, "leafX" if o.get("main") else "leaf"])
    return out


def swing_rect(o):
    r, sw = o["r"], o["sw"]
    vert = (r[2] - r[0]) < (r[3] - r[1])
    a0, a1 = (r[1], r[3]) if vert else (r[0], r[2])
    plane = (r[2] if sw > 0 else r[0]) if vert else (r[3] if sw > 0 else r[1])
    w = (a1 - a0) / (1 if o["style"] == 1 else 2)
    s0, s1 = sorted((plane, plane + sw * w))
    return (s0, a0, s1, a1) if vert else (a0, s0, a1, s1)


def riser(h):
    n = math.ceil(h / STAIR["rmax"] - 1e-9)
    return n + n % 2


def stair_geo(P, h):
    """階段の1層分（v5: 東半分を北へ上がり、北の踊り場で折り返して西半分を南へ）。戻り値 (箱, 床の踊り場の北端)。"""
    s, n = P["stair"], riser(h)
    r, m, t, w = h / n, n // 2, STAIR["tread"], STAIR["w"]
    ve = s[3] - STAIR["land"]
    start = ve - (m - 1) * t
    out = []
    for j in range(1, m):
        top = j * r
        out.append([s[2] - w, start + (j - 1) * t, s[2], start + j * t, max(0, top - r - 150), top, "stair"])
    out.append([s[0], ve, s[2], s[3], h / 2 - 150, h / 2, "stair"])
    for j in range(1, m):
        top = h / 2 + j * r
        out.append([s[0], ve - j * t, s[0] + w, ve - (j - 1) * t, top - r - 150, top, "stair"])
    return out, start


def slab_rects(P, level, h_below, h_this):
    """床スラブの長方形（階段の吹抜けと昇降路を除く）。level 1 は左奥（Roof）まで含む全面。"""
    W, D, UY, CX0 = P["W"], P["D"], P["UY"], P["CX0"]
    base = [(0, 0, W, D)] if level <= 1 else [(0, 0, W, UY), (CX0, UY, W, D)]
    if level == 0:
        return [list(b) for b in base]
    s, w = P["stair"], STAIR["w"]
    lw = stair_geo(P, h_below)[1]                      # 下の階から上がってくる西半分の踊り場の北端
    le = stair_geo(P, h_this)[1] if h_this else lw     # 上へ上がる東半分の踊り場の北端（屋上は上がらない）
    holes = [(s[0], lw, s[0] + w, s[3]), (s[0] + w, min(lw, le), s[2] - w, s[3]), (s[2] - w, le, s[2], s[3]), tuple(P["ev"])]
    return rects_minus(base, holes)


def planter(r, side, slab):
    """植栽（煉瓦の手すり 3辺、土、植物）。side は建物に付く側（'S' 南の壁に付く・'N' 北）。"""
    x0, y0, x1, y1 = r
    t, h = PARAPET_T, PLANTER_H
    out = [[x0, y0, x1, y1, -SLAB, 0, "pl"]] if slab else []
    if side == "N":   # 建物の北に付く: 西・北・東
        out += [[x0, y0, x0 + t, y1, 0, h, "brick"], [x0 + t, y1 - t, x1, y1, 0, h, "brick"], [x1 - t, y0, x1, y1 - t, 0, h, "brick"]]
    else:             # 建物の南に付く: 西・南・東
        out += [[x0, y0, x0 + t, y1, 0, h, "brick"], [x0 + t, y0, x1 - t, y0 + t, 0, h, "brick"], [x1 - t, y0, x1, y1, 0, h, "brick"]]
    return out


def clumps(r, n, z):
    """植物の株の中心 [x, y, z, 大きさ]（土の上に n 株を並べる）。"""
    x0, y0, x1, y1 = r
    long_x = (x1 - x0) >= (y1 - y0)
    s = min(x1 - x0, y1 - y0)
    return [[round(x0 + (x1 - x0) * (k + 0.5) / n, 1) if long_x else round((x0 + x1) / 2, 1),
             round((y0 + y1) / 2, 1) if long_x else round(y0 + (y1 - y0) * (k + 0.5) / n, 1), z, round(s, 1)] for k in range(n)]


def storey(P, kind, h, h_below=None):
    """1層分の箱（z は階の床から）。kind: gf 1階、l1 1F、typ 2〜8F、rf 屋上。"""
    W, D, UY, CX0 = P["W"], P["D"], P["UY"], P["CX0"]
    co, st = P["core"], P["stair"]
    hw = h - SLAB
    out, plants = [], []
    L_ol = [(0, 0), (W, 0), (W, D), (CX0, D), (CX0, UY), (0, UY)]
    croom = [r["poly"] for r in P["core_rooms"]]
    if kind == "gf":   # 階段室の扉は1階だけ EV ホールへ開く（v5 1階平面）
        opens = win_list(WIN_GF) + [dict(o, sw=-1) if o.get("stair") else o for o in P["inner"] if o.get("core")]
        stock_door = {"r": STOCK["door"], "kind": "door", "z": (0, DOOR_H), "sw": 1, "style": 1, "sub": True}   # sub: 階段室の中を仕切る壁の扉
        cols = P["corners"] + GF_COL_ADD
        out += walls(P, rpoly((0, 0, W, D)), [rpoly(r) for r in GF_SPACE] + croom, cols, opens, hw)
        sr = STOCK["r"]   # Stock の南の壁（扉付き）と、東の低い壁（階段の間）。煉瓦の間仕切り
        dr = STOCK["door"]
        out += [b[:6] + ["part"] for b in walls(P, rpoly((sr[0], dr[1], sr[2], dr[3])), [], [], [stock_door], STOCK["h"])]
        out += [[sr[2], dr[1], sr[2] + (st[2] - st[0] - 2 * STAIR["w"]), sr[3], 0, STOCK["mid"], "part"]]
        out += [[*b[:6], "fl_gf" + ("S" if b[1] <= 1 else "")] for b in [[0, 0, W, D, ROAD_Z, 0]]]
        out += [[*P["ev"][:4], -1, 1, "dark"]]
        opens.append(stock_door)
    elif kind == "rf":
        opens = [o for o in P["inner"] if o.get("stair")] + win_list([WIN_TYP[7]])
        opens.append({"r": (9000, UY, 9900, co[1] + 200), "kind": "door", "z": (0, DOOR_H), "sw": -1, "style": 1})   # 屋上への扉（仮定）
        cols = []
        out += walls(P, rpoly(co), croom, cols, opens, ROOF_ROOM - SLAB)
        out += [[co[0], co[1], co[2], co[3], ROOF_ROOM - SLAB, ROOF_ROOM, "conc"]]
        p = PARAPET_RF
        out += [[0, 0, W, WALL_T, 0, p, "brick"], [0, WALL_T, WALL_T, UY, 0, p, "conc"], [W - WALL_T, WALL_T, W, UY, 0, p, "conc"], [WALL_T, UY - WALL_T, CX0, UY, 0, p, "conc"]]
    else:
        opens = win_list(WIN_TYP) + P["inner"]
        cols = P["corners"]
        out += walls(P, L_ol, [r["poly"] for r in P["rooms"]] + croom, cols, opens, hw)
        out += planter(N_PLANTER, "N", kind != "l1") + planter(S_PLANTER, "S", True)
        soil = [(150, 9800, 1200, 10550), (2300, 9800, 3200, 10550), (7900, -850, 10750, -350)] + TERRACE_BEDS
        out += [[*r, 0, 450 if i < 3 else 400, "soil"] for i, r in enumerate(soil)]
        for i, r in enumerate(soil):
            plants += clumps(r, [1, 1, 5, 4, 4][i], 450 if i < 3 else 400)
    for c in cols:
        out.append([*c, 0, hw, "concS" if c[1] <= 1 else "conc"])
    for o in opens:
        out += leaves(o) if o["kind"] == "door" else frames(o)
    if kind != "rf":
        for e in P["eps"]:
            out.append([*e, 0, hw, "eps"])
    if kind != "gf":   # 床スラブと、その下の梁（下の階の天井）
        lvl = {"l1": 1, "typ": 2, "rf": 9}[kind]
        for r in slab_rects(P, lvl, h_below, h if kind != "rf" else None):
            out.append([*r, -SLAB, 0, ("fl_rf" if kind == "rf" else "fl_typ") + ("S" if r[1] <= 1 else "")])
        out.append([WALL_T, 4112.5 - BEAM[0] / 2, W - WALL_T, 4112.5 + BEAM[0] / 2, -BEAM[1], -SLAB, "beam"])
        if kind == "l1":   # 1階の左奥（駐車 5・6）の南の縁の梁。2階より上は壁の中
            out.append([WALL_T, UY - BEAM[0], CX0, UY, -BEAM[1], -SLAB, "beam"])
    if kind != "rf":
        out += stair_geo(P, h)[0]
    return [[round(v, 1) if isinstance(v, float) else v for v in b] for b in out], plants, opens


def site(P):
    """敷地・道路・塀・植栽の地盤・車路の坂・段（z は1階の床から）。"""
    W, D = P["W"], P["D"]
    sx0, sx1 = -(SITE_W - W) / 2, W + (SITE_W - W) / 2
    sy0, sy1 = -SB_FRONT, -SB_FRONT + SITE_D
    t, bh = BOUNDARY
    gz = ROAD_Z + SITE_UP
    out = [[sx0, sy0, sx1, sy1, ROAD_Z - 150, ROAD_Z, "ground"],
           [sx0 - 30000, sy0 - ROAD_W, sx1 + 30000, sy0, ROAD_Z - 200, ROAD_Z - 10, "road"]]
    x = sx0 - 28000
    while x < sx1 + 28000:
        out.append([x, sy0 - ROAD_W / 2 - 75, x + 3000, sy0 - ROAD_W / 2 + 75, ROAD_Z - 10, ROAD_Z - 5, "line"])
        x += 6000
    beds = [(sx0 + t, sy0, 0, sy1 - t), (0, D, W, sy1 - t), (W, sy0, sx1 - t, sy1 - t), (0, sy0, DRIVE_OUT[0], 0), (STEPS["x"][1], sy0, W, 0)]
    out += [[*b, ROAD_Z, gz, "green"] for b in beds]
    out += [[sx0, sy0, sx0 + t, sy1, ROAD_Z, gz + bh, "wallS"], [sx0 + t, sy1 - t, sx1 - t, sy1, ROAD_Z, gz + bh, "wallS"], [sx1 - t, sy0, sx1, sy1, ROAD_Z, gz + bh, "wallS"]]
    n, (x0, x1), (ya, yb) = STEPS["n"], STEPS["x"], STEPS["y"]
    r, d = -ROAD_Z / n, (yb - ya) / (n - 1)
    for k in range(1, n):
        out.append([x0, ya + (k - 1) * d, x1, ya + k * d, ROAD_Z, ROAD_Z + k * r, "step"])
    out.append([x0, yb, x1, 0, ROAD_Z, 0, "tact"])
    ramp = [DRIVE_OUT[0], sy0, DRIVE_OUT[1], 0, ROAD_Z, 0]
    return [[round(v, 1) if isinstance(v, float) else v for v in b] for b in out], ramp, (sx0, sy0, sx1, sy1)


def model():
    """モデルに埋め込むデータ。"""
    P = plan()
    W, D = P["W"], P["D"]
    zs = [0.0] + [GF_H + i * TYP_H for i in range(N_TYP + 1)]
    names = ["GF"] + [f"{i}F" for i in range(1, N_TYP + 1)] + ["RF"]
    types, opens = {}, {}
    for k, h, hb in (("gf", GF_H, None), ("l1", TYP_H, GF_H), ("typ", TYP_H, TYP_H), ("rf", ROOF_ROOM, TYP_H)):
        b, p, o = storey(P, k, h, hb)
        types[k] = {"b": b, "p": p}
        opens[k] = o
    levels = [{"n": names[i], "z": round(zs[i], 1), "t": "gf" if i == 0 else "l1" if i == 1 else "rf" if i == N_TYP + 1 else "typ"} for i in range(len(zs))]
    sb, ramp, sr = site(P)
    rooms = [{"poly": r["poly"], "en": r["en"], "ja": r["ja"], "cat": r["cat"], "at": r["at"]} for r in P["rooms"] + P["core_rooms"]]
    gf_core = [dict(r, poly=r["poly"]) for r in rooms if r["cat"] == "C"]
    park = []
    for x0, y0, x1, y1, n, ax in PARK:
        for k in range(n):
            park.append([round(x0 + (x1 - x0) * k / n, 1), y0, round(x0 + (x1 - x0) * (k + 1) / n, 1), y1] if ax == "x" else
                        [x0, round(y0 + (y1 - y0) * k / n, 1), x1, round(y0 + (y1 - y0) * (k + 1) / n, 1)])
    return {
        "bld": [0, 0, W, D], "unitY": P["UY"], "coreX": P["CX0"], "void": list(VOID), "site": [round(v, 1) for v in sr], "roadW": ROAD_W, "roadZ": ROAD_Z,
        "levels": levels, "types": types, "siteB": sb, "ramp": ramp,
        "rooms": {"typ": rooms, "gf": gf_core},
        "gf": {"park": park, "drive": list(DRIVE), "tact": [list(t) for t in TACTILE], "stock": list(STOCK["r"]), "wheel": 14500},
        "dims": {"w": W_NOTE, "d": D_NOTE, "rf": round(zs[-1], 1), "top": round(zs[-1] + ROOF_ROOM, 1)},
        "src": [SRC.name, "01_TOHO_BASHUNDHARA_v5_261028_A3.pdf"],
    }, P, opens, zs


# ======== 検図（記入値・面積表・平面の整合）。階段の規定値の照合は check_model.py（LAW）
def check():
    found, notes = [], []
    try:
        d, P, opens, zs = model()
    except ValueError as e:
        return [str(e)], notes
    W, D, UY, CX0 = P["W"], P["D"], P["UY"], P["CX0"]
    # 記入寸法。許容 2 mm: RevG の外形 10,993.8 と記入値 10.995 m の差 1.2 mm と、記入値の丸め（小数3桁の m、±0.5 mm）
    tol = 2.0
    for name, val, note in (("幅", W, W_NOTE), ("奥行", D, D_NOTE), ("住戸の奥行", UY, UNIT_NOTE), ("コアの奥行", D - UY, CORE_NOTE)):
        if abs(val - note) > tol:
            found.append(f"記入寸法と違う: {name} {val:,.1f} mm（記入値 {note:,} mm、許容 ±{tol} mm）")
    hs = [zs[i + 1] - zs[i] for i in range(len(zs) - 1)]
    if abs(hs[0] - 12 * FT) > 0.1 or any(abs(h - 10 * FT) > 0.1 for h in hs[1:]) or len(hs) != 1 + 8:
        found.append(f"階高が記入値（GF 12′、1〜8F 10′）と違う: {[round(h, 1) for h in hs]}")
    top = zs[-1] + ROOF_ROOM - ROAD_Z
    if top > H_MAX:
        found.append(f"高さが H ≤ 33 m を超える: 道路から階段室の上端まで {top / 1000:.2f} m")
    notes.append(f"記入寸法: 幅 {W:,.1f}（10.995 m）・奥行 {D:,.0f}・住戸 {UY:,.0f}・コア {D - UY:,.0f} mm、GF {hs[0]:,.1f}・1〜8F {hs[1]:,.1f} mm、"
                 f"屋根 {(zs[-1] - ROAD_Z) / 1000:.2f} m・階段室の上端 {top / 1000:.2f} m（道路から、H ≤ 33 m）")
    # 面積表（m²、小数2桁）。許容: 幅の差 2 mm × 奥行 15 m ＝ 0.03 m² と、表の丸め 0.005 m²
    atol = tol * D / 1e6 + 0.005
    L_ol = [(0, 0), (W, 0), (W, D), (CX0, D), (CX0, UY), (0, UY)]
    for name, val, key in (("基準階", poly_area(L_ol) / 1e6, "typical"), ("建築面積", W * D / 1e6, "coverage"), ("敷地", SITE_W * SITE_D / 1e6, "plot")):
        if abs(val - AREA[key]) > atol:
            found.append(f"面積表と違う: {name} {val:.3f} m²（表 {AREA[key]:.2f} m²、許容 ±{atol:.3f}）")
        notes.append(f"面積: {name} {val:.3f} m²（表 {AREA[key]:.2f}）")
    # 平面の整合: 開口が壁の上にあるか（中心が部屋の中でない）、扉の開く側が部屋か、窓・扉の開きが柱と重ならないか
    ov = lambda a, b: a[0] < b[2] - 1 and b[0] < a[2] - 1 and a[1] < b[3] - 1 and b[1] < a[3] - 1
    croom = [r["poly"] for r in P["core_rooms"]]
    cases = (("基準階", opens["typ"], [r["poly"] for r in P["rooms"]] + croom, P["corners"]),
             ("1階", opens["gf"], [rpoly(s) for s in GF_SPACE] + croom + [rpoly(STOCK["r"])], P["corners"] + GF_COL_ADD))
    for lv, ops, spaces, cols in cases:
        for o in ops:
            r = o["r"]
            if not o.get("sub") and any(inside(p, (r[0] + r[2]) / 2, (r[1] + r[3]) / 2) for p in spaces):
                found.append(f"{lv}: 開口が壁の上にない {r}")
            area = swing_rect(o) if o["kind"] == "door" and o["style"] != "ev" else r
            if o["kind"] == "door" and o["style"] != "ev" and not any(inside(p, (area[0] + area[2]) / 2, (area[1] + area[3]) / 2) for p in spaces):
                found.append(f"{lv}: 扉の開く側に部屋がない {r}")
            for c in cols:
                if ov(area, c):
                    found.append(f"{lv}: {'扉の開き' if o['kind'] == 'door' else '窓・開口'}が柱と重なる {r} と柱 {c}")
    west = [o for o in opens["typ"] if o["kind"] != "door" and o["r"][0] <= 1 and o["r"][2] <= WALL_T + 1]
    if len(west) != 1:
        found.append(f"西面の窓が各階1本でない: {len(west)} 本（立面の横長窓を採る、了承済み）")
    if not same(N_PLANTER[1::2], (9750, 10720), 1) or abs(S_PLANTER[2] - S_PLANTER[0] - 3300) > 1:
        found.append("植栽の位置・幅が了承の値（北 y 9,750〜10,720、南 幅 3.3 m）と違う")
    notes.append(f"平面: 部屋 {len(P['rooms'])}・コア {len(P['core_rooms'])}・扉 {sum(o['kind'] == 'door' for o in opens['typ'])}・"
                 f"窓と開口 {sum(o['kind'] != 'door' for o in opens['typ'])}（基準階）、柱 {len(P['corners'])}（1階 {len(P['corners']) + len(GF_COL_ADD)}）")
    nb = sum(len(t["b"]) for t in d["types"].values())
    notes.append(f"箱 {nb}（1階 {len(d['types']['gf']['b'])}・1F {len(d['types']['l1']['b'])}・2〜8F {len(d['types']['typ']['b'])}・屋上 {len(d['types']['rf']['b'])}）、敷地 {len(d['siteB'])}")
    return found, notes


# ======== HTML
def texts(d, P, zs):
    hs = [zs[1] - zs[0], zs[2] - zs[1]]
    n0, n1 = riser(hs[0]), riser(hs[1])
    W, D, UY, CX0 = P["W"], P["D"], P["UY"], P["CX0"]
    L_ol = [(0, 0), (W, 0), (W, D), (CX0, D), (CX0, UY), (0, UY)]
    a_typ, a_cov, a_plot = poly_area(L_ol) / 1e6, W * D / 1e6, SITE_W * SITE_D / 1e6
    rf, top = (zs[-1] - ROAD_Z) / 1000, (zs[-1] + ROOF_ROOM - ROAD_Z) / 1000
    sb_side = (SITE_W - W) / 2000
    sb_rear = (SITE_D - SB_FRONT - D) / 1000
    t = {
        "en": {
            "title": "Apartment building G+8 — drawing set v5",
            "sub": "3D model of the v5 drawings (2026-10-28): one dwelling on each of floors 1F–8F over ground-floor parking, one stair and one lift at the rear right. Concept model.",
            "sSrcv": "v5 drawings, p2 (plans, west and south elevations, section) and the plan DXF RevG",
            "sSrcM": "Plan from RevG with the changes drawn in v5; heights from the v5 section and elevations",
            "sSitev": f"45′ × 64′ ({SITE_W / 1000:.2f} × {SITE_D / 1000:.2f} m). Road 25′ ({ROAD_W / 1000:.2f} m) on the south. Setbacks: front {SB_FRONT / 1000:.2f} m, rear {sb_rear:.2f} m, sides {sb_side:.2f} m.",
            "sBldv": f"10.995 × 15.000 m, G+8. Floors 1F–8F: dwelling 9.75 m deep, core 5.25 m behind it on the right; the rear left ({VOID[2] / 1000:.2f} × {CORE_NOTE / 1000:.2f} m) is open above the ground floor (“Roof”).",
            "sLvv": f"GF 12′ ({GF_H / 1000:.3f} m), 1F–8F 10′ ({TYP_H / 1000:.3f} m). Ground floor +1′-6″ above the road (assumed). Roof {rf:.2f} m above the road, parapet {PARAPET_RF / 1000:.2f} m, stair room {ROOF_ROOM / 1000:.2f} m high: top {top:.2f} m (H ≤ 33 m).",
            "sFinv": "West face fair-faced concrete (formwork 1,800 × 900, form ties @600 × @450) with one long window on each floor; south face exposed brick (English bond). East and north faces concrete (assumed: no drawing). Partitions brick, 125 mm, exposed.",
            "sUnitv": "B.R.2 and B.R.3, each with a bath; Master Bedroom with bath and closet; Living Dining entered at ENT. from the lift hall; Kitchen; accessible bath; Terrace with planters. Brick planter balconies north of B.R.3 and south of the Master Bedroom.",
            "sGfv": "Parking for 6 (1–4 on the east, 5–6 under the roof at the rear left), brick driveway, steps and tactile paving from the road to the lift hall, lift, stair, stock under the stair.",
            "sStv": f"One stair, flights 1.15 m: GF {n0} risers × {hs[0] / n0:.0f} mm, 1F–8F {n1} × {hs[1] / n1:.0f} mm, treads 250 mm; up the east flight, back on the west (as v5). Lift 1,600 kg (RevG).",
            "sStrv": f"RC. Four corner columns (v5 plan: “Wide Span”, “No Column”) and one more at the ground floor. Slab {SLAB} mm, beams {BEAM[0]} × {BEAM[1]} mm (assumed).",
            "sArv": f"Typical floor {a_typ:.2f} m² (table 136.60), building area {a_cov:.2f} m² (table 164.92), plot {a_plot:.2f} m² (table 267.56).",
            "note": "Concept model for discussion, not for construction. Where the v5 drawings disagree, this model takes: the ground-floor height as written (12′; drawn about 3.17 m); the west windows from the elevation (one long window; the plan shows one per room); the north planter from the plan; the south planter 3.3 m wide (the RevG line is 5.6 m). Window sizes, the east and north faces, slab, beams and levels are assumptions. Not checked: building and fire rules, structure.",
        },
        "ja": {
            "title": "集合住宅 G+8 — 図面一式 v5",
            "sub": "図面一式 v5（2026-10-28）の3Dモデル。1階は駐車場、1F〜8F に住戸が1戸ずつ、右奥に階段1本・EV 1台。概念モデル。",
            "sSrcv": "v5 の2頁（平面・西立面・南立面・断面）と、平面 DXF RevG",
            "sSrcM": "平面は RevG に v5 の変更を当てたもの、高さは v5 の断面・立面による",
            "sSitev": f"45′ × 64′（{SITE_W / 1000:.2f} × {SITE_D / 1000:.2f} m）。前面道路 25′（{ROAD_W / 1000:.2f} m）、南。後退: 前面 {SB_FRONT / 1000:.2f} m、背面 {sb_rear:.2f} m、両側 {sb_side:.2f} m。",
            "sBldv": f"10.995 × 15.000 m、G+8。1F〜8F は住戸の奥行 9.75 m、その北の右にコア 5.25 m。左奥（{VOID[2] / 1000:.2f} × {CORE_NOTE / 1000:.2f} m）は1階の上が空く（「Roof」）。",
            "sLvv": f"GF 12′（{GF_H / 1000:.3f} m）、1F〜8F 10′（{TYP_H / 1000:.3f} m）。1階の床は道路から +1′-6″（仮定）。屋根は道路から {rf:.2f} m、パラペット {PARAPET_RF / 1000:.2f} m、階段室の高さ {ROOF_ROOM / 1000:.2f} m で上端 {top:.2f} m（H ≤ 33 m）。",
            "sFinv": "西面は打ち放し（型枠 1,800 × 900、Pコン @600 × @450）で各階に横長の窓1本、南面は煉瓦（イングリッシュボンド）。東面・北面は打ち放し（図が無いので仮定）。間仕切りは煉瓦 125 mm、現し。",
            "sUnitv": "寝室2・寝室3（それぞれ浴室付き）、主寝室（浴室・クローゼット付き）、リビング・ダイニング（ENT. で EV ホールから入る）、台所、共用浴室（障害者対応）、テラス（植栽付き）。寝室3 の北と主寝室の南に、煉瓦の手すりの植栽バルコニー。",
            "sGfv": "駐車 6台（1〜4 は東、5・6 は左奥の屋根の下）、煉瓦敷きの車路、道路から EV ホールまでの段と点字ブロック、EV、階段、階段の下の Stock。",
            "sStv": f"1本、有効幅 1.15 m。GF は蹴上 {hs[0] / n0:.0f} mm × {n0} 段、1F〜8F は {hs[1] / n1:.0f} mm × {n1} 段、踏面 250 mm。東半分を上がり、西半分で戻る（v5 による）。EV 1,600 kg（RevG）。",
            "sStrv": f"RC。柱は四隅の4本（v5 の平面。注記「Wide Span」「No Column」）と、1階だけにもう1本。スラブ {SLAB} mm、梁 {BEAM[0]} × {BEAM[1]} mm（仮定）。",
            "sArv": f"基準階 {a_typ:.2f} m²（表 136.60）、建築面積 {a_cov:.2f} m²（表 164.92）、敷地 {a_plot:.2f} m²（表 267.56）。",
            "note": "協議用の概念モデルで、施工用ではありません。v5 の図の中で食い違う箇所は次のとおり採りました: 1階の高さは記入値の 12′（図は約 3.17 m）、西面の窓は立面の横長窓1本（平面は部屋ごとの窓）、北の植栽は平面の位置、南の植栽の幅は 3.3 m（RevG の線は 5.6 m）。窓の寸法、東面・北面、スラブ・梁・床の高さは仮定です。未照合: 建築・消防の法規、構造。",
        },
    }
    ui = {"en": dict(kDrawing="Drawing", kScale="Scale", kDate="Date", kRev="Rev.", vPersp="Perspective", vStreet="From the street", vSouth="South", vWest="West", vTop="Top",
                     zoom="Distance", dims="Dimensions", lvTag="Floors shown", zones="Room names", csTag="For Clip Studio (GLB)", glbAll="Save what is shown as GLB",
                     glbErr="The GLB exporter could not be loaded. Check the internet connection and reload the page.",
                     hint="Drag to rotate about the centre of the model; right-drag or Shift-drag moves the view sideways (arrow keys too, after clicking the view); a view button resets it. On a phone or tablet, drag with two fingers to move and pinch to zoom. Scroll or use the slider to zoom. Lower the floors slider to hide the floors above and look into a floor. The GLB holds what is shown and opens in Clip Studio as a 3D material (1 unit = 1 m).",
                     specH="Specification", sSrc="Source", sSite="Plot", sBld="Building", sLv="Levels", sFin="Finishes", sUnit="Dwelling", sGf="Ground floor", sSt="Stair, lift", sStr="Structure", sAr="Areas",
                     lv=[f"{n}" for n in ["GF"] + [f"{i}F" for i in range(1, N_TYP + 1)] + ["Roof"]], roof="Roof", ent="ENT.", stock="Stock"),
          "ja": dict(kDrawing="図番", kScale="縮尺", kDate="日付", kRev="版", vPersp="パース", vStreet="道路から", vSouth="南面", vWest="西面", vTop="上から",
                     zoom="距離", dims="寸法表示", lvTag="表示する階", zones="部屋名", csTag="Clip Studio 用（GLB）", glbAll="表示中のモデルを GLB で保存",
                     glbErr="GLB の書き出し機能を読み込めませんでした。インターネット接続を確かめて、ページを読み込み直してください。",
                     hint="ドラッグでモデルの中央を中心に回転、右ドラッグか Shift＋ドラッグで平行移動（画面をクリックしたあとは矢印キーでも可。視点のボタンで元に戻る）、スマートフォンでは2本指のドラッグで平行移動・つまんで拡大縮小、スクロールまたはスライダーで拡大縮小。「表示する階」を下げると上の階が外れ、その階の中が見えます。GLB には表示中のものが入り、Clip Studio に 3D 素材として読み込めます（1 単位 = 1 m）。",
                     specH="仕様", sSrc="元の図", sSite="敷地", sBld="建物", sLv="レベル", sFin="仕上げ", sUnit="住戸", sGf="1階", sSt="階段・EV", sStr="構造", sAr="面積",
                     lv=["GF"] + [f"{i}F" for i in range(1, N_TYP + 1)] + ["屋上"], roof="屋根", ent="ENT.", stock="Stock")}
    txt = {l: dict(ui[l], **t[l]) for l in ("en", "ja")}
    return txt


def html():
    d, P, opens, zs = model()
    txt = texts(d, P, zs)
    e = txt["en"]
    tpl = TPL.read_text(encoding="utf-8")
    rep = {"__TXT__": json.dumps(txt, ensure_ascii=False), "__DATA__": json.dumps(d, ensure_ascii=False, separators=(",", ":")),
           "__DRAWING__": DRAWING, "__DATE__": DATE, "__REV__": REV, "__SRC0__": d["src"][0], "__SRC1__": d["src"][1]}
    for k in ("title", "sub", "sSrcv", "sSrcM", "sSitev", "sBldv", "sLvv", "sFinv", "sUnitv", "sGfv", "sStv", "sStrv", "sArv", "note", "hint"):
        rep[f"__{k}__"] = e[k]
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    return tpl


# ======== 確認用の平面図
def preview(path):
    d, P, opens, zs = model()
    col = {"brick": "#b5532f", "conc": "#555", "part": "#d08a5c", "concS": "#333", "beam": None, "stair": "#cbb", "fr": "#378add", "gl": "#9cd", "vt": "#9cd",
           "leaf": "#d85a30", "leafX": "#a03a10", "metal": "#888", "pl": "#e3efd8", "soil": "#7a5", "eps": "#bbb", "dark": "#333"}
    parts = []
    W, D = P["W"], P["D"]
    for k, title in (("gf", "1階"), ("typ", "2〜8階（1F は左奥に屋根）"), ("rf", "屋上")):
        s = [f'<h3 style="font:16px sans-serif">{title}</h3><svg xmlns="http://www.w3.org/2000/svg" viewBox="-1800 {-(D + 1800)} {W + 3600} {D + 4400}" width="560" style="background:#fff">']
        bs = d["types"][k]["b"]
        for b in sorted(bs, key=lambda b: b[5]):
            if b[6].startswith("fl_"):
                s.append(f'<rect x="{b[0]}" y="{-b[3]}" width="{b[2] - b[0]}" height="{b[3] - b[1]}" fill="#f4f1ea"/>')
        for r in (d["rooms"]["typ"] if k == "typ" else d["rooms"]["gf"] if k == "gf" else []):
            s.append(f'<polygon points="{" ".join(f"{x},{-y}" for x, y in r["poly"])}" fill="#f6f1e6" stroke="#ddd" stroke-width="10"/>')
            s.append(f'<text x="{r["at"][0]}" y="{-r["at"][1]}" font-size="260" text-anchor="middle">{r["ja"]}</text>')
        for b in bs:
            c = col.get(b[6].rstrip("S"))
            if not c or b[6].startswith("fl_"):
                continue
            low = b[4] > 0 and b[6] in ("brick", "conc", "part")
            s.append(f'<rect x="{b[0]}" y="{-b[3]}" width="{max(b[2] - b[0], 20)}" height="{max(b[3] - b[1], 20)}" fill="{c}" fill-opacity="{0.35 if low else 0.9}"/>')
        s.append("</svg>")
        parts.append("".join(s))
    legend = '<p style="font:14px sans-serif">濃い灰＝打ち放し、茶＝南面の煉瓦、橙＝間仕切り、青＝窓、赤＝扉の戸（開いた状態）、薄い色＝開口の上下に残る壁、緑＝植栽</p>'
    Path(path).write_text('<!doctype html><meta charset="utf-8"><title>CM-06 平面の確認</title><body style="margin:8px;background:#fff">' + legend +
                          '<div style="display:flex;flex-wrap:wrap;gap:12px">' + "".join(f"<div>{p}</div>" for p in parts) + "</div></body>", encoding="utf-8")


if __name__ == "__main__":
    if "--html" in sys.argv:
        OUT.write_text(html(), encoding="utf-8", newline="\n")
        print("書き出し:", OUT.relative_to(ROOT).as_posix())
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
    f, n = check()
    print(f"検出 {len(f)}")
    for t in n:
        print("・" + t)
    for t in f:
        print("✗ " + t)
