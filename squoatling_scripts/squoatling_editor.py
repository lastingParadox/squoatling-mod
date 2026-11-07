"""
Squoatling preview & palette editor.

Run:  python squoatling_scripts/squoatling_editor.py      (needs Pillow; tkinter ships with Python)

- Composites body + head + hair + markings + emote + arms the same way Starbound's
  humanoid renderer does (vanilla frame grids and offsets from humanoid.config).
- Edits the fur/eye palettes. "Save" writes BOTH species/squoatling.species and the
  swatch images in squoatling_scripts/skins/, because the pack script
  (grab_colors.py) regenerates the species palettes from those swatches.
- Watches every sprite it draws (and the species file) and redraws when they change on disk.
"""

import copy
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageTk

# --------------------------------------------------------------------------- paths

SCRIPT_DIR = Path(__file__).resolve().parent
MOD_DIR = SCRIPT_DIR.parent
HUMANOID_DIR = MOD_DIR / "humanoid" / "squoatling"
SPECIES_FILE = MOD_DIR / "species" / "squoatling.species"
SKINS_DIR = SCRIPT_DIR / "skins"

# --------------------------------------------------------------------------- palette keys
# Same keys / descriptions / swatch positions as grab_colors.py.

BODY_KEYS = [
    ("CDBC89", "Primary Fur"),
    ("D9CFAC", "Secondary Fur"),
    ("A08E58", "Tertiary Fur"),
    ("897A4B", "Lighter Outline"),
    ("72643E", "Darker Outline"),
    ("AF7E55", "Hoof / Snout"),
    ("7F5B3E", "Dark Hoof Outline"),
    ("5E432E", "Darker Hoof Outline"),
    ("DED19F", "Horn"),
    ("968F72", "Horn Outline"),
    ("C1B68D", "Horn Ridges"),
]
EYE_KEYS = [
    ("FACF20", "Light Eye"),
    ("CFA100", "Eye"),
    ("AB7D00", "Dark Eye"),
]

# --------------------------------------------------------------------------- vanilla frame data
# From assets/humanoid/{male,female}body.frames, frontarm.frames, emote.frames, humanoid.config

FRAME = 43

BODY_GRID = [
    [None, "idle.1", "idle.2", "idle.3", "idle.4", "idle.5", "sit.1", None, "duck.1"],
    [None, "walk.1", "walk.2", "walk.3", "walk.4", "walk.5", "walk.6", "walk.7", "walk.8"],
    [None, "run.1", "run.2", "run.3", "run.4", "run.5", "run.6", "run.7", "run.8"],
    [None, "jump.1", "jump.2", "jump.3", "jump.4", "fall.1", "fall.2", "fall.3", "fall.4"],
    [None, "climb.1", "climb.2", "climb.3", "climb.4", "climb.5", "climb.6", "climb.7", "climb.8"],
    [None, "swimIdle.1", None, None, "swim.1", "swim.2", "swim.3", "swim.4"],
]
BODY_ALIASES = {"swimIdle.2": "swimIdle.1", "swim.5": "swimIdle.1", "swim.6": "swimIdle.1",
                "swim.7": "swimIdle.1", "lay.1": "run.8"}

ARM_GRID = [
    [None, "idle.1", "idle.2", "idle.3", "idle.4", "idle.5", None, None, "duck.1"],
    [None, None, "walk.1", "walk.2", "walk.3", "walk.4", "walk.5", None, "rotation"],
    [None, None, "run.1", "run.2", "run.3", "run.4", "run.5", None, None],
    [None, "jump.1", "jump.2", "jump.3", "jump.4", "fall.1", "fall.2", "fall.3", "fall.4"],
    [None] * 9,
    [None, "swimIdle.1", "swimIdle.2", None, "swim.1", "swim.2", "swim.3", "swim.4", "swim.5"],
    [None, None, None, "idleMelee", None, None, None, None, "duckMelee"],
]
ARM_ALIASES = {"swim.6": "swimIdle.1", "swim.7": "swimIdle.2", "sit.1": "idle.1", "lay.1": "idle.1"}

EMOTE_GRID = [
    [None, "blabber.1", "blabber.2", None, "shout.1", "shout.2", None, None],
    [None, "happy.1", "happy.2", None, None, None, None, "idle.1"],
    [None, "sad.1", "sad.2", "sad.3", "sad.4", "sad.5", None, None],
    [None, "neutral.1", "neutral.2", None, "laugh.1", "laugh.2", None, None],
    [None, "annoyed.1", "annoyed.2", None, None, None, None, None],
    [None, "oh.1", "oh.2", None, "oooh.1", "oooh.2", "oooh.3", None],
    [None] * 8,
    [None, "blink.1", "blink.2", None, "wink.1", "wink.2", "wink.3", "wink.4"],
]
EMOTE_ALIASES = {"eat.1": "shout.1", "eat.2": "shout.2", "blink.3": "idle.1", "wink.5": "idle.1",
                 "sleep.1": "blink.2", "sleep.2": "blink.2"}
# (label, frame base, frame count, seconds per cycle) from humanoidTiming.emoteCycle/emoteFrames
EMOTES = [
    ("Idle", "idle", 1, 1.0), ("Blabber", "blabber", 2, 0.3), ("Shout", "shout", 2, 0.3),
    ("Happy", "happy", 2, 0.3), ("Sad", "sad", 5, 1.0), ("Neutral", "neutral", 2, 0.3),
    ("Laugh", "laugh", 2, 0.5), ("Annoyed", "annoyed", 2, 1.0), ("Oh", "oh", 2, 1.0),
    ("Oooh", "oooh", 3, 1.0), ("Blink", "blink", 3, 1.0), ("Wink", "wink", 5, 0.5),
    ("Eat", "eat", 2, 0.3), ("Sleep", "sleep", 2, 1.0),
]

HEAD_FRAMES = {"normal": (1, 0), "climb": (1, 4)}  # hair/head/markings default.frames

# (body/arm frame base, frame count, seconds per cycle)
STATES = {
    "Idle": ("idle", 1, 1.0),
    "Walk": ("walk", 8, 0.75),
    "Run": ("run", 8, 0.75),
    "Jump": ("jump", 4, 0.25),
    "Fall": ("fall", 4, 0.25),
    "Climb": ("climb", 8, 0.8),
    "Swim": ("swim", 7, 0.5),
    "SwimIdle": ("swimIdle", 2, 0.5),
    "Duck": ("duck", 1, 1.0),
    "Sit": ("sit", 1, 1.0),
}

ARM_WALK_SEQ = [2, 1, 2, 3, 4, 5, 4, 3]
ARM_RUN_SEQ = [2, 1, 2, 3, 4, 5, 4, 3]
WALK_BOB = [-1, -2, -1, 0, -1, -2, -1, 0]
RUN_BOB = [-1, 0, -1, -2, -1, 0, -1, -2]
SWIM_BOB = [0, -1, -2, -1, 0, 0, 0]
RUN_FALL_OFFSET = 1
JUMP_BOB = 1
DUCK_OFFSET = -8
SIT_OFFSET = -1
HEAD_RUN_OFFSET = (1, 0)
HEAD_SWIM_OFFSET = (1, 0)
HEAD_DUCK_OFFSET = (1, 0)
HEAD_SIT_OFFSET = (0, 0)

# (name, body idle frame, arm idle frame, head offset, arm offset)
PERSONALITIES = [
    ("Standard", "idle.1", "idle.1", (0, 0), (0, 0)),
    ("Confident", "idle.2", "idle.2", (-1, 0), (0, 0)),
    ("Gunslinger", "idle.3", "idle.3", (-1, 0), (0, 0)),
    ("Heroic", "idle.4", "idle.4", (-1, 0), (0, 0)),
    ("Scared", "idle.5", "idle.5", (0, 0), (0, 0)),
    ("Wonderful", "idle.2", "idle.5", (-1, 0), (0, 0)),
    ("Prepared", "idle.4", "idle.3", (-1, 0), (1, 0)),
    ("Fabulous", "idle.5", "idle.2", (0, 0), (0, 0)),
    ("Stoic", "idle.4", "idle.1", (0, 0), (0, 0)),
    ("Nervous", "idle.5", "idle.3", (0, 0), (2, 0)),
]

BACKGROUNDS = {"Dark": (40, 42, 54), "Mid": (110, 110, 120), "Light": (225, 225, 230),
               "Sky": (120, 170, 220), "Checker": None}

PAD = 12  # extra pixels around the 43x43 frame so offsets never clip


def build_lookup(grid, aliases):
    out = {}
    for r, row in enumerate(grid):
        for c, name in enumerate(row):
            if name:
                out[name] = (c, r)
    for alias, target in aliases.items():
        if target in out:
            out.setdefault(alias, out[target])
    return out


BODY_LOOKUP = build_lookup(BODY_GRID, BODY_ALIASES)
ARM_LOOKUP = build_lookup(ARM_GRID, ARM_ALIASES)
EMOTE_LOOKUP = build_lookup(EMOTE_GRID, EMOTE_ALIASES)

# --------------------------------------------------------------------------- helpers


def strip_json_comments(text):
    """Starbound JSON allows // and /* */ comments; strip them (outside strings)."""
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


def load_species():
    raw = SPECIES_FILE.read_bytes().decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(strip_json_comments(raw))
    return data, raw


def norm_hex(s):
    s = s.strip().lstrip("#").upper()
    if len(s) == 8 and s.endswith("FF"):
        s = s[:6]
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6 or any(ch not in "0123456789ABCDEF" for ch in s):
        return None
    return s


def hex_rgba(h):
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def readable_fg(h):
    r, g, b, _ = hex_rgba(h)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#FFFFFF"


def recolor(img, mapping):
    """Apply a Starbound ?replace directive (exact opaque RGB match)."""
    if not mapping:
        return img
    data = [mapping.get(px, px) for px in img.getdata()]
    out = Image.new("RGBA", img.size)
    out.putdata(data)
    return out


def skin_sort_key(p):
    return (0, int(p.stem), p.name) if p.stem.isdigit() else (1, 0, p.name)


class ImageCache:
    """Loads sprites as RGBA and reloads them when their mtime changes."""

    def __init__(self):
        self.entries = {}  # path -> (mtime, image or None)

    def get(self, path):
        path = Path(path)
        if path not in self.entries:
            self._load(path)
        return self.entries[path][1]

    def _load(self, path):
        try:
            mtime = path.stat().st_mtime_ns
            with Image.open(path) as im:
                img = im.convert("RGBA")
            self.entries[path] = (mtime, img)
            return True
        except Exception:
            # Missing or half-written file: remember "nothing" and retry on next poll.
            old = self.entries.get(path, (None, None))[1]
            self.entries[path] = (None, old)
            return False

    def poll(self):
        changed = False
        for path, (mtime, _img) in list(self.entries.items()):
            try:
                now = path.stat().st_mtime_ns
            except OSError:
                now = None
            if now != mtime:
                changed |= self._load(path) or now is None
        return changed


# --------------------------------------------------------------------------- app


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Squoatling Editor")
        self.minsize(1050, 680)

        self.cache = ImageCache()
        self.palettes = []          # [{"body": {key: hex}, "eye": {key: hex}}]
        self.saved_palettes = []
        self.species_mtime = None
        self.species_text = ""
        self.skin_template = None   # list of ("body"/"eye", key) | None per pixel
        self.skin_size = None
        self.selected = 0
        self.anim_frame = 0
        self.emote_frame = 0
        self.preview_photo = None
        self.swatch_photos = []
        self.hair_options = {}
        self.marking_options = {}
        self.swatch_widgets = {}

        self._build_ui()
        self.load_from_disk(initial=True)

        self.bind_all("<Control-s>", lambda e: self.save())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self._anim_tick)
        self.after(150, self._emote_tick)
        self.after(500, self._poll)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Palette.Treeview", rowheight=22)
        style.configure("Dirty.TLabel", foreground="#C0392B")

        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(0, weight=1)

        # ---------------- left: preview + controls
        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        # A Canvas doesn't resize to its content, so zooming never changes the window size.
        self.preview_canvas = tk.Canvas(left, width=560, height=480, bg="#282A36", bd=1,
                                        relief="sunken", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", lambda e: self.render())
        self._checker_cache = None

        ctrl = ttk.LabelFrame(left, text="Preview", padding=6)
        ctrl.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for c in (1, 3, 5):
            ctrl.columnconfigure(c, weight=1)

        self.gender = tk.StringVar(value="male")
        self.state_var = tk.StringVar(value="Idle")
        self.personality = tk.StringVar(value=PERSONALITIES[0][0])
        self.hair_var = tk.StringVar()
        self.marking_var = tk.StringVar(value="(none)")
        self.emote_var = tk.StringVar(value="Idle")
        self.eye_var = tk.StringVar(value="Same as fur palette")
        self.bg_var = tk.StringVar(value="Dark")
        self.zoom = tk.IntVar(value=8)
        self.playing = tk.BooleanVar(value=True)
        self.emote_playing = tk.BooleanVar(value=True)
        self.show_arms = tk.BooleanVar(value=True)
        self.color_hair = tk.BooleanVar(value=True)
        self.face_left = tk.BooleanVar(value=False)
        self.frame_var = tk.IntVar(value=1)

        r = 0
        ttk.Label(ctrl, text="Gender").grid(row=r, column=0, sticky="w")
        gf = ttk.Frame(ctrl)
        gf.grid(row=r, column=1, sticky="w")
        for g in ("male", "female"):
            ttk.Radiobutton(gf, text=g.title(), value=g, variable=self.gender,
                            command=self._gender_changed).pack(side="left", padx=(0, 6))
        ttk.Label(ctrl, text="Pose").grid(row=r, column=2, sticky="w", padx=(10, 0))
        cb = ttk.Combobox(ctrl, textvariable=self.state_var, values=list(STATES), state="readonly", width=14)
        cb.grid(row=r, column=3, sticky="ew")
        cb.bind("<<ComboboxSelected>>", lambda e: self._state_changed())
        ttk.Label(ctrl, text="Personality").grid(row=r, column=4, sticky="w", padx=(10, 0))
        cb = ttk.Combobox(ctrl, textvariable=self.personality, values=[p[0] for p in PERSONALITIES],
                          state="readonly", width=14)
        cb.grid(row=r, column=5, sticky="ew")
        cb.bind("<<ComboboxSelected>>", lambda e: self.render())

        r += 1
        ttk.Label(ctrl, text="Frame").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ff = ttk.Frame(ctrl)
        ff.grid(row=r, column=1, columnspan=3, sticky="ew", pady=(6, 0))
        ff.columnconfigure(0, weight=1)
        self.frame_scale = tk.Scale(ff, from_=1, to=1, orient="horizontal", variable=self.frame_var,
                                    showvalue=True, command=lambda v: self._frame_scrubbed())
        self.frame_scale.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(ff, text="Animate", variable=self.playing).grid(row=0, column=1, padx=6)
        self.frame_name_label = ttk.Label(ctrl, text="", foreground="#666")
        self.frame_name_label.grid(row=r, column=4, columnspan=2, sticky="w", padx=(10, 0), pady=(6, 0))

        r += 1
        ttk.Label(ctrl, text="Hair").grid(row=r, column=0, sticky="w", pady=(6, 0))
        self.hair_cb = ttk.Combobox(ctrl, textvariable=self.hair_var, state="readonly", width=26)
        self.hair_cb.grid(row=r, column=1, sticky="ew", pady=(6, 0))
        self.hair_cb.bind("<<ComboboxSelected>>", lambda e: self.render())
        ttk.Label(ctrl, text="Markings").grid(row=r, column=2, sticky="w", padx=(10, 0), pady=(6, 0))
        self.marking_cb = ttk.Combobox(ctrl, textvariable=self.marking_var, state="readonly", width=14)
        self.marking_cb.grid(row=r, column=3, sticky="ew", pady=(6, 0))
        self.marking_cb.bind("<<ComboboxSelected>>", lambda e: self.render())
        ttk.Label(ctrl, text="Emote").grid(row=r, column=4, sticky="w", padx=(10, 0), pady=(6, 0))
        ef = ttk.Frame(ctrl)
        ef.grid(row=r, column=5, sticky="ew", pady=(6, 0))
        ef.columnconfigure(0, weight=1)
        cb = ttk.Combobox(ef, textvariable=self.emote_var, values=[e[0] for e in EMOTES],
                          state="readonly", width=10)
        cb.grid(row=0, column=0, sticky="ew")
        cb.bind("<<ComboboxSelected>>", lambda e: (setattr(self, "emote_frame", 0), self.render()))
        ttk.Checkbutton(ef, text="Anim", variable=self.emote_playing).grid(row=0, column=1, padx=(4, 0))

        r += 1
        ttk.Label(ctrl, text="Eyes").grid(row=r, column=0, sticky="w", pady=(6, 0))
        self.eye_cb = ttk.Combobox(ctrl, textvariable=self.eye_var, state="readonly", width=26)
        self.eye_cb.grid(row=r, column=1, sticky="ew", pady=(6, 0))
        self.eye_cb.bind("<<ComboboxSelected>>", lambda e: self.render())
        ttk.Label(ctrl, text="Background").grid(row=r, column=2, sticky="w", padx=(10, 0), pady=(6, 0))
        cb = ttk.Combobox(ctrl, textvariable=self.bg_var, values=list(BACKGROUNDS), state="readonly", width=10)
        cb.grid(row=r, column=3, sticky="ew", pady=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.render())
        ttk.Label(ctrl, text="Zoom").grid(row=r, column=4, sticky="w", padx=(10, 0), pady=(6, 0))
        tk.Scale(ctrl, from_=2, to=14, orient="horizontal", variable=self.zoom, showvalue=True,
                 command=lambda v: self.render()).grid(row=r, column=5, sticky="ew")

        r += 1
        tf = ttk.Frame(ctrl)
        tf.grid(row=r, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Checkbutton(tf, text="Show arms", variable=self.show_arms, command=self.render).pack(side="left")
        ttk.Checkbutton(tf, text="Apply palette to hair & markings", variable=self.color_hair,
                        command=self.render).pack(side="left", padx=12)
        ttk.Checkbutton(tf, text="Face left", variable=self.face_left, command=self.render).pack(side="left")

        # ---------------- right: palettes
        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="ns")
        right.rowconfigure(1, weight=1)

        lf = ttk.LabelFrame(right, text="Palettes (fur + eyes, in-game order)", padding=6)
        lf.grid(row=0, column=0, rowspan=2, sticky="nsew")
        lf.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(lf, show="tree", style="Palette.Treeview", height=10, selectmode="browse")
        self.tree.column("#0", width=250)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)

        bf = ttk.Frame(lf)
        bf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for i in range(3):
            bf.columnconfigure(i, weight=1)
        ttk.Button(bf, text="Duplicate", command=self.add_palette).grid(row=0, column=0, sticky="ew")
        ttk.Button(bf, text="New (base)", command=lambda: self.add_palette(base=True)).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(bf, text="Delete", command=self.delete_palette).grid(row=0, column=2, sticky="ew")
        ttk.Button(bf, text="Move up", command=lambda: self.move_palette(-1)).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Button(bf, text="Move down", command=lambda: self.move_palette(1)).grid(row=1, column=1, sticky="ew", padx=3, pady=(3, 0))

        ed = ttk.LabelFrame(right, text="Colors", padding=6)
        ed.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.editor_title = ttk.Label(ed, text="", font=("TkDefaultFont", 9, "bold"))
        self.editor_title.grid(row=0, column=0, columnspan=4, sticky="w")
        row = 1
        for group, keys, title in (("body", BODY_KEYS, "Fur (bodyColor)"), ("eye", EYE_KEYS, "Eyes (undyColor)")):
            ttk.Label(ed, text=title, foreground="#555").grid(row=row, column=0, columnspan=4, sticky="w", pady=(6, 2))
            row += 1
            for key, desc in keys:
                ttk.Label(ed, text=desc).grid(row=row, column=0, sticky="w")
                base = tk.Label(ed, width=2, bg="#" + key, relief="solid", bd=1)
                base.grid(row=row, column=1, padx=(6, 2))
                base.bind("<Enter>", lambda e, k=key: self.status(f"Base sprite color #{k}"))
                sw = tk.Label(ed, width=4, relief="raised", bd=1, cursor="hand2")
                sw.grid(row=row, column=2, padx=2, pady=1)
                sw.bind("<Button-1>", lambda e, g=group, k=key: self.pick_color(g, k))
                var = tk.StringVar()
                ent = ttk.Entry(ed, textvariable=var, width=9, font=("Consolas", 10))
                ent.grid(row=row, column=3, sticky="w")
                ent.bind("<Return>", lambda e, g=group, k=key: self.hex_entered(g, k))
                ent.bind("<FocusOut>", lambda e, g=group, k=key: self.hex_entered(g, k))
                self.swatch_widgets[(group, key)] = (sw, var, ent)
                row += 1

        sf = ttk.Frame(right)
        sf.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        sf.columnconfigure(0, weight=1)
        self.dirty_label = ttk.Label(sf, text="", style="Dirty.TLabel")
        self.dirty_label.grid(row=0, column=0, sticky="w")
        ttk.Button(sf, text="Revert", command=self.revert).grid(row=0, column=1, padx=4)
        self.save_btn = ttk.Button(sf, text="Save  (Ctrl+S)", command=self.save)
        self.save_btn.grid(row=0, column=2)

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=(6, 2)).pack(
            fill="x", side="bottom")

    def status(self, msg):
        self.status_var.set(msg)

    # ------------------------------------------------------------------ loading
    def load_from_disk(self, initial=False):
        try:
            data, raw = load_species()
        except Exception as ex:
            messagebox.showerror("Squoatling Editor", f"Could not read {SPECIES_FILE}:\n{ex}")
            if initial:
                self.destroy()
                raise SystemExit(1)
            return
        self.species = data
        self.species_text = raw
        self.species_mtime = SPECIES_FILE.stat().st_mtime_ns
        bodies = data.get("bodyColor", [])
        eyes = data.get("undyColor", [])
        pals = []
        for i in range(max(len(bodies), len(eyes))):
            body = dict(bodies[i]) if i < len(bodies) else {}
            eye = dict(eyes[i]) if i < len(eyes) else {}
            for k, _ in BODY_KEYS:
                body[k] = (norm_hex(str(body.get(k, k))) or k)
            for k, _ in EYE_KEYS:
                eye[k] = (norm_hex(str(eye.get(k, k))) or k)
            pals.append({"body": body, "eye": eye})
        self.palettes = pals
        self.saved_palettes = copy.deepcopy(pals)
        self.selected = min(self.selected, max(0, len(pals) - 1))
        self._build_skin_template()
        self._check_skins_match()
        self.refresh_palette_list()
        self.refresh_part_lists()
        self._state_changed()

    def _build_skin_template(self):
        """Learn which pixel of the swatch images holds which palette key, so swatches can
        be regenerated for any palette."""
        self.skin_template = None
        files = sorted(SKINS_DIR.glob("*.png"), key=skin_sort_key) if SKINS_DIR.is_dir() else []
        for i, f in enumerate(files):
            if i >= len(self.palettes):
                break
            pal = self.palettes[i]
            inverse = {}
            for g in ("body", "eye"):
                for k, v in pal[g].items():
                    inverse.setdefault(hex_rgba(v), []).append((g, k))
            if any(len(v) > 1 for v in inverse.values()):
                continue  # ambiguous palette (two keys share a color)
            try:
                with Image.open(f) as im:
                    img = im.convert("RGBA")
            except Exception:
                continue
            template, ok = [], True
            for px in img.getdata():
                if px[3] == 0:
                    template.append(None)
                elif px in inverse:
                    template.append(inverse[px][0])
                else:
                    ok = False
                    break
            if ok and len({t for t in template if t}) == len(BODY_KEYS) + len(EYE_KEYS):
                self.skin_template = template
                self.skin_size = img.size
                return

    def _check_skins_match(self):
        files = sorted(SKINS_DIR.glob("*.png"), key=skin_sort_key) if SKINS_DIR.is_dir() else []
        if self.skin_template is None:
            self.status("Warning: couldn't learn the skins/ swatch layout - Save will only write the species file "
                        "(and the pack script may overwrite it).")
        elif len(files) != len(self.palettes):
            self.status(f"Note: species has {len(self.palettes)} palettes but skins/ has {len(files)} images. "
                        "Saving will rewrite skins/ to match.")
        else:
            self.status(f"Loaded {len(self.palettes)} palettes from {SPECIES_FILE.name}.")

    # ------------------------------------------------------------------ parts lists
    def _species_gender(self):
        for g in self.species.get("genders", []):
            if g.get("name") == self.gender.get():
                return g
        return {}

    def refresh_part_lists(self):
        gdef = self._species_gender()
        in_species_hair = list(gdef.get("hair", []))
        hair_dir = HUMANOID_DIR / "hair"
        opts = {}
        for name in in_species_hair:
            opts[f"{name}"] = hair_dir / f"{name}.png"
        if hair_dir.is_dir():
            for p in sorted(hair_dir.glob("*.png")):
                if p.stem not in in_species_hair:
                    opts[f"{p.stem}   (not in species)"] = p
            for sub in sorted(d for d in hair_dir.iterdir() if d.is_dir()):
                for p in sorted(sub.glob("*.png"), key=lambda q: (len(q.stem), q.stem)):
                    opts[f"{sub.name}/{p.stem}"] = p
        if list(opts) != list(self.hair_options):
            self.hair_options = opts
            self.hair_cb["values"] = list(opts)
        if self.hair_var.get() not in opts:
            self.hair_var.set(next(iter(opts), ""))

        mark_group = gdef.get("facialHairGroup", "markings") or "markings"
        mark_dir = HUMANOID_DIR / mark_group
        listed = [str(x) for x in gdef.get("facialHair", [])]
        mopts = {"(none)": None}
        for name in listed:
            mopts[name] = mark_dir / f"{name}.png"
        if mark_dir.is_dir():
            for p in sorted(mark_dir.glob("*.png")):
                if p.stem not in listed:
                    mopts[f"{p.stem}   (not in species)"] = p
        if list(mopts) != list(self.marking_options):
            self.marking_options = mopts
            self.marking_cb["values"] = list(mopts)
        if self.marking_var.get() not in mopts:
            self.marking_var.set("(none)")

    def _gender_changed(self):
        self.refresh_part_lists()
        self.render()

    # ------------------------------------------------------------------ palette list
    def _swatch_strip(self, pal):
        s, gap = 14, 6
        w = s * len(BODY_KEYS) + gap + s * len(EYE_KEYS)
        img = Image.new("RGBA", (w + 1, s + 2), (0, 0, 0, 0))
        x = 0
        for g, keys in (("body", BODY_KEYS), ("eye", EYE_KEYS)):
            for k, _ in keys:
                img.paste(Image.new("RGBA", (s - 1, s), hex_rgba(pal[g][k])), (x, 1))
                x += s
            x += gap
        return ImageTk.PhotoImage(img)

    def refresh_palette_list(self):
        self.tree.delete(*self.tree.get_children())
        self.swatch_photos = []
        for i, pal in enumerate(self.palettes):
            ph = self._swatch_strip(pal)
            self.swatch_photos.append(ph)
            mark = " *" if i >= len(self.saved_palettes) or pal != self.saved_palettes[i] else ""
            self.tree.insert("", "end", iid=str(i), text=f" {i}{mark}", image=ph)
        if self.palettes:
            self.selected = max(0, min(self.selected, len(self.palettes) - 1))
            self.tree.selection_set(str(self.selected))
            self.tree.see(str(self.selected))
        self.eye_cb["values"] = ["Same as fur palette"] + [f"Palette {i}" for i in range(len(self.palettes))]
        if self.eye_var.get() not in self.eye_cb["values"]:
            self.eye_var.set("Same as fur palette")
        self.refresh_editor()
        self.update_dirty()

    def _update_row(self, i):
        ph = self._swatch_strip(self.palettes[i])
        self.swatch_photos[i] = ph
        mark = " *" if i >= len(self.saved_palettes) or self.palettes[i] != self.saved_palettes[i] else ""
        self.tree.item(str(i), image=ph, text=f" {i}{mark}")

    def _tree_selected(self, _e=None):
        sel = self.tree.selection()
        if sel:
            self.selected = int(sel[0])
            self.refresh_editor()
            self.render()

    def refresh_editor(self):
        if not self.palettes:
            self.editor_title.config(text="No palettes")
            return
        pal = self.palettes[self.selected]
        self.editor_title.config(text=f"Palette {self.selected}")
        for (g, k), (sw, var, _ent) in self.swatch_widgets.items():
            h = pal[g][k]
            sw.config(bg="#" + h, activebackground="#" + h)
            var.set(h)

    # ------------------------------------------------------------------ editing
    def set_color(self, group, key, hexv):
        pal = self.palettes[self.selected]
        if pal[group][key] == hexv:
            return
        pal[group][key] = hexv
        self._update_row(self.selected)
        self.refresh_editor()
        self.update_dirty()
        self.render()

    def pick_color(self, group, key):
        if not self.palettes:
            return
        cur = self.palettes[self.selected][group][key]
        res = colorchooser.askcolor(color="#" + cur, title=f"Palette {self.selected}: {key}", parent=self)
        if res and res[1]:
            self.set_color(group, key, norm_hex(res[1]))

    def hex_entered(self, group, key):
        if not self.palettes:
            return
        _sw, var, _ent = self.swatch_widgets[(group, key)]
        h = norm_hex(var.get())
        if h is None:
            self.bell()
            var.set(self.palettes[self.selected][group][key])
            self.status(f"'{var.get()}' isn't a hex color (use RRGGBB).")
            return
        self.set_color(group, key, h)

    def add_palette(self, base=False):
        if base or not self.palettes:
            pal = {"body": {k: k for k, _ in BODY_KEYS}, "eye": {k: k for k, _ in EYE_KEYS}}
        else:
            pal = copy.deepcopy(self.palettes[self.selected])
        self.palettes.append(pal)
        self.selected = len(self.palettes) - 1
        self.refresh_palette_list()
        self.render()

    def delete_palette(self):
        if not self.palettes:
            return
        if len(self.palettes) == 1:
            messagebox.showinfo("Squoatling Editor", "Can't delete the last palette.")
            return
        if not messagebox.askyesno("Delete palette", f"Delete palette {self.selected}?\n"
                                   "(Nothing is written until you Save.)"):
            return
        del self.palettes[self.selected]
        self.selected = min(self.selected, len(self.palettes) - 1)
        self.refresh_palette_list()
        self.render()

    def move_palette(self, d):
        j = self.selected + d
        if 0 <= j < len(self.palettes):
            p = self.palettes
            p[self.selected], p[j] = p[j], p[self.selected]
            self.selected = j
            self.refresh_palette_list()

    def is_dirty(self):
        return self.palettes != self.saved_palettes

    def update_dirty(self):
        dirty = self.is_dirty()
        self.dirty_label.config(text="Unsaved changes" if dirty else "")
        self.title(("* " if dirty else "") + "Squoatling Editor")

    def revert(self):
        if self.is_dirty() and not messagebox.askyesno("Revert", "Discard all unsaved palette changes?"):
            return
        self.palettes = copy.deepcopy(self.saved_palettes)
        self.refresh_palette_list()
        self.render()

    # ------------------------------------------------------------------ saving
    def save(self):
        if not self.palettes:
            return
        try:
            data, raw = load_species()  # re-read so other edits to the file are kept
        except Exception as ex:
            messagebox.showerror("Save failed", f"Could not read {SPECIES_FILE}:\n{ex}")
            return
        if strip_json_comments(raw) != raw and not messagebox.askyesno(
                "Comments will be lost", "The species file contains comments, which will be removed. Continue?"):
            return
        data["bodyColor"] = [{k: p["body"][k] for k in p["body"]} for p in self.palettes]
        data["undyColor"] = [{k: p["eye"][k] for k in p["eye"]} for p in self.palettes]
        newline = "\r\n" if "\r\n" in raw else "\n"
        text = json.dumps(data, indent=2)
        if raw.endswith(("\n", "\r\n")):
            text += "\n"
        try:
            with open(SPECIES_FILE, "w", encoding="utf-8", newline=newline) as f:
                f.write(text)
        except Exception as ex:
            messagebox.showerror("Save failed", f"Could not write {SPECIES_FILE}:\n{ex}")
            return
        self.species = data
        self.species_mtime = SPECIES_FILE.stat().st_mtime_ns

        skin_msg = ""
        if self.skin_template is not None:
            try:
                self._write_skins()
                skin_msg = f" and {len(self.palettes)} swatches in skins/"
            except Exception as ex:
                messagebox.showwarning("Skins not written",
                                       f"The species file was saved, but writing skins/ failed:\n{ex}\n\n"
                                       "The pack script regenerates palettes from skins/, so fix this before packing.")
        else:
            messagebox.showwarning("Skins not written",
                                   "Couldn't work out the skins/ swatch layout, so only the species file was saved.\n"
                                   "The pack script (grab_colors.py) will overwrite these palettes from skins/.")

        self.saved_palettes = copy.deepcopy(self.palettes)
        self.refresh_palette_list()
        self.status(f"Saved {len(self.palettes)} palettes to {SPECIES_FILE.name}{skin_msg}.")

    def _write_skins(self):
        w, h = self.skin_size
        tmp_files = []
        for i, pal in enumerate(self.palettes):
            px = [(0, 0, 0, 0) if t is None else hex_rgba(pal[t[0]][t[1]]) for t in self.skin_template]
            img = Image.new("RGBA", (w, h))
            img.putdata(px)
            tmp = SKINS_DIR / f"_saving_{i}.png.tmp"
            img.save(tmp, format="PNG")
            tmp_files.append(tmp)
        for old in SKINS_DIR.glob("*.png"):
            if old.stem.isdigit():
                old.unlink()
        for i, tmp in enumerate(tmp_files):
            tmp.replace(SKINS_DIR / f"{i}.png")

    def on_close(self):
        if self.is_dirty():
            ans = messagebox.askyesnocancel("Unsaved changes", "Save palette changes before closing?")
            if ans is None:
                return
            if ans:
                self.save()
                if self.is_dirty():
                    return
        self.destroy()

    # ------------------------------------------------------------------ animation
    def _state_changed(self):
        _base, count, _cycle = STATES[self.state_var.get()]
        self.frame_scale.config(to=count)
        self.anim_frame = 0
        self.frame_var.set(1)
        self.render()

    def _frame_scrubbed(self):
        self.anim_frame = self.frame_var.get() - 1
        self.render()

    def _anim_tick(self):
        _base, count, cycle = STATES[self.state_var.get()]
        delay = max(40, int(cycle / count * 1000))
        if self.playing.get() and count > 1:
            self.anim_frame = (self.anim_frame + 1) % count
            self.frame_var.set(self.anim_frame + 1)
            self.render()
        self.after(delay, self._anim_tick)

    def _current_emote(self):
        return next(e for e in EMOTES if e[0] == self.emote_var.get())

    def _emote_tick(self):
        _l, _b, count, cycle = self._current_emote()
        delay = max(40, int(cycle / count * 1000))
        if self.emote_playing.get() and count > 1:
            self.emote_frame = (self.emote_frame + 1) % count
            self.render()
        self.after(delay, self._emote_tick)

    # ------------------------------------------------------------------ polling
    def _poll(self):
        try:
            changed = self.cache.poll()
            # species file changed outside the editor?
            try:
                m = SPECIES_FILE.stat().st_mtime_ns
            except OSError:
                m = self.species_mtime
            if m != self.species_mtime:
                if self.is_dirty():
                    self.species_mtime = m
                    self.status("species file changed on disk; you have unsaved edits, so it wasn't reloaded "
                                "(Revert discards your edits; Save overwrites the palettes).")
                    try:
                        self.species, _ = load_species()
                    except Exception:
                        pass
                else:
                    self.load_from_disk()
                    self.status("species file changed on disk - reloaded.")
                changed = True
            # new hair/markings files appearing
            self.refresh_part_lists()
            if changed:
                self.render()
        finally:
            self.after(500, self._poll)

    # ------------------------------------------------------------------ rendering
    def _mapping(self, pal, eye_pal):
        m = {}
        if pal:
            for k, v in pal["body"].items():
                if k != v:
                    m[hex_rgba(k)] = hex_rgba(v)
        if eye_pal:
            for k, v in eye_pal["eye"].items():
                if k != v:
                    m[hex_rgba(k)] = hex_rgba(v)
        return m

    def _crop(self, path, cell):
        img = self.cache.get(path)
        if img is None or cell is None:
            return None
        c, r = cell
        box = (c * FRAME, r * FRAME, (c + 1) * FRAME, (r + 1) * FRAME)
        if box[2] > img.width or box[3] > img.height:
            return None
        return img.crop(box)

    def compose(self):
        gender = self.gender.get()
        state = self.state_var.get()
        base, count, _ = STATES[state]
        seq = (self.anim_frame % count) + 1
        pers = next(p for p in PERSONALITIES if p[0] == self.personality.get())

        pal = self.palettes[self.selected] if self.palettes else None
        eye_sel = self.eye_var.get()
        eye_pal = pal
        if eye_sel.startswith("Palette "):
            idx = int(eye_sel.split()[1])
            if idx < len(self.palettes):
                eye_pal = self.palettes[idx]
        mapping = self._mapping(pal, eye_pal)
        hair_mapping = mapping if self.color_hair.get() else {}

        # --- frame names (Humanoid::render logic)
        if state == "Idle":
            body_name, arm_name = pers[1], pers[2]
        elif state in ("Duck", "Sit"):
            body_name = arm_name = f"{base}.1"
        else:
            body_name = f"{base}.{seq}"
            arm_seq = seq
            if state == "Walk":
                arm_seq = ARM_WALK_SEQ[seq - 1]
            elif state == "Run":
                arm_seq = ARM_RUN_SEQ[seq - 1]
            arm_name = f"{base}.{arm_seq}"

        bob = 0
        head_off = (0, 0)
        arm_off = (0, 0)
        if state == "Idle":
            head_off, arm_off = pers[3], pers[4]
        elif state == "Walk":
            bob = WALK_BOB[seq - 1]
        elif state == "Run":
            bob = RUN_FALL_OFFSET + RUN_BOB[seq - 1]
            head_off = HEAD_RUN_OFFSET
        elif state == "Jump":
            bob = JUMP_BOB
        elif state == "Fall":
            bob = RUN_FALL_OFFSET
        elif state == "Swim":
            bob = SWIM_BOB[seq - 1]
            head_off = HEAD_SWIM_OFFSET
        elif state == "SwimIdle":
            head_off = HEAD_SWIM_OFFSET
        elif state == "Duck":
            bob = DUCK_OFFSET
            head_off = HEAD_DUCK_OFFSET
        elif state == "Sit":
            bob = SIT_OFFSET
            head_off = HEAD_SIT_OFFSET

        climbing = state == "Climb"
        head_cell = HEAD_FRAMES["climb" if climbing else "normal"]
        # game y is up, image y is down
        head_xy = (PAD + head_off[0], PAD - (bob + head_off[1]))
        arm_xy = (PAD + arm_off[0], PAD - arm_off[1])
        body_xy = (PAD, PAD)

        size = FRAME + 2 * PAD
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        missing = []

        def draw(path, cell, xy, m, label):
            if path is None:
                return
            crop = self._crop(path, cell)
            if crop is None:
                if cell is not None:
                    missing.append(label)
                return
            canvas.alpha_composite(recolor(crop, m), xy)

        show_arms = self.show_arms.get() and not climbing
        arm_cell = ARM_LOOKUP.get(arm_name)
        # Layer order matches Starbound's Humanoid::render:
        # back arm, head, emote, hair, body, [legs/chest armor], facial hair (markings), [facial mask],
        # [head armor], front arm. So the body is drawn OVER hair, and markings over the body.
        if show_arms:
            draw(HUMANOID_DIR / "backarm.png", arm_cell, arm_xy, mapping, "backarm")
        draw(HUMANOID_DIR / f"{gender}head.png", head_cell, head_xy, mapping, f"{gender}head")
        if not climbing:
            _l, ebase, ecount, _c = self._current_emote()
            ename = f"{ebase}.{(self.emote_frame % ecount) + 1}"
            draw(HUMANOID_DIR / "emote.png", EMOTE_LOOKUP.get(ename), head_xy, mapping, "emote")
        draw(self.hair_options.get(self.hair_var.get()), head_cell, head_xy, hair_mapping, "hair")
        draw(HUMANOID_DIR / f"{gender}body.png", BODY_LOOKUP.get(body_name), body_xy, mapping, f"{gender}body")
        draw(self.marking_options.get(self.marking_var.get()), head_cell, head_xy, hair_mapping, "markings")
        if show_arms:
            draw(HUMANOID_DIR / "frontarm.png", arm_cell, arm_xy, mapping, "frontarm")

        if self.face_left.get():
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)

        info = f"body: {body_name}"
        if show_arms:
            info += f"   arms: {arm_name}"
        if climbing:
            info += "   (arms are part of the climb body frames)"
        if missing:
            info += "   missing: " + ", ".join(missing)
        return canvas, info

    def render(self):
        if not hasattr(self, "species"):
            return
        try:
            img, info = self.compose()
        except Exception as ex:  # never let a bad file kill the UI
            self.frame_name_label.config(text=f"render error: {ex}")
            return
        self.frame_name_label.config(text=info)
        z = max(1, self.zoom.get())
        big = img.resize((img.width * z, img.height * z), Image.NEAREST)

        cv = self.preview_canvas
        cw, ch = max(1, cv.winfo_width()), max(1, cv.winfo_height())
        if cw <= 1 or ch <= 1:  # not laid out yet
            cw, ch = int(cv["width"]), int(cv["height"])
        bg = BACKGROUNDS[self.bg_var.get()]
        if bg is None:
            key = (cw, ch, z)
            if not self._checker_cache or self._checker_cache[0] != key:
                tile = 4 * z
                back = Image.new("RGBA", (cw, ch), (200, 200, 200, 255))
                dark = Image.new("RGBA", (tile, tile), (160, 160, 160, 255))
                # anchor the checker to the sprite so it lines up with sprite pixels
                ox = ((cw - big.width) // 2) % (tile * 2) - tile * 2
                oy = ((ch - big.height) // 2) % (tile * 2) - tile * 2
                for j, y in enumerate(range(oy, ch, tile)):
                    for x in range(ox + (j % 2) * tile, cw, tile * 2):
                        back.paste(dark, (x, y))
                self._checker_cache = (key, back)
            back = self._checker_cache[1].copy()
        else:
            back = Image.new("RGBA", (cw, ch), bg + (255,))
        # centered; anything larger than the canvas is simply clipped
        back.paste(big, ((cw - big.width) // 2, (ch - big.height) // 2), big)
        self.preview_photo = ImageTk.PhotoImage(back)
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=self.preview_photo)


def main():
    os.chdir(MOD_DIR)
    app = Editor()
    app.mainloop()


if __name__ == "__main__":
    main()
