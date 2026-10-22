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
 13. 修正指示用の DXF（dxf/ の最新）が、現行のモデルから書き出したものと同じか
 14. GLB の書き出し機能が three.js と同じ版で読み込まれ、保存ボタンがあるか
 15. 住戸 CM-01 と建物 CM-03 の一致（窓・掃出し窓・バルコニー・共用コア・玄関扉）と、住戸の家具と柱の重なり
 建物 CM-03: 規模、後退、階段・EV・高架水槽の規定、コアの配置、柱がバルコニーに立たないか（値は LAW の出典を参照）
 住戸: 家具が共用コア・バルコニーの壁と重ならないか、バルコニーには植物だけか

照合していない内容（未照合）:
  - 画面での見た目、ドラッグ操作、スマートフォン幅・ダークモードの表示
  - 寸法の前提（壁厚 250 mm、スラブ 125 mm、天井扇の高さなど）と原典・構造計算との照合
  - 扉・窓の寸法（高さ 7′、幅、腰高）と法規（BNBC など）・採光・換気の基準との照合

使い方:  python tools/check_model.py
終了コード: 検出 0 件なら 0、1 件以上なら 1。
"""
import json
import math
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
    m = re.search(r"const CORE=\{x0:([\d.]+),v0:([\d.]+),t:([\d.]+)\},BAL=\{x0:([\d.]+),x1:([\d.]+),d:([\d.]+)\};", js)
    if not m:
        return None
    g = list(map(float, m.groups()))
    out["CORE"] = {"x0": g[0], "v0": g[1], "t": g[2]}
    out["BAL"] = {"x0": g[3], "x1": g[4], "d": g[5]}
    dims = parse_dims(js)
    out["TF"] = dims[3] / FT if dims else 0.82
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
    if not op:
        return [("x", 0, 0, idp, 1, "L"), ("x", iw, 0, idp, -1, "R"), ("v", 0, 0, iw, 1, "F"), ("v", idp, 0, iw, -1, "B")]
    tf, co, ba = op["TF"], op["CORE"], op["BAL"]
    f = [("x", 0, 0, idp, 1, "L"), ("x", iw, 0, co["v0"], -1, "R"), ("v", 0, 0, ba["x0"] - tf, 1, "F"),
         ("v", 0, ba["x1"] + tf, iw, 1, "F"), ("v", ba["d"] + tf, ba["x0"] - tf, ba["x1"] + tf, 1, "K"),
         ("v", idp, 0, co["x0"], -1, "B"), ("x", co["x0"], co["v0"], idp, -1, "C"), ("v", co["v0"], co["x0"], iw, -1, "CH")]
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
        elif not hz and "CORE" in op and abs(c - (op["CORE"]["x0"] + op["CORE"]["t"] / 2)) < 0.01:
            s = "C"
        out.append((i, s or (hz, c), a, b, 0.0, op["DH"], "door", sw))
    return out


def line_geom(line, iw, idp, op=None):
    """壁の線を (横向きか, 位置, 範囲) に。範囲は外壁・コア・バルコニーの壁なら (始点, 終点)、間仕切りなら None。
    F/B/L/R の位置は内面、K（バルコニーの奥の壁）・C／CH（コアの壁）の位置は壁の中心。"""
    if line in ("F", "B"):
        return True, 0 if line == "F" else idp, (0, iw)
    if line in ("L", "R"):
        return False, 0 if line == "L" else iw, (0, idp)
    if line == "K":
        return True, op["BAL"]["d"] + op["TF"] / 2, (op["BAL"]["x0"], op["BAL"]["x1"])
    if line == "C":
        return False, op["CORE"]["x0"] + op["CORE"]["t"] / 2, (op["CORE"]["v0"], idp)
    if line == "CH":
        return True, op["CORE"]["v0"] + op["CORE"]["t"] / 2, (op["CORE"]["x0"], iw)
    return line[0], line[1], None


def hinge(line, c, sw, op, rng):
    """扉の吊り元の面の位置（ft）。"""
    if rng is None:
        return c + sw * op["PT"] / FT / 2
    if line == "C":
        return c + sw * op["CORE"]["t"] / 2
    return c


def check_open(op, iw, idp, h_ft, boxes, cat, ex, wall_y, found, notes):
    ht = op["PT"] / FT / 2
    pts = parts(op, iw, idp)
    ops = openings(op, iw, idp)
    # 6. 開口の範囲と、扉が間仕切りの上にあるか
    for i, line, a, b, lo, hi, kind, sw in ops:
        hz, c, length = line_geom(line, iw, idp, op)
        if not (a < b and lo < hi <= h_ft + TOL):
            found.append(f"開口の寸法が不正: {i}")
        if length is not None:
            if a < length[0] - TOL or b > length[1] + TOL:
                found.append(f"開口が壁の範囲外: {i}")
            co, ba, tf = op["CORE"], op["BAL"], op["TF"]
            if line == "F" and a < ba["x1"] + tf - TOL and ba["x0"] - tf + TOL < b:
                found.append(f"正面の開口がバルコニーのくぼみにかかる: {i}")
            if (line == "B" and b > co["x0"] + TOL) or (line == "R" and b > co["v0"] + TOL):
                found.append(f"外壁の開口が共用コアにかかる: {i}")
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
            if line_geom(p[1], iw, idp, op)[:2] == line_geom(q[1], iw, idp, op)[:2] and p[2] < q[3] - TOL and q[2] < p[3] - TOL:
                found.append(f"開口どうしが重なる: {p[0]} と {q[0]}")
    # 9. 床置きの家具と、間仕切り・扉の開き
    rects = []
    for hz, c, lo, hi in pts:
        rects.append((f"間仕切り {'v' if hz else 'x'}={c}", (lo - ht, hi + ht, c - ht, c + ht) if hz else (c - ht, c + ht, lo - ht, hi + ht)))
    for i, line, a, b, lo, hi, kind, sw in ops:
        if kind != "door":
            continue
        hz, c, length = line_geom(line, iw, idp, op)
        hp = hinge(line, c, sw, op, length)
        s0, s1 = sorted((hp, hp + sw * (b - a)))
        rects.append((f"扉 {i} の開き", (a, b, s0, s1) if hz else (s0, s1, a, b)))
    co, ba, tf = op["CORE"], op["BAL"], op["TF"]
    rects += [("共用コア", (co["x0"], iw, co["v0"], idp)), ("バルコニーの左の壁", (ba["x0"] - tf, ba["x0"], -tf, ba["d"] + tf)),
              ("バルコニーの右の壁", (ba["x1"], ba["x1"] + tf, -tf, ba["d"] + tf)), ("バルコニーの奥の壁", (ba["x0"] - tf, ba["x1"] + tf, ba["d"], ba["d"] + tf))]
    for k, x, v, mount, B, *_ in boxes:
        if mount == "floor" and ex.get(k, (None, None))[1] != "plant" and overlap((ba["x0"], ba["x1"], -tf, ba["d"]), B):
            found.append(f"バルコニーに植物以外の家具: {k} ({x}, {v})")
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
            if line_geom(oline, iw, idp, op)[:2] != line_geom(line, iw, idp, op)[:2] or not (a < along[1] - TOL and along[0] < b - TOL):
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


# 建物モデル（BLD）の照合値。出典は 01_法規/建築条件_4カタ_階段1本_v1_261016.md（同ファイルで官報と照合済み。
# このスクリプトの作成時に官報の原文は見直していない）
LAW = {
    "front_min": 1.5,   # m  DBR 規則41(1)（道路中心から 4.5 m との大きい方）
    "side_min": 1.00,   # m  DBR 表1（7階まで）
    "rear_min": 1.25,   # m  同上
    "stair_w": 1.15,    # m  DBR 第57条(ঘ)・表10
    "riser_max": 0.175, "tread_min": 0.225, "rt_min": 0.400, "flight_max": 20, "headroom": 2.15,
    "ev_height": 18.0,  # m  DBR 規則59(1): 最上階の屋根がこれを超えると EV が要る
    "tank_max": 5.0,    # m  DBR 規則49(ঘ): 高架水槽は屋根の仕上げ面から 5 m 以内
}


def col_points(b):
    """柱の位置（建物の座標 ft）。コアの位置は除き、移した柱は移した先。"""
    cl, out = b["COL"], []
    for x0 in cl["xs"]:
        for v0 in cl["vs"]:
            if [x0, v0] in cl["skip"]:
                continue
            mv = next((m for m in cl.get("move", []) if m[0] == x0 and m[1] == v0), None)
            out.append((mv[2], mv[3]) if mv else (x0, v0))
    return out


def read_bld(js):
    m = re.search(r"const BLD=(\{.*?\}\});", js, re.S)
    return json.loads(m.group(1)) if m else None


def cross_check():
    """15. 住戸モデル（CM-01）と建物モデル（CM-03）の一致: 窓・バルコニー・コア・玄関扉、住戸の家具と柱。"""
    bp, up = MODELS / "building_g6.html", MODELS / "unit_brick.html"
    if not (bp.exists() and up.exists()):
        return [], ["未照合（ファイルが無い）"]
    last = lambda p: re.findall(r"<script>(.*?)</script>", p.read_text(encoding="utf-8"), re.S)[-1]
    b, ujs = read_bld(last(bp)), last(up)
    op, dims = parse_open(ujs), parse_dims(ujs)
    if not (b and op and dims):
        return ["データが読めない"], []
    found, n = [], 0
    off, iw, idp = op["TF"], dims[4], dims[5]
    eq = lambda p, q: len(p) == len(q) and all(abs(x - y) <= 0.02 for x, y in zip(p, q))
    if abs(b["T"] - off) > 0.01:
        found.append(f"外壁の厚さが違う: CM-03 {b['T']} ft、住戸 {off:.3f} ft")
    for sd in "FLRB":
        uw = sorted([a + off, c + off, lo, hi] for i, s2, a, c, lo, hi in op["WINS"] if s2 == sd)
        bw = sorted(b["WIN"][sd])
        n += len(bw)
        if len(uw) != len(bw) or not all(eq(p, q) for p, q in zip(uw, bw)):
            found.append(f"{sd} 面の窓が一致しない: 住戸 {[[round(v, 2) for v in w] for w in uw]} ／ CM-03 {bw}")
    k = [[a + off, c + off, lo, hi] for i, s2, a, c, lo, hi in op["WINS"] if s2 == "K"]
    if len(k) != 1 or not eq(k[0], b["WIN"]["K"]):
        found.append("バルコニーの掃出し窓が一致しない")
    ba, bb = op["BAL"], b["BAL"]
    if not eq([ba["x0"] + off, ba["x1"] + off, ba["d"] + off], [bb["x0"], bb["x1"], bb["d"]]):
        found.append("バルコニーのくぼみが一致しない")
    co = op["CORE"]
    if not eq([co["x0"] + off, co["x0"] + off, co["v0"] + off, co["v0"] + off, co["t"]],
              [b["EV"]["x0"], b["LOBBY"]["x0"], b["STAIR"]["v0"], b["LOBBY"]["v0"], b["STAIR"]["wall"]]):
        found.append("共用コアの位置・壁厚が一致しない")
    d1 = [[a + off, c + off] for i, s, a, c, lo, hi, kind, sw in openings(op, iw, idp) if s == "C"]
    if len(d1) != 1 or not eq(d1[0], b["LOBBY"]["door"]):
        found.append(f"玄関扉の位置が一致しない: 住戸 {d1} ／ CM-03 {b['LOBBY']['door']}")
    cat, init, cl = parse_cat(ujs), parse_init(ujs) or [], b["COL"]
    cols = [(x - off, v - off) for x, v in col_points(b)]
    for kf, x, v, r in init:
        if kf not in cat or cat[kf][2] != "floor":
            continue
        w, d, _ = cat[kf]
        bw_, bd_ = (d, w) if r % 180 else (w, d)
        B = (x - bw_ / 2, x + bw_ / 2, v - bd_ / 2, v + bd_ / 2)
        for cx, cv in cols:
            if overlap((cx - cl["b"] / 2, cx + cl["b"] / 2, cv - cl["d"] / 2, cv + cl["d"] / 2), B):
                found.append(f"住戸の家具が柱と重なる: {kf} ({x}, {v}) と柱 ({cx:.2f}, {cv:.2f})")
    inside = [c for c in cols if 0 < c[0] < iw and 0 < c[1] < idp]
    return found, [f"窓 {n} か所・掃出し窓・バルコニー・コア・玄関扉・柱 {len(cols)} 本を照合（住戸の中に立つ柱 {len(inside)} 本）"]


def check_building(js, found, notes):
    m = re.search(r"const BLD=(\{.*?\}\});", js, re.S)
    if not m:
        found.append("建物のデータ（BLD）が読めない")
        return
    b = json.loads(m.group(1))
    st, ev, lb, si = b["STAIR"], b["EV"], b["LOBBY"], b["SITE"]
    fl = lambda i: b["PL"] if i == 0 else b["PL"] + b["GF"] + (i - 1) * b["TYP"]
    roof = fl(b["N"] + 1)
    # A. 規模（ユーザー指定: 建物 36×52 ft、敷地 45×65 ft、GF 12 ft・1〜6F 10 ft、G+6、前面道路 40 ft）
    want = {"W": 36, "D": 52, "GF": 12, "TYP": 10, "N": 6}
    for k, v in want.items():
        if b[k] != v:
            found.append(f"規模が指定と違う: {k}={b[k]}（指定 {v}）")
    if (si["W"], si["D"], si["ROAD"]) != (45, 65, 40):
        found.append(f"敷地・道路が指定と違う: {si['W']}×{si['D']}、道路 {si['ROAD']}")
    # B. 敷地に収まり、後退が足りるか
    if abs(si["S"] * 2 + b["W"] - si["W"]) > TOL or abs(si["F"] + b["D"] + si["R"] - si["D"]) > TOL:
        found.append("建物と後退の合計が敷地と合わない")
    front_req = max(LAW["front_min"], 4.5 - si["ROAD"] / 2 * FT)
    for name, val, req in (("前面", si["F"] * FT, front_req), ("側面", si["S"] * FT, LAW["side_min"]), ("背面", si["R"] * FT, LAW["rear_min"])):
        if val < req - 1e-6:
            found.append(f"後退の不足: {name} {val:.2f} m < {req:.2f} m")
    # C. 階段
    xi0, xi1 = st["x0"] + st["wall"], st["x1"] - b["T"]
    vi0, vi1 = st["v0"] + st["wall"], st["v1"] - b["T"]
    cw, cl = (xi1 - xi0) * FT, (vi1 - vi0) * FT
    if 2 * st["w"] + st["gap"] > cw + 1e-6:
        found.append(f"階段室の内法幅 {cw:.3f} m < 2×{st['w']}+{st['gap']}")
    if st["w"] < LAW["stair_w"]:
        found.append(f"階段の幅 {st['w']} m < {LAW['stair_w']} m")
    if st["tread"] < LAW["tread_min"]:
        found.append(f"踏面 {st['tread']} m < {LAW['tread_min']} m")
    rows = []
    for i in range(b["N"] + 1):
        h = (fl(i + 1) - fl(i)) * FT
        n = math.ceil(h / st["rmax"] - 1e-9)
        n += n % 2
        r = h / n
        run = (n / 2 - 1) * st["tread"]
        rows.append(f"{'GF' if i == 0 else str(i) + 'F'} {n}段×{r * 1000:.1f}")
        if r > LAW["riser_max"] + 1e-9 or r + st["tread"] < LAW["rt_min"] - 1e-9 or n / 2 > LAW["flight_max"]:
            found.append(f"階段の寸法が規定外: {rows[-1]} mm")
        if st["land"] + run + st["land"] > cl + 1e-6:
            found.append(f"階段室の内法長さ {cl:.3f} m に踊り場・階段が収まらない（{rows[-1]}）")
        if h - r - 0.6 * FT < LAW["headroom"]:
            found.append(f"階段の頭上 {h - r - 0.6 * FT:.2f} m < {LAW['headroom']} m")
        land_end = vi1 - (st["land"] + run) / FT
        if not (vi0 <= st["door"][0] and st["door"][1] <= land_end):
            found.append(f"階段室の扉が階の踊り場（v {vi0:.2f}〜{land_end:.2f}）に入らない")
    notes.append("階段: " + "、".join(rows[:2]) + f" mm、室内法 {cw:.2f} × {cl:.2f} m")
    # D. コアの配置（重なり・建物内）
    rects = {"階段室": (st["x0"], st["x1"], st["v0"], st["v1"]), "昇降路": (ev["x0"], ev["x1"], ev["v0"], ev["v1"]),
             "ホール": (lb["x0"], lb["x1"], lb["v0"], lb["v1"])}
    for k, r in rects.items():
        if r[0] < -TOL or r[1] > b["W"] + TOL or r[2] < -TOL or r[3] > b["D"] + TOL:
            found.append(f"{k}が建物の外に出る")
    ks = list(rects)
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            if overlap(rects[ks[i]], rects[ks[j]]):
                found.append(f"{ks[i]}と{ks[j]}が重なる")
    if not (lb["x0"] <= ev["door"][0] and ev["door"][1] <= lb["x1"] and abs(ev["v0"] - lb["v1"]) < TOL):
        found.append("EV の扉がホールに面していない")
    if abs(st["x0"] - lb["x1"]) > TOL or not (lb["v0"] <= st["door"][0] and st["door"][1] <= lb["v1"]):
        found.append("階段室の扉がホールに面していない")
    # E. EV の要否と高架水槽
    top = (roof - fl(0)) * FT
    notes.append(f"屋上スラブは1階床から {top:.2f} m（EV が要る高さ {LAW['ev_height']} m）")
    tank_top = (b["ROOF"]["room"] + b["ROOF"]["tank"][4]) * FT
    if tank_top > LAW["tank_max"] + 1e-6:
        found.append(f"高架水槽の上端が屋上から {tank_top:.2f} m（上限 {LAW['tank_max']} m）")
    # F. 柱がバルコニー（くぼみ）の中に立たないか
    ba, cl = b["BAL"], b["COL"]
    for x, v in col_points(b):
        if overlap((x - cl["b"] / 2, x + cl["b"] / 2, v - cl["d"] / 2, v + cl["d"] / 2), (ba["x0"], ba["x1"], 0, ba["d"])):
            found.append(f"柱がバルコニーの中に立つ: ({x}, {v})")
    notes.append(f"保留 1: 階段1本（消防規則 2014 第13別表(৯)は7層以上で階段2本。施主の判断で保留）")
    notes.append("未照合: 容積率・建蔽率の上限、消防水槽、上階の柱・梁、住戸の間取り")


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

    # 14. GLB の書き出し（Clip Studio 用）: three.js と書き出し機能の版がそろい、保存ボタンがあるか
    core = re.search(r"three\.js/r(\d+)/three\.min\.js", html)
    gexp = re.search(r"three@0\.(\d+)\.0/examples/js/exporters/GLTFExporter\.js", html)
    if not (core and gexp and core.group(1) == gexp.group(1)):
        found.append("GLTFExporter の読み込みが無いか、three.js と版が合わない")
    if 'id="glbB"' not in html or "saveGLB(" not in js:
        found.append("GLB の保存ボタン（glbB）か saveGLB が無い")

    if "const BLD=" in js:
        check_building(js, found, notes)
        return found, notes, revs, None

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
    cf, cn = cross_check()
    print(f"■ 住戸 CM-01 と建物 CM-03 の一致  検出 {len(cf)}")
    for t in cn:
        print("   ・" + t)
    for t in cf:
        print("   ✗ " + t)
    total += len(cf)
    # 13. 修正指示用の DXF（dxf/ の最新）が、現行のモデルから書き出したものと同じか
    dxfs = sorted((ROOT / "dxf").glob("unit_plan_*.dxf"))
    if dxfs:
        import export_dxf as xd
        E, info = xd.build()
        cur = xd.to_dxf(E)
        last = dxfs[-1].read_text(encoding="cp932")
        cnt, odd = xd.stats(last)
        bad = []
        # cp932 は「〜」などを別の文字に読み戻すので、バイト列で比べる
        if dxfs[-1].read_bytes().replace(b"\r\n", b"\n") != cur.encode("cp932"):
            bad.append(f"{dxfs[-1].name} が現行のモデルと一致しない（python tools/export_dxf.py で書き出し直す）")
        if odd:
            bad.append(f"壁の輪郭が閉じていない（端点 {len(odd)} 個）")
        if cnt.get(("ARC", "A-DOOR"), 0) != info["doors"]:
            bad.append(f"扉の円弧 {cnt.get(('ARC', 'A-DOOR'), 0)} 個 ≠ 扉 {info['doors']} か所")
        print(f"■ dxf/{dxfs[-1].name}  検出 {len(bad)}（現行モデルから書き出し直した内容と照合）")
        for b in bad:
            print("   ✗ " + b)
        total += len(bad)
    print(f"合計 検出 {total}（{len(files)} ファイル）")
    print("未照合: 画面表示・操作、寸法の前提と原典の照合、扉・窓の寸法と法規（BNBC など）の照合")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
