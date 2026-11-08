"""
Clothing (items/armors) support for squoatling_editor.py:

- loading .chest / .legs / .head / .back items and their colorOptions (with the // NAME comments)
- writing colorOptions back IN PLACE (the rest of the file, comments and formatting are untouched)
- resolving sprite paths and .frames files the way Starbound does (case-sensitive!)
- sanity checks for the sprite sheets ("are the animations solid?")
"""

import json
import re
from pathlib import Path

# --------------------------------------------------------------------------- frames

FRAME = 43


def parse_frames(data):
    """Turn a Starbound .frames dict into {frame name: (x0, y0, x1, y1)} (y measured from the top)."""
    boxes = {}
    grid = data.get("frameGrid")
    if grid:
        w, h = grid["size"]
        bx, by = grid.get("begin", [0, 0])
        cols, rows = grid.get("dimensions", [0, 0])
        names = grid.get("names")
        if names:
            for r, row in enumerate(names):
                for c, name in enumerate(row or []):
                    if name:
                        boxes[name] = (bx + c * w, by + r * h, bx + (c + 1) * w, by + (r + 1) * h)
        else:  # unnamed grid -> "0", "1", ...
            for i in range(cols * rows):
                c, r = i % cols, i // cols
                boxes[str(i)] = (bx + c * w, by + r * h, bx + (c + 1) * w, by + (r + 1) * h)
    for name, rect in (data.get("frameList") or {}).items():
        boxes[name] = tuple(rect)
    aliases = data.get("aliases") or {}
    for _ in range(8):  # aliases may point at aliases
        for alias, target in aliases.items():
            if alias not in boxes and target in boxes:
                boxes[alias] = boxes[target]
    return boxes


_ARM_GRID = {
    "frameGrid": {"size": [43, 43], "dimensions": [9, 8], "names": [
        [None, "idle.1", "idle.2", "idle.3", "idle.4", "idle.5", None, None, "duck.1"],
        [None, None, "walk.1", "walk.2", "walk.3", "walk.4", "walk.5", None, "rotation"],
        [None, None, "run.1", "run.2", "run.3", "run.4", "run.5", None, None],
        [None, "jump.1", "jump.2", "jump.3", "jump.4", "fall.1", "fall.2", "fall.3", "fall.4"],
        [None] * 9,
        [None, "swimIdle.1", "swimIdle.2", None, "swim.1", "swim.2", "swim.3", "swim.4", "swim.5"],
        [None, None, None, "idleMelee", None, None, None, None, "duckMelee"],
    ]},
    "aliases": {"swim.6": "swimIdle.1", "swim.7": "swimIdle.2", "sit.1": "idle.1", "lay.1": "idle.1"},
}
_BODY_GRID_NAMES = [
    [None, "idle.1", "idle.2", "idle.3", "idle.4", "idle.5", "sit.1", None, "duck.1"],
    [None, "walk.1", "walk.2", "walk.3", "walk.4", "walk.5", "walk.6", "walk.7", "walk.8"],
    [None, "run.1", "run.2", "run.3", "run.4", "run.5", "run.6", "run.7", "run.8"],
    [None, "jump.1", "jump.2", "jump.3", "jump.4", "fall.1", "fall.2", "fall.3", "fall.4"],
    [None, "climb.1", "climb.2", "climb.3", "climb.4", "climb.5", "climb.6", "climb.7", "climb.8"],
]
_PANTS = {
    "frameGrid": {"size": [43, 43], "dimensions": [9, 6], "names": _BODY_GRID_NAMES + [
        [None, "swimIdle.1", None, None, "swim.1", "swim.2", "swim.3", "swim.4", None]]},
    "aliases": {"swimIdle.2": "swimIdle.1", "swim.5": "swimIdle.1", "swim.6": "swimIdle.2",
                "swim.7": "swimIdle.2", "lay.1": "idle.1"},
}
_CHEST = {
    "frameList": {"chest.1": [43, 0, 86, 43], "chest.2": [0, 43, 43, 86], "chest.3": [43, 43, 86, 86],
                  "run": [43, 86, 86, 129], "duck": [43, 129, 86, 172], "swim": [43, 215, 86, 258]},
    "aliases": {"idle.1": "chest.1", "idle.2": "chest.2", "idle.3": "chest.3", "idle.4": "chest.2",
                "idle.5": "chest.1", "duck.1": "duck"},
}
_HEAD = {"frameList": {"normal": [43, 0, 86, 43], "climb": [43, 172, 86, 215]}}
_BACK = {
    "frameGrid": {"size": [43, 43], "dimensions": [9, 7], "names": _BODY_GRID_NAMES + [
        [None, "swimIdle.1", None, None, "swim.1", "swim.2", "swim.3", "swim.4", None],
        [None] + [f"runbackwards.{i}" for i in range(1, 9)]]},
    "aliases": {"swimIdle.2": "swimIdle.1", "swim.5": "swimIdle.1", "swim.6": "swimIdle.1",
                "swim.7": "swimIdle.1", "lay.1": "idle.1"},
}
_ICONS = {"frameList": {"head": [0, 0, 16, 16], "chest": [16, 0, 32, 16], "pants": [32, 0, 48, 16],
                        "back": [48, 0, 64, 16]}}

# Files that exist in vanilla assets at /items/armors/<name>.frames (found by Starbound's
# upward .frames search for any sprite living under /items/armors/).
VANILLA_ARMOR_FRAMES = {
    "chest": _CHEST, "chestm": _CHEST, "chestf": _CHEST,
    "pants": _PANTS, "pantsm": _PANTS, "pantsf": _PANTS,
    "fsleeve": _ARM_GRID, "fsleevef": _ARM_GRID, "bsleeve": _ARM_GRID, "bsleevef": _ARM_GRID,
    "head": _HEAD, "headm": _HEAD, "headf": _HEAD, "back": _BACK, "icons": _ICONS,
}

# Frames each role actually uses in game (for the empty-frame check).
CHEST_USED = ["chest.1", "chest.2", "chest.3", "run", "duck", "swim"]
PANTS_USED = ([f"idle.{i}" for i in range(1, 6)] + ["sit.1", "duck.1"] +
              [f"walk.{i}" for i in range(1, 9)] + [f"run.{i}" for i in range(1, 9)] +
              [f"jump.{i}" for i in range(1, 5)] + [f"fall.{i}" for i in range(1, 5)] +
              [f"climb.{i}" for i in range(1, 9)] + ["swimIdle.1"] + [f"swim.{i}" for i in range(1, 5)])
SLEEVE_USED = ([f"idle.{i}" for i in range(1, 6)] + ["duck.1", "rotation"] +
               [f"walk.{i}" for i in range(1, 6)] + [f"run.{i}" for i in range(1, 6)] +
               [f"jump.{i}" for i in range(1, 5)] + [f"fall.{i}" for i in range(1, 5)] +
               ["swimIdle.1", "swimIdle.2"] + [f"swim.{i}" for i in range(1, 6)])
HEAD_USED = ["normal", "climb"]
# Animation sequences used for the "does one frame look broken?" check.
SEQUENCES = {
    "pants": [("walk", 8), ("run", 8), ("climb", 8), ("jump", 4), ("fall", 4)],
    "sleeve": [("walk", 5), ("run", 5), ("jump", 4), ("fall", 4)],
}

# --------------------------------------------------------------------------- json helpers


def strip_json_comments(text):
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load_json_file(path):
    raw = Path(path).read_bytes().decode("utf-8-sig")
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError:
        return json.loads(strip_json_comments(raw)), raw


def _skip_ws_comments(text, i):
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            break
    return i


def _match_bracket(text, i):
    """text[i] is '[' or '{'; return index just past its matching closer (string/comment aware)."""
    depth, n, in_str = 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced brackets")


def find_key_value_span(text, key):
    """Find the value span of a top-level key. Returns (value_start, value_end) or None."""
    i = _skip_ws_comments(text, 0)
    if i >= len(text) or text[i] != "{":
        return None
    i += 1
    n = len(text)
    while i < n:
        i = _skip_ws_comments(text, i)
        if i >= n or text[i] == "}":
            return None
        if text[i] == ",":
            i += 1
            continue
        if text[i] != '"':
            return None
        j = i + 1
        while text[j] != '"':
            j += 2 if text[j] == "\\" else 1
        name = json.loads(text[i:j + 1])
        i = _skip_ws_comments(text, j + 1)
        if text[i] != ":":
            return None
        i = _skip_ws_comments(text, i + 1)
        start = i
        if text[i] in "[{":
            end = _match_bracket(text, i)
        elif text[i] == '"':
            k = i + 1
            while text[k] != '"':
                k += 2 if text[k] == "\\" else 1
            end = k + 1
        else:
            end = i
            while end < n and text[end] not in ",}\r\n":
                end += 1
        if name == key:
            return start, end
        i = end
    return None


def parse_color_options(text):
    """-> list of {"name": str, "colors": {key: value}} from the colorOptions array (with // names)."""
    span = find_key_value_span(text, "colorOptions")
    if not span:
        return []
    arr = text[span[0]:span[1]]
    values = json.loads(strip_json_comments(arr))
    names, pending, depth, i, n, in_str = [], "", 0, 0, len(arr), False
    while i < n:
        c = arr[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif arr.startswith("//", i):
            j = arr.find("\n", i)
            j = n if j < 0 else j
            if depth == 1:
                pending = arr[i + 2:j].strip()
            i = j
            continue
        elif arr.startswith("/*", i):
            j = arr.find("*/", i + 2)
            j = n if j < 0 else j
            if depth == 1:
                pending = arr[i + 2:j].strip()
            i = j + 2
            continue
        elif c in "[{":
            if c == "{" and depth == 1:
                names.append(pending)
                pending = ""
            depth += 1
        elif c in "]}":
            depth -= 1
        i += 1
    opts = []
    for idx, v in enumerate(values):
        if isinstance(v, dict):
            opts.append({"name": names[idx] if idx < len(names) else "", "colors": dict(v)})
        else:  # string directive option; keep it as-is but not editable as colors
            opts.append({"name": names[idx] if idx < len(names) else "", "colors": {}, "raw": v})
    return opts


def format_color_options(options, base_indent, newline):
    ind = base_indent + "  "
    lines = ["["]
    for i, opt in enumerate(options):
        if opt.get("name"):
            lines.append(f"{ind}// {opt['name']}")
        if "raw" in opt:
            body = json.dumps(opt["raw"])
        else:
            pairs = ", ".join(f'"{k}" : "{v}"' for k, v in opt["colors"].items())
            body = "{ " + pairs + " }" if pairs else "{ }"
        lines.append(ind + body + ("," if i < len(options) - 1 else ""))
    lines.append(base_indent + "]")
    return newline.join(lines)


def replace_color_options(text, options):
    newline = "\r\n" if "\r\n" in text else "\n"
    span = find_key_value_span(text, "colorOptions")
    if span:
        line_start = text.rfind("\n", 0, span[0]) + 1
        m = re.match(r"[ \t]*", text[line_start:])
        base = m.group(0)
        return text[:span[0]] + format_color_options(options, base, newline) + text[span[1]:]
    # no colorOptions yet: add one before the final closing brace
    end = text.rstrip().rfind("}")
    before = text[:end].rstrip()
    return (before + "," + newline + '  "colorOptions" : ' +
            format_color_options(options, "  ", newline) + newline + text[end:])


# --------------------------------------------------------------------------- paths


def exact_or_case_match(path):
    """-> (path_on_disk, exact_case) or (None, False). Starbound asset paths are case-sensitive."""
    path = Path(path)
    parent = path.parent
    if not parent.is_dir():
        return None, False
    try:
        names = [p.name for p in parent.iterdir()]
    except OSError:
        return None, False
    if path.name in names:
        return parent / path.name, True
    low = path.name.lower()
    for nm in names:
        if nm.lower() == low:
            return parent / nm, False
    return None, False


def asset_path_parts(ref):
    """'chestm.png:chest.1?replace...' -> 'chestm.png'"""
    return re.split(r"[:?]", ref, maxsplit=1)[0]


def resolve_ref(mod_dir, item_dir, ref):
    rel = asset_path_parts(ref)
    if rel.startswith("/"):
        return Path(mod_dir) / rel.lstrip("/")
    return Path(item_dir) / rel


def find_frames(mod_dir, image_path):
    """Mimic Starbound's .frames lookup: <stem>.frames or default.frames in the image's folder, then each
    parent folder up to the asset root; vanilla /items/armors/*.frames as the last resort.
    Returns (boxes, description) or (None, reason)."""
    mod_dir = Path(mod_dir)
    image_path = Path(image_path)
    stem = image_path.stem
    d = image_path.parent
    while True:
        for cand in (f"{stem}.frames", "default.frames"):
            p, exact = exact_or_case_match(d / cand)
            if p is not None and exact:
                try:
                    data, _ = load_json_file(p)
                    return parse_frames(data), str(p.relative_to(mod_dir))
                except Exception as ex:
                    return None, f"{p.name} is not valid JSON ({ex})"
        if d == mod_dir or mod_dir not in d.parents:
            break
        d = d.parent
    try:
        rel = image_path.relative_to(mod_dir).as_posix()
    except ValueError:
        rel = ""
    if rel.startswith("items/armors/") and stem in VANILLA_ARMOR_FRAMES:
        return parse_frames(VANILLA_ARMOR_FRAMES[stem]), f"vanilla /items/armors/{stem}.frames"
    return None, f"no '{stem}.frames' or default.frames found (vanilla only has " \
                 f"{', '.join(sorted(k for k in VANILLA_ARMOR_FRAMES if k != 'icons'))})"


# --------------------------------------------------------------------------- item model

KIND_BY_EXT = {".chest": "chest", ".legs": "legs", ".head": "head", ".back": "back"}


class ClothingItem:
    def __init__(self, mod_dir, path):
        self.mod_dir = Path(mod_dir)
        self.path = Path(path)
        self.kind = KIND_BY_EXT[self.path.suffix.lower()]
        self.reload()

    def reload(self):
        self.data, self.raw = load_json_file(self.path)
        self.mtime = self.path.stat().st_mtime_ns
        self.options = parse_color_options(self.raw)
        self.saved_options = json.loads(json.dumps(self.options))

    @property
    def item_name(self):
        return self.data.get("itemName", self.path.stem)

    @property
    def label(self):
        return f"{self.data.get('shortdescription', self.item_name)}  [{self.kind}]  {self.path.parent.name}"

    def is_dirty(self):
        return self.options != self.saved_options

    def color_keys(self):
        keys = []
        for opt in self.options:
            for k in opt["colors"]:
                if k.lower() not in [x.lower() for x in keys]:
                    keys.append(k)
        return keys

    def refs(self, gender):
        """-> {role: ref string} for the given gender ('male'/'female')."""
        frames = self.data.get(f"{gender}Frames")
        if frames is None:
            return {}
        if self.kind == "chest":
            if isinstance(frames, dict):
                return {k: v for k, v in frames.items() if k in ("body", "frontSleeve", "backSleeve") and v}
            return {"body": frames}
        if isinstance(frames, str):
            return {self.kind: frames}
        return {}

    def image_path(self, gender, role):
        """Path Starbound would load (exact case) and the on-disk match (may differ in case)."""
        ref = self.refs(gender).get(role)
        if not ref:
            return None, None, False
        wanted = resolve_ref(self.mod_dir, self.path.parent, ref)
        disk, exact = exact_or_case_match(wanted)
        return wanted, disk, exact

    def save(self):
        raw = self.path.read_bytes().decode("utf-8-sig")
        new = replace_color_options(raw, self.options)
        # sanity: must still parse and contain exactly our options
        check = json.loads(strip_json_comments(new))
        if len(check.get("colorOptions", [])) != len(self.options):
            raise ValueError("colorOptions round-trip check failed")
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        self.raw = new
        self.data = check
        self.mtime = self.path.stat().st_mtime_ns
        self.saved_options = json.loads(json.dumps(self.options))


def find_items(mod_dir):
    root = Path(mod_dir) / "items" / "armors"
    items = []
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() in KIND_BY_EXT and p.is_file():
                try:
                    items.append(ClothingItem(mod_dir, p))
                except Exception as ex:  # broken JSON etc.
                    print(f"skipping {p}: {ex}")
    return items


# --------------------------------------------------------------------------- checks


def _opaque_count(img):
    return sum(1 for a in img.getchannel("A").getdata() if a)


def check_item(item, get_image, arm_images=None):
    """-> list of (level, message); level in 'error' | 'warn' | 'info' | 'ok'.
    get_image(path) returns an RGBA PIL image or None.
    arm_images: {"frontSleeve": RGBA arm sheet, "backSleeve": ...} - sleeves are judged against the arm
    they cover (an empty sleeve frame is only a problem where the arm itself is visible)."""
    arm_images = arm_images or {}
    arm_boxes = parse_frames(_ARM_GRID)
    out = []
    keys = {k.lower()[:6] for k in item.color_keys()}
    roles_used = {"body": CHEST_USED, "frontSleeve": SLEEVE_USED, "backSleeve": SLEEVE_USED,
                  "legs": PANTS_USED, "head": HEAD_USED, "back": PANTS_USED}
    seen = set()
    case_issues = []
    for gender in ("male", "female"):
        refs = item.refs(gender)
        if not refs:
            out.append(("error", f"{gender}Frames is missing"))
            continue
        for role, ref in refs.items():
            wanted, disk, exact = item.image_path(gender, role)
            tag = f"{gender} {role} '{asset_path_parts(ref)}'"
            if (role, str(wanted)) in seen:
                continue
            seen.add((role, str(wanted)))
            if disk is None:
                out.append(("error", f"{tag}: file not found"))
                continue
            if not exact:
                case_issues.append((wanted, disk))
                out.append(("error", f"{tag}: on disk it's '{disk.name}'. Starbound paths are case-sensitive, so "
                                     f"this will fail in game (use 'Fix file-name case')."))
            boxes, where = find_frames(item.mod_dir, wanted)
            if boxes is None:
                out.append(("error", f"{tag}: {where}"))
                continue
            img = get_image(disk)
            if img is None:
                out.append(("error", f"{tag}: can't read image"))
                continue
            used = [n for n in roles_used.get(role, []) if n in boxes]
            missing_names = [n for n in roles_used.get(role, []) if n not in boxes]
            if missing_names:
                out.append(("warn", f"{tag}: frames file ({where}) has no " + ", ".join(missing_names[:8])))
            need_w = max((boxes[n][2] for n in used), default=0)
            need_h = max((boxes[n][3] for n in used), default=0)
            if img.width < need_w or img.height < need_h:
                out.append(("error", f"{tag}: sheet is {img.width}x{img.height}, frames need at least "
                                     f"{need_w}x{need_h}"))
            counts = {}
            for n in used:
                b = boxes[n]
                if b[2] <= img.width and b[3] <= img.height:
                    counts[n] = _opaque_count(img.crop(b))
            arm = arm_images.get(role)
            arm_counts = {}
            if arm is not None:
                for n in counts:
                    b = arm_boxes.get(n)
                    if b and b[2] <= arm.width and b[3] <= arm.height:
                        arm_counts[n] = _opaque_count(arm.crop(b))
            empty = [n for n, c in counts.items() if c == 0]
            if counts and len(empty) == len(counts):
                level = "info" if "Sleeve" in role else "error"
                out.append((level, f"{tag}: every frame is empty" + (" (sleeveless?)" if level == "info" else "")))
            elif empty:
                if arm_counts:
                    # an empty sleeve is fine where the arm is hidden too
                    exposed = [n for n in empty if arm_counts.get(n, 0) > 0]
                    if exposed:
                        out.append(("error", f"{tag}: empty frame(s) where the arm is visible: "
                                             f"{', '.join(exposed)}. The bare arm will show there."))
                else:
                    out.append(("error", f"{tag}: empty frame(s): {', '.join(empty)}. "
                                         f"The clothing will vanish there."))
            seq_key = "pants" if role in ("legs", "back") else "sleeve" if "Sleeve" in role else None
            for base, cnt in SEQUENCES.get(seq_key, []):
                names = [f"{base}.{i}" for i in range(1, cnt + 1)]
                if arm_counts:
                    # judge sleeves by how much of the arm they cover
                    vals = [(n, counts[n] / arm_counts[n]) for n in names
                            if counts.get(n) and arm_counts.get(n)]
                    fmt = lambda n, v, med: f"{n} (covers {v:.0%} of the arm vs ~{med:.0%})"
                else:
                    vals = [(n, counts[n]) for n in names if counts.get(n)]
                    fmt = lambda n, v, med: f"{n} ({v}px vs ~{med}px)"
                if len(vals) < 3:
                    continue
                med = sorted(v for _, v in vals)[len(vals) // 2]
                odd = [fmt(n, v, med) for n, v in vals if v < med * 0.5 or v > med * 2]
                if odd:
                    out.append(("warn", f"{tag}: {base} frame(s) look very different from the rest of the "
                                        f"animation: {', '.join(odd)}"))
            # pixels that don't change with color options
            if keys:
                stray = {}
                for n in used:
                    b = boxes[n]
                    if b[2] > img.width or b[3] > img.height:
                        continue
                    for px in img.crop(b).getdata():
                        if px[3]:
                            h = "%02x%02x%02x" % px[:3]
                            if h not in keys:
                                stray[h] = stray.get(h, 0) + 1
                if stray:
                    top = ", ".join(f"#{h.upper()} x{c}" for h, c in sorted(stray.items(), key=lambda t: -t[1])[:6])
                    out.append(("info", f"{tag}: colors that don't change with the color option: {top}"
                                        f"{' ...' if len(stray) > 6 else ''}"))
    icon = item.data.get("inventoryIcon")
    if isinstance(icon, str):
        wanted = resolve_ref(item.mod_dir, item.path.parent, icon)
        disk, exact = exact_or_case_match(wanted)
        if disk is None:
            out.append(("error", f"inventoryIcon '{asset_path_parts(icon)}': file not found"))
        elif not exact:
            case_issues.append((wanted, disk))
            out.append(("error", f"inventoryIcon '{asset_path_parts(icon)}': on disk it's '{disk.name}' "
                                 f"(case mismatch)"))
    if not item.options:
        out.append(("warn", "no colorOptions: the item can't be dyed and character creation can't recolor it"))
    if not [m for m in out if m[0] in ("error", "warn")]:
        out.insert(0, ("ok", "No problems found."))
    item.case_issues = case_issues
    return out


def fix_case(case_issues):
    """Rename files on disk to the exact case the config uses. Returns list of 'old -> new'."""
    done = []
    for wanted, disk in case_issues:
        disk = Path(disk)
        wanted = Path(wanted)
        if not disk.exists() or disk.name == wanted.name:
            continue
        tmp = disk.with_name(disk.name + ".casefix.tmp")
        disk.rename(tmp)          # two steps: Windows ignores case-only renames
        tmp.rename(disk.with_name(wanted.name))
        done.append(f"{disk.name} -> {wanted.name}")
    return done
