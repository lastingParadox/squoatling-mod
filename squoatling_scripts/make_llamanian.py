"""
Generate the programmatic parts of the Llamanian race from the Squoatling sources.

    python squoatling_scripts/make_llamanian.py [--dry-run] [--no-patches] [--no-cinematics]

Re-runnable: it OVERWRITES generated files (humanoid/llamanian/*, species/llamanian*.*,
interface/title/llamanian*.png, cinematics copies). Do NOT run it after you've hand-edited
humanoid/llamanian/* unless you pass --skip-sprites (or you'll lose the edits).
Squoatling assets are never modified; existing .patch files only get a llamanian op appended
(skipped if one is already there). Needs Pillow.

The color mapping lives in squoatling_scripts/llamanian/llamanian_palette.json.
"""

import argparse
import colorsys
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MOD = HERE.parent
SQ = MOD / "humanoid" / "squoatling"
LL = MOD / "humanoid" / "llamanian"
PALETTE_JSON = HERE / "llamanian" / "llamanian_palette.json"
REPORT = HERE / "llamanian" / "generated_report.txt"
PREVIEW = HERE / "llamanian" / "palette_preview.png"
# Hand-drawn reference portraits already living in humanoid/llamanian/ - never overwritten.
PORTRAIT_REF = LL / "Llamanian_sprite.png"

log = []


def say(msg):
    log.append(msg)
    print(msg)


def rgb(h):
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hexs(c):
    return "%02X%02X%02X" % tuple(c[:3])


# --------------------------------------------------------------------------- mapping


def load_mapping():
    data = json.loads(PALETTE_JSON.read_text(encoding="utf-8"))
    body = {k.upper(): v["to"].upper() for k, v in data["body"].items()}
    eye = {k.upper(): v["to"].upper() for k, v in data["eye"].items()}
    snap = {k.upper(): v.upper() for k, v in data["snap"].items() if not k.startswith("_")}
    targets = list(body.values()) + list(eye.values())
    dupes = [t for t, n in Counter(targets).items() if n > 1]
    assert not dupes, f"llamanian_palette.json: targets must be unique, duplicated: {dupes}"
    clash = set(targets) & (set(body) | set(eye))
    # a target equal to another role's *source* key would make chained recoloring ambiguous
    assert not clash, f"targets collide with Squoatling source keys: {sorted(clash)}"
    return data, body, eye, snap


def recolor_map(body, eye, snap):
    m = {}
    for k, v in {**body, **eye}.items():
        m[rgb(k)] = rgb(v)
    for k, v in snap.items():
        m[rgb(k)] = rgb(body.get(v, eye.get(v, v)))  # snap to the key, then to its Llamanian color
    return m


# --------------------------------------------------------------------------- png io


def save_indexed(img, path):
    """Write an RGBA image as an 8-bit colormap PNG (like the Squoatling sources)."""
    img = img.convert("RGBA")
    colors = {}
    idx = []
    for px in img.getdata():
        if px[3] == 0:
            px = (0, 0, 0, 0)
        if px not in colors:
            colors[px] = len(colors)
        idx.append(colors[px])
    assert len(colors) <= 256, f"{path}: {len(colors)} colors"
    out = Image.new("P", img.size)
    out.putdata(idx)
    pal, alpha = [], []
    for px in sorted(colors, key=colors.get):
        pal += list(px[:3])
        alpha.append(px[3])
    out.putpalette(pal + [0] * (768 - len(pal)))
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, transparency=bytes(alpha), optimize=False)


def recolor_image(img, cmap):
    img = img.convert("RGBA")
    px = [(*cmap.get(p[:3], p[:3]), p[3]) if p[3] else p for p in img.getdata()]
    out = Image.new("RGBA", img.size)
    out.putdata(px)
    return out


# --------------------------------------------------------------------------- sprites


def build_sprites(cmap, body, eye, dry):
    known = set(rgb(k) for k in {**body, **eye}) | set(cmap)
    report = {}
    horn_src = {rgb(k) for k in ("DED19F", "968F72", "C1B68D")}
    strays = Counter()
    n = 0
    for src in sorted(SQ.rglob("*")):
        rel = src.relative_to(SQ)
        if any("template" in part.lower() for part in rel.parts[:-1]):
            continue  # "female template"/"male template" folders: artist reference copies, not in-game
        if src.is_dir():
            continue
        dst = LL / rel
        if src.suffix != ".png" or src.name == "dead.png":
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
            continue
        im = Image.open(src).convert("RGBA")
        op = [p[:3] for p in im.getdata() if p[3]]
        horn = sum(1 for p in op if p in horn_src)
        if horn:
            report[str(rel)] = horn
        for p in op:
            if p not in known and p != (0, 0, 0):
                strays[hexs(p)] += 1
        if not dry:
            save_indexed(recolor_image(im, cmap), dst)
        n += 1
    say(f"sprites: recolored {n} png sheets -> humanoid/llamanian/ (dead.png + .frames copied as-is)")
    return report, strays


# --------------------------------------------------------------------------- palettes


def hsv(c):
    return colorsys.rgb_to_hsv(*(x / 255 for x in c))


def unhsv(h, s, v):
    return tuple(round(x * 255) for x in colorsys.hsv_to_rgb(h % 1.0, min(1, max(0, s)), min(1, max(0, v))))


def variant_color(sq_base, sq_var, ll_base):
    """Squoatling variant -> Llamanian: hue from the variant, S/V scaled by (llamanian base / squoatling base)."""
    h_b, s_b, v_b = hsv(sq_base)
    h_v, s_v, v_v = hsv(sq_var)
    _, s_l, v_l = hsv(ll_base)
    if (sq_var == sq_base):
        return ll_base
    rs = max(0.5, min(1.6, s_l / max(s_b, 0.08)))
    rv = max(0.5, min(1.4, v_l / max(v_b, 0.08)))
    s = s_v * rs
    v = v_v * rv
    h = h_v if s_v > 0.06 else hsv(ll_base)[0]
    return unhsv(h, s, v)


def build_palettes(sq_species, body, eye):
    sq_body, sq_eye = sq_species["bodyColor"], sq_species["undyColor"]
    new_body, new_eye = [], []
    for row in sq_body:
        out = {}
        for k, ll in body.items():
            sq_base = rgb(k)
            sq_var = rgb(row.get(k, k))
            out[ll] = hexs(variant_color(sq_base, sq_var, rgb(ll)))
        new_body.append(out)
    for i, row in enumerate(sq_eye):
        new_eye.append({ll: (ll if i == 0 else row[k]) for k, ll in eye.items()})
    new_body[0] = {ll: ll for ll in body.values()}
    # sanity: variants should keep the roles distinguishable
    for i, row in enumerate(new_body):
        c = Counter(row.values())
        d = [k for k, n in c.items() if n > 1]
        if d:
            say(f"  note: bodyColor[{i}] merges roles into the same color ({d}) - tweak by hand if it matters")
    return new_body, new_eye


# --------------------------------------------------------------------------- species + ancillary


def build_species(dry, body, eye):
    src = MOD / "species" / "squoatling.species"
    sp = json.loads(src.read_text(encoding="utf-8-sig"))
    new_body, new_eye = build_palettes(sp, body, eye)
    sp["kind"] = "llamanian"
    sp["charCreationTooltip"] = {
        "title": "Llamanian",
        "subTitle": "TODO",
        "description": "TODO: Llamanian description.",
    }
    sp["nameGen"] = ["/species/llamanianmalenamegen.config:names", "/species/llamanianfemalenamegen.config:names"]
    sp["skull"] = "/humanoid/llamanian/dead.png"
    sp["charGenTextLabels"] = ["Llamanian" if t == "Squoatling" else t for t in sp["charGenTextLabels"]]
    for g in sp["genders"]:
        n = g["name"]
        g["characterImage"] = f"/interface/title/llamanian{n}.png"
        # gender icons are species-neutral: keep pointing at the squoatling ones
    sp["bodyColor"], sp["undyColor"] = new_body, new_eye
    if not dry:
        (MOD / "species" / "llamanian.species").write_text(json.dumps(sp, indent=2) + "\n", encoding="utf-8")
        for g in ("male", "female", ""):
            s = MOD / "species" / f"squoatling{g}namegen.config"
            shutil.copyfile(s, MOD / "species" / f"llamanian{g}namegen.config")
    say("species: wrote species/llamanian.species (+ 3 placeholder namegen copies - still SQUOATLING names)")
    return sp


def build_title_images(cmap, dry):
    for g in ("male", "female"):
        im = Image.open(MOD / "interface" / "title" / f"squoatling{g}.png")
        if not dry:
            save_indexed(recolor_image(im, cmap), MOD / "interface" / "title" / f"llamanian{g}.png")
    say("interface/title: llamanianmale.png / llamanianfemale.png = recolored Squoatling previews (placeholder, redraw)")


def build_cinematics(dry):
    n = 0
    for src in sorted((MOD / "cinematics").rglob("*")):
        if src.is_dir() or "squoatling" not in str(src.relative_to(MOD / "cinematics")).lower():
            continue
        dst = MOD / "cinematics" / str(src.relative_to(MOD / "cinematics")).replace("squoatling", "llamanian")
        n += 1
        if dry:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in (".cinematic", ".frames"):
            dst.write_text(src.read_text(encoding="utf-8").replace("squoatling", "llamanian"), encoding="utf-8")
        else:
            shutil.copyfile(src, dst)
    say(f"cinematics: copied {n} files squoatling->llamanian (art is still the Squoatling pod/ship; refs rewritten)")


PATCHES = [
    # (file, text of the op to append, marker that means 'already done')
    ("interface/windowconfig/charcreation.config.patch",
     '{ "op" : "add", "path" : "/speciesOrdering/-", "value" : "llamanian" }'),
    ("ai/ai.config.patch",
     '{\n\t\t"op" : "add",\n\t\t"path" : "/species/llamanian",\n\t\t"value" : {\n'
     '\t\t\t"aiFrames" : "squoatlingAI.png",\n\t\t\t"portraitFrames" : "portraits/squoatlingportrait.png",\n'
     '\t\t\t"staticFrames" : "staticsquoatling.png"\n\t\t}\n\t}'),
    ("universe_server.config.patch", None),  # built from the squoatling op below
    ("player.config.patch",
     '{ "op" : "add", "path" : "/defaultCodexes/llamanian", "value" : [ "protectorate1", "protectorate2" ] }'),
    ("quests/quests.config.patch",
     '{\n\t\t"op": "add",\n\t\t"path": "/initialquests/llamanian",\n\t\t"value": [\n\t\t\t"protectorate"\n\t\t]\n\t},\n'
     '\t{\n\t\t"op": "add",\n\t\t"path": "/pronounGenders/llamanian",\n\t\t"value": {\n'
     '\t\t\t"male": "neutral",\n\t\t\t"female": "neutral"\n\t\t}\n\t}'),
    ("treasure/shiplocker.treasurepools.patch",
     '{\n    "op": "add",\n    "path": "/llamanianStarterTreasure",\n    "value": [[0, {\n      "fill" : [\n'
     '        {"pool" : "starterTreasure"},\n        {"item" : [ "squoatlingsword", 1 ]}\n      ]\n    }]]\n  }'),
    ("objects/protectorate/objects/protectorateship/protectorateship.object.patch",
     '{\n    "op": "add",\n    "path": "/llamanianDescription",\n    "value": "Just as I hoped This ship is my way out of here."\n  }'),
]


def append_patch(path, op, dry):
    p = MOD / path
    with open(p, encoding="utf-8", newline="") as f:  # newline="": keep the file's CRLF/LF as is
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    if "llamanian" in text:
        say(f"patch: {path}: already has a llamanian op - skipped")
        return
    if op is None:  # universe_server: copy the squoatling op with the name swapped
        m = re.search(r"\{\s*\"op\".*\}", text, re.S)
        op = m.group(0).replace("squoatling", "llamanian") if m else None
        if not op:
            say(f"patch: {path}: could not parse - add the llamanian op by hand")
            return
        # ships: no llamanian structures exist, so keep pointing at the squoatling ships
        op = op.replace("/ships/llamanian/llamanian", "/ships/squoatling/squoatling")
    end = text.rstrip().rfind("]")
    new = text[:end].rstrip() + "," + nl + op.replace("\r\n", "\n").replace("\n", nl) + nl + "]" + nl
    if not dry:
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    say(f"patch: {path}: appended llamanian op")


# --------------------------------------------------------------------------- preview


def build_preview(sp, body, eye):
    ref = PORTRAIT_REF
    if not ref.exists():
        return
    base = Image.open(ref).convert("RGBA")
    rows = sp["bodyColor"]
    scale = 8
    w, h = base.size
    cols = 8
    nr = (len(rows) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (w + 2) * scale, nr * (h + 2) * scale), (70, 70, 80, 255))
    # the portrait is painted in Llamanian base colors, i.e. the bodyColor[0] keys
    for i, row in enumerate(rows):
        cm = {rgb(k): rgb(v) for k, v in row.items()}
        cm.update({rgb(k): rgb(v) for k, v in sp["undyColor"][0].items()})
        im = recolor_image(base, cm).resize((w * scale, h * scale), Image.NEAREST)
        x, y = (i % cols) * (w + 2) * scale, (i // cols) * (h + 2) * scale
        sheet.paste(im, (x, y), im)
    sheet.save(PREVIEW)
    say(f"preview: {PREVIEW.relative_to(MOD)} (all {len(rows)} fur palettes on the reference portrait, row-major)")


# --------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-patches", action="store_true")
    ap.add_argument("--no-cinematics", action="store_true")
    ap.add_argument("--skip-sprites", action="store_true", help="keep hand-edited humanoid/llamanian sheets")
    a = ap.parse_args()

    data, body, eye, snap = load_mapping()
    cmap = recolor_map(body, eye, snap)
    horn, strays = {}, Counter()
    if not a.skip_sprites:
        horn, strays = build_sprites(cmap, body, eye, a.dry_run)
    sp = build_species(a.dry_run, body, eye)
    build_title_images(cmap, a.dry_run)
    if not a.no_cinematics:
        build_cinematics(a.dry_run)
    if not a.no_patches:
        for path, op in PATCHES:
            append_patch(path, op, a.dry_run)
    if not a.dry_run:
        build_preview(sp, body, eye)
    if horn:
        say("\nHorn-colored pixels still present (erase by hand), per sheet:")
        for k, v in sorted(horn.items()):
            say(f"  {k}: {v}")
    if strays:
        say("\nOff-palette colors left untouched (not in the mapping): " + ", ".join(f"{k} x{v}" for k, v in strays.items()))
    if not a.dry_run:
        REPORT.write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
