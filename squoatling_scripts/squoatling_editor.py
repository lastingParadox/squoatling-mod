"""
Species preview & palette editor (Squoatling, Llamanian, Verinian).

Run:  python squoatling_scripts/squoatling_editor.py [--species llamanian]   (needs Pillow)
      or "Species Editor.bat". The species can be switched from the window.

- Composites body + head + hair + markings + emote + arms + clothing the same way Starbound's
  humanoid renderer does (vanilla frame grids and offsets from humanoid.config).
- "Palettes" tab edits the species palettes (bodyColor / undyColor, plus hairColor for species with
  their own hair colors) in species/<species>.species. Add a species in SPECIES_KEYS.
- "Clothing" tab edits colorOptions of everything in items/armors (written back in place, comments
  kept) and checks the sprite sheets for missing/empty/odd frames and file-name case problems.
- Watches every file it draws (and the configs) and redraws when they change on disk.
"""

import copy
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

import squoatling_clothing as sc

# --------------------------------------------------------------------------- paths

SCRIPT_DIR = Path(__file__).resolve().parent
MOD_DIR = SCRIPT_DIR.parent
# Vanilla assets unpacked next to the game's assets folder (Starbound/unpacked); used read-only for vanilla outfits
VANILLA_DIR = MOD_DIR.parent.parent / "unpacked"
# Per-species clothing offsets for the preview (pixels, + = down); edited from the window
OFFSETS_FILE = SCRIPT_DIR / "clothing_offsets.json"
# chest = shirt down; shrink = rows removed from the middle of the shirt (hem moves back up);
# frontSleeve / backSleeve follow each arm; legs = pants down; legsShrink = rows removed from the middle of the
# legs so the waistband moves down while the cuffs/feet stay on the ground.
# Verinian: shoulders + front arm sit 3px lower, back arm 2px, legs shorter - the shirt sits 3px lower minus one
# mid-torso row (hem 2px lower), the pants' waistband 2px lower with the legs 2 rows shorter (feet unchanged),
# so the waistband shows under the hem exactly like on the other species.
OFFSET_FIELDS = [("chest", "Shirt"), ("shrink", "Shirt shrink"), ("frontSleeve", "Front sleeve"),
                 ("backSleeve", "Back sleeve"), ("legs", "Pants"), ("legsShrink", "Pants shrink")]
SHRINK_FIELDS = {"shrink", "legsShrink"}
DEFAULT_OFFSETS = {"verinian": {"chest": 3, "shrink": 1, "frontSleeve": 3, "backSleeve": 2,
                                "legs": 2, "legsShrink": 2}}

def _species_arg():
    """`--species llamanian` (or SPECIES=llamanian) picks the species shown first; it can be switched
    in the window afterwards."""
    import sys
    a = sys.argv
    if "--species" in a and a.index("--species") + 1 < len(a):
        return a[a.index("--species") + 1].lower()
    return os.environ.get("SPECIES", "squoatling").lower()


# --------------------------------------------------------------------------- palette keys
# Base sprite colors (the keys of bodyColor / undyColor / hairColor in each species file) and their names.
# Set for the current species by set_species(); everything else reads these module globals.

SQUOATLING_BODY_KEYS = [
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
SQUOATLING_EYE_KEYS = [
    ("FACF20", "Light Eye"),
    ("CFA100", "Eye"),
    ("AB7D00", "Dark Eye"),
]

VERINIAN_BODY_KEYS = [
    ("954535", "Main Fur"),
    ("702E22", "Light Outline / Secondary Fur"),
    ("381913", "Dark Outline / Tertiary Fur"),
    ("B4A0A0", "Ear"),
    ("87807F", "Light Claw"),
    ("675B58", "Main Claw / Tail Stripe"),
    ("403836", "Dark Claw / Tail Stripe Outline"),
]
VERINIAN_EYE_KEYS = [
    ("B1B5D9", "Light Eye"),
    ("6A6AA0", "Main Eye"),
    ("5146A0", "Dark Eye"),
]
VERINIAN_HAIR_KEYS = [
    ("D9C189", "Hair Light"),
    ("A38D59", "Hair"),
    ("735E3A", "Hair Dark"),
]


def _llamanian_keys():
    """Llamanian sprites are the Squoatling ones repainted: translate the Squoatling role names through
    squoatling_scripts/llamanian/llamanian_palette.json (name kept, key swapped)."""
    table = SCRIPT_DIR / "llamanian" / "llamanian_palette.json"
    data = json.loads(table.read_text(encoding="utf-8"))
    return ([(data["body"][k]["to"].upper(), n) for k, n in SQUOATLING_BODY_KEYS],
            [(data["eye"][k]["to"].upper(), n) for k, n in SQUOATLING_EYE_KEYS])


# name -> (body keys, eye keys, hair keys or None). Hair keys = the species has its own hairColor list
# (headOptionAsHairColor); without them hair is tinted with the fur palette.
SPECIES_KEYS = {
    "squoatling": lambda: (SQUOATLING_BODY_KEYS, SQUOATLING_EYE_KEYS, None),
    "llamanian": lambda: _llamanian_keys() + (None,),
    "verinian": lambda: (VERINIAN_BODY_KEYS, VERINIAN_EYE_KEYS, VERINIAN_HAIR_KEYS),
}

SPECIES = HUMANOID_DIR = SPECIES_FILE = None
BODY_KEYS = EYE_KEYS = HAIR_KEYS = None


def available_species():
    return [s for s in SPECIES_KEYS if (MOD_DIR / "species" / f"{s}.species").exists()]


def set_species(name):
    """Point the module-level paths and key lists at another species."""
    global SPECIES, HUMANOID_DIR, SPECIES_FILE, BODY_KEYS, EYE_KEYS, HAIR_KEYS
    if name not in SPECIES_KEYS:
        raise ValueError(f"Unknown species '{name}' (known: {', '.join(SPECIES_KEYS)})")
    BODY_KEYS, EYE_KEYS, HAIR_KEYS = SPECIES_KEYS[name]()
    SPECIES = name
    HUMANOID_DIR = MOD_DIR / "humanoid" / name
    SPECIES_FILE = MOD_DIR / "species" / f"{name}.species"


set_species(_species_arg() if _species_arg() in SPECIES_KEYS else "squoatling")


# --------------------------------------------------------------------------- vanilla frame data
# From assets/humanoid/{male,female}body.frames, frontarm.frames, emote.frames, humanoid.config

FRAME = 43

BODY_FRAMES = sc.parse_frames({
    "frameGrid": {"size": [43, 43], "dimensions": [9, 6], "names": [
        [None, "idle.1", "idle.2", "idle.3", "idle.4", "idle.5", "sit.1", None, "duck.1"],
        [None, "walk.1", "walk.2", "walk.3", "walk.4", "walk.5", "walk.6", "walk.7", "walk.8"],
        [None, "run.1", "run.2", "run.3", "run.4", "run.5", "run.6", "run.7", "run.8"],
        [None, "jump.1", "jump.2", "jump.3", "jump.4", "fall.1", "fall.2", "fall.3", "fall.4"],
        [None, "climb.1", "climb.2", "climb.3", "climb.4", "climb.5", "climb.6", "climb.7", "climb.8"],
        [None, "swimIdle.1", None, None, "swim.1", "swim.2", "swim.3", "swim.4"],
    ]},
    "aliases": {"swimIdle.2": "swimIdle.1", "swim.5": "swimIdle.1", "swim.6": "swimIdle.1",
                "swim.7": "swimIdle.1", "lay.1": "run.8"},
})
ARM_FRAMES = sc.parse_frames(sc._ARM_GRID)
EMOTE_FRAMES = sc.parse_frames({
    "frameGrid": {"size": [43, 43], "dimensions": [8, 8], "names": [
        [None, "blabber.1", "blabber.2", None, "shout.1", "shout.2", None, None],
        [None, "happy.1", "happy.2", None, None, None, None, "idle.1"],
        [None, "sad.1", "sad.2", "sad.3", "sad.4", "sad.5", None, None],
        [None, "neutral.1", "neutral.2", None, "laugh.1", "laugh.2", None, None],
        [None, "annoyed.1", "annoyed.2", None, None, None, None, None],
        [None, "oh.1", "oh.2", None, "oooh.1", "oooh.2", "oooh.3", None],
        [None] * 8,
        [None, "blink.1", "blink.2", None, "wink.1", "wink.2", "wink.3", "wink.4"],
    ]},
    "aliases": {"eat.1": "shout.1", "eat.2": "shout.2", "blink.3": "idle.1", "wink.5": "idle.1",
                "sleep.1": "blink.2", "sleep.2": "blink.2"},
})
HEAD_FRAMES = sc.parse_frames(sc._HEAD)  # hair/head/markings default.frames

# (label, frame base, frame count, seconds per cycle) from humanoidTiming.emoteCycle/emoteFrames
EMOTES = [
    ("Idle", "idle", 1, 1.0), ("Blabber", "blabber", 2, 0.3), ("Shout", "shout", 2, 0.3),
    ("Happy", "happy", 2, 0.3), ("Sad", "sad", 5, 1.0), ("Neutral", "neutral", 2, 0.3),
    ("Laugh", "laugh", 2, 0.5), ("Annoyed", "annoyed", 2, 1.0), ("Oh", "oh", 2, 1.0),
    ("Oooh", "oooh", 3, 1.0), ("Blink", "blink", 3, 1.0), ("Wink", "wink", 5, 0.5),
    ("Eat", "eat", 2, 0.3), ("Sleep", "sleep", 2, 1.0),
]

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
NONE = "(none)"

# --------------------------------------------------------------------------- helpers


def load_species():
    data, raw = sc.load_json_file(SPECIES_FILE)
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


def recolor(img, mapping):
    """Apply a Starbound ?replace directive (exact opaque RGB match)."""
    if not mapping:
        return img
    data = [mapping.get(px, px) for px in img.getdata()]
    out = Image.new("RGBA", img.size)
    out.putdata(data)
    return out


def shrink_rows(img, n):
    """Remove n rows from the middle of the sprite's painted area (rows below move up), so a piece keeps its
    top and bottom edges (collar/hem, waistband/cuffs) but gets n px shorter - for species with a shorter
    torso or legs."""
    bbox = img.getchannel("A").getbbox()
    if not bbox or n <= 0:
        return img
    top, bottom = bbox[1], bbox[3]
    for _ in range(min(n, max(0, bottom - top - 2))):
        y = top + int((bottom - top) * 0.55)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.paste(img.crop((0, 0, img.width, y)), (0, 0))
        out.paste(img.crop((0, y + 1, img.width, img.height)), (0, y))
        img, bottom = out, bottom - 1
    return img


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

    def forget(self, path):
        self.entries.pop(Path(path), None)

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


class ColorRows:
    """A block of 'label | base swatch | current swatch | hex entry' rows."""

    def __init__(self, app, parent, on_pick, on_hex):
        self.app, self.parent, self.on_pick, self.on_hex = app, parent, on_pick, on_hex
        self.widgets = {}
        self.row = 0

    def clear(self):
        for w in self.parent.winfo_children():
            w.destroy()
        self.widgets = {}
        self.row = 0

    def header(self, text):
        ttk.Label(self.parent, text=text, foreground="#555").grid(row=self.row, column=0, columnspan=4,
                                                                  sticky="w", pady=(6, 2))
        self.row += 1

    def add(self, ident, base_hex, label):
        r = self.row
        ttk.Label(self.parent, text=label).grid(row=r, column=0, sticky="w")
        base = tk.Label(self.parent, width=2, bg="#" + base_hex, relief="solid", bd=1)
        base.grid(row=r, column=1, padx=(6, 2))
        base.bind("<Enter>", lambda e: self.app.status(f"Base sprite color #{base_hex}"))
        sw = tk.Label(self.parent, width=4, relief="raised", bd=1, cursor="hand2")
        sw.grid(row=r, column=2, padx=2, pady=1)
        sw.bind("<Button-1>", lambda e: self.on_pick(ident))
        var = tk.StringVar()
        ent = ttk.Entry(self.parent, textvariable=var, width=9, font=("Consolas", 10))
        ent.grid(row=r, column=3, sticky="w")
        ent.bind("<Return>", lambda e: self.on_hex(ident))
        ent.bind("<FocusOut>", lambda e: self.on_hex(ident))
        self.widgets[ident] = (sw, var)
        self.row += 1

    def set(self, ident, hexv):
        sw, var = self.widgets[ident]
        sw.config(bg="#" + hexv, activebackground="#" + hexv)
        var.set(hexv)

    def get_text(self, ident):
        return self.widgets[ident][1].get()


def swatch_strip(groups, size=14, gap=6):
    """groups: list of lists of hex colors -> PhotoImage strip."""
    w = sum(len(g) * size for g in groups) + gap * (len(groups) - 1)
    img = Image.new("RGBA", (max(1, w) + 1, size + 2), (0, 0, 0, 0))
    x = 0
    for g in groups:
        for h in g:
            img.paste(Image.new("RGBA", (size - 1, size), hex_rgba(h)), (x, 1))
            x += size
        x += gap
    return ImageTk.PhotoImage(img)


# --------------------------------------------------------------------------- app


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Species Editor - {SPECIES.title()}")
        self.minsize(1150, 760)

        self.cache = ImageCache()
        # species palettes
        self.palettes = []          # [{"body": {key: hex}, "eye": {key: hex}}]
        self.saved_palettes = []
        self.species_mtime = None
        self.selected = 0
        self.swatch_photos = []
        # clothing
        self.items = []
        self.cl_item = None         # ClothingItem being edited
        self.cl_selected = 0        # option index being edited
        self.cl_photos = []
        self.cl_sync = {}           # frozenset(paths) -> BooleanVar
        self._checks_dirty = True
        # preview
        self.anim_frame = 0
        self.emote_frame = 0
        self.preview_photo = None
        self.hair_options = {}
        self.marking_options = {}
        self._checker_cache = None

        self._build_ui()
        self._load_offsets()
        self.load_from_disk(initial=True)
        self.load_items()

        self.bind_all("<Control-s>", lambda e: self.save())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self._anim_tick)
        self.after(150, self._emote_tick)
        self.after(500, self._poll)
        self._lock_window_size()

    def _lock_window_size(self):
        """Give the window an explicit size once laid out. After that Tk never resizes it to fit content
        (changing labels, long item names, status messages) - only the user can, by dragging."""
        self.update_idletasks()
        w = min(max(self.winfo_reqwidth(), 1150), self.winfo_screenwidth() - 40)
        h = min(max(self.winfo_reqheight(), 760), self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}")

    # ================================================================== UI
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
        root.rowconfigure(0, weight=1)

        # ---------------- left: preview + controls
        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        # A Canvas doesn't resize to its content, so zooming never changes the window size.
        self.preview_canvas = tk.Canvas(left, width=560, height=420, bg="#282A36", bd=1,
                                        relief="sunken", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", lambda e: self.render())

        ctrl = ttk.LabelFrame(left, text="Preview", padding=6)
        ctrl.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for c in (1, 3, 5):
            ctrl.columnconfigure(c, weight=1)

        self.gender = tk.StringVar(value="male")
        self.state_var = tk.StringVar(value="Idle")
        self.personality = tk.StringVar(value=PERSONALITIES[0][0])
        self.hair_var = tk.StringVar()
        self.marking_var = tk.StringVar(value=NONE)
        self.emote_var = tk.StringVar(value="Idle")
        self.eye_var = tk.StringVar(value="Same as fur palette")
        self.hair_color_var = tk.StringVar(value="Same as fur palette")
        self.bg_var = tk.StringVar(value="Dark")
        self.zoom = tk.IntVar(value=8)
        self.playing = tk.BooleanVar(value=True)
        self.emote_playing = tk.BooleanVar(value=True)
        self.show_arms = tk.BooleanVar(value=True)
        self.color_hair = tk.BooleanVar(value=True)
        self.face_left = tk.BooleanVar(value=False)
        self.clothing_only = tk.BooleanVar(value=False)
        self.frame_var = tk.IntVar(value=1)
        self.shirt_var = tk.StringVar(value=NONE)
        self.shirt_color = tk.StringVar()
        self.pants_var = tk.StringVar(value=NONE)
        self.pants_color = tk.StringVar()

        def combo(row, col, label, var, values=(), width=14, cmd=None, padx=(10, 0)):
            ttk.Label(ctrl, text=label).grid(row=row, column=col, sticky="w", padx=padx, pady=(6, 0))
            cb = ttk.Combobox(ctrl, textvariable=var, values=list(values), state="readonly", width=width)
            cb.grid(row=row, column=col + 1, sticky="ew", pady=(6, 0))
            cb.bind("<<ComboboxSelected>>", lambda e: (cmd or self.render)())
            return cb

        r = 0
        ttk.Label(ctrl, text="Gender").grid(row=r, column=0, sticky="w")
        gf = ttk.Frame(ctrl)
        gf.grid(row=r, column=1, sticky="w")
        for g in ("male", "female"):
            ttk.Radiobutton(gf, text=g.title(), value=g, variable=self.gender,
                            command=self._gender_changed).pack(side="left", padx=(0, 6))
        combo(r, 2, "Pose", self.state_var, STATES, cmd=self._state_changed)
        combo(r, 4, "Personality", self.personality, [p[0] for p in PERSONALITIES])

        r += 1
        ttk.Label(ctrl, text="Frame").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ff = ttk.Frame(ctrl)
        ff.grid(row=r, column=1, columnspan=3, sticky="ew", pady=(6, 0))
        ff.columnconfigure(1, weight=1)
        ttk.Button(ff, text="<", width=2, command=lambda: self.step_frame(-1)).grid(row=0, column=0)
        self.frame_scale = tk.Scale(ff, from_=1, to=1, orient="horizontal", variable=self.frame_var,
                                    showvalue=True, command=lambda v: self._frame_scrubbed())
        self.frame_scale.grid(row=0, column=1, sticky="ew")
        ttk.Button(ff, text=">", width=2, command=lambda: self.step_frame(1)).grid(row=0, column=2)
        ttk.Checkbutton(ff, text="Animate", variable=self.playing).grid(row=0, column=3, padx=6)
        self.frame_name_label = ttk.Label(ctrl, text="", foreground="#666", wraplength=330, width=48)
        self.frame_name_label.grid(row=r, column=4, columnspan=2, sticky="w", padx=(10, 0), pady=(6, 0))

        r += 1
        self.hair_cb = combo(r, 0, "Hair", self.hair_var, width=26, padx=(0, 0))
        self.marking_cb = combo(r, 2, "Markings", self.marking_var)
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
        self.shirt_cb = combo(r, 0, "Shirt", self.shirt_var, width=26, padx=(0, 0),
                              cmd=lambda: self._preview_item_changed("chest"))
        self.shirt_color_cb = combo(r, 2, "Shirt color", self.shirt_color)
        ttk.Checkbutton(ctrl, text="Clothing only (hide character)", variable=self.clothing_only,
                        command=self.render).grid(row=r, column=4, columnspan=2, sticky="w", padx=(10, 0),
                                                  pady=(6, 0))
        r += 1
        self.pants_cb = combo(r, 0, "Pants", self.pants_var, width=26, padx=(0, 0),
                              cmd=lambda: self._preview_item_changed("legs"))
        self.pants_color_cb = combo(r, 2, "Pants color", self.pants_color)
        ttk.Button(ctrl, text="Undress", command=self.undress).grid(row=r, column=4, sticky="w",
                                                                    padx=(10, 0), pady=(6, 0))

        r += 1
        self.eye_cb = combo(r, 0, "Eyes", self.eye_var, width=26, padx=(0, 0))
        self.hair_color_cb = combo(r, 2, "Hair color", self.hair_color_var)
        r += 1
        combo(r, 0, "Background", self.bg_var, BACKGROUNDS, width=10, padx=(0, 0))
        # Per-species clothing offset (preview/export only): for species whose body sits lower in the
        # frame than the standard humanoid (e.g. Verinians), so vanilla and mod outfits line up.
        ttk.Label(ctrl, text="Zoom").grid(row=r, column=4, sticky="w", padx=(10, 0), pady=(6, 0))
        tk.Scale(ctrl, from_=2, to=14, orient="horizontal", variable=self.zoom, showvalue=True,
                 command=lambda v: self.render()).grid(row=r, column=5, sticky="ew")

        r += 1
        ttk.Label(ctrl, text="Clothing offset\n(px down, this species)").grid(row=r, column=0, sticky="w",
                                                                           pady=(6, 0))
        of = ttk.Frame(ctrl)
        of.grid(row=r, column=1, columnspan=5, sticky="w", pady=(6, 0))
        self.offset_vars = {}
        for key, label in OFFSET_FIELDS:
            var = tk.IntVar(value=0)
            self.offset_vars[key] = var
            ttk.Label(of, text=label).pack(side="left")
            lo = 0 if key in SHRINK_FIELDS else -10
            sp = ttk.Spinbox(of, from_=lo, to=10, width=3, textvariable=var, command=self._offsets_changed)
            sp.pack(side="left", padx=(2, 8))
            sp.bind("<Return>", lambda e: self._offsets_changed())
            sp.bind("<FocusOut>", lambda e: self._offsets_changed())

        r += 1
        tf = ttk.Frame(ctrl)
        tf.grid(row=r, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Checkbutton(tf, text="Show arms", variable=self.show_arms, command=self.render).pack(side="left")
        self.color_hair_check = ttk.Checkbutton(tf, text="Apply palette to hair & markings",
                                                variable=self.color_hair, command=self.render)
        self.color_hair_check.pack(side="left", padx=12)
        ttk.Checkbutton(tf, text="Face left", variable=self.face_left, command=self.render).pack(side="left")
        ttk.Button(ctrl, text="Export image…", command=self.export_image).grid(
            row=r, column=5, sticky="e", pady=(6, 0))

        # ---------------- right: tabs + save bar
        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="ns")
        right.rowconfigure(1, weight=1)
        spf = ttk.Frame(right)
        spf.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(spf, text="Species", font=("TkDefaultFont", 10, "bold")).pack(side="left")
        self.species_var = tk.StringVar(value=SPECIES)
        self.species_cb = ttk.Combobox(spf, textvariable=self.species_var, values=available_species(),
                                       state="readonly", width=16)
        self.species_cb.pack(side="left", padx=(8, 0))
        self.species_cb.bind("<<ComboboxSelected>>", lambda e: self.switch_species(self.species_var.get()))
        self.tabs = ttk.Notebook(right)
        self.tabs.grid(row=1, column=0, sticky="nsew")
        fur_tab = ttk.Frame(self.tabs, padding=6)
        cl_tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(fur_tab, text="Palettes")
        self.tabs.add(cl_tab, text="Clothing")
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        self._build_fur_tab(fur_tab)
        self._build_clothing_tab(cl_tab)

        sf = ttk.Frame(right)
        sf.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        sf.columnconfigure(0, weight=1)
        self.dirty_label = ttk.Label(sf, text="", style="Dirty.TLabel", wraplength=250, width=30)
        self.dirty_label.grid(row=0, column=0, sticky="w")
        ttk.Button(sf, text="Revert", command=self.revert).grid(row=0, column=1, padx=4)
        ttk.Button(sf, text="Save  (Ctrl+S)", command=self.save).grid(row=0, column=2)

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=(6, 2), width=1).pack(
            fill="x", side="bottom")

    def _build_fur_tab(self, tab):
        tab.rowconfigure(0, weight=1)
        lf = ttk.LabelFrame(tab, text="Palettes (in-game order)", padding=6)
        lf.grid(row=0, column=0, sticky="nsew")
        lf.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(lf, show="tree", style="Palette.Treeview", height=9, selectmode="browse")
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
        ttk.Button(bf, text="New (base)", command=lambda: self.add_palette(base=True)).grid(
            row=0, column=1, sticky="ew", padx=3)
        ttk.Button(bf, text="Delete", command=self.delete_palette).grid(row=0, column=2, sticky="ew")
        ttk.Button(bf, text="Move up", command=lambda: self.move_palette(-1)).grid(
            row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Button(bf, text="Move down", command=lambda: self.move_palette(1)).grid(
            row=1, column=1, sticky="ew", padx=3, pady=(3, 0))

        ed = ttk.LabelFrame(tab, text="Colors", padding=6)
        ed.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.editor_title = ttk.Label(ed, text="", font=("TkDefaultFont", 9, "bold"), width=24)
        self.editor_title.grid(row=0, column=0, sticky="w")
        # scrollable: species with many keys (Verinian has fur + eyes + hair) would push the window taller
        holder = ttk.Frame(ed)
        holder.grid(row=1, column=0, sticky="ew")
        self.rows_canvas, rows_frame = self._scroll_area(holder, height=330, width=290)
        self.fur_rows = ColorRows(self, rows_frame, self.pick_color, self.hex_entered)
        self._build_color_rows()

    def _scroll_area(self, holder, height, width):
        """A fixed-size, vertically scrolling area inside `holder`. Returns (canvas, inner frame)."""
        canvas = tk.Canvas(holder, height=height, width=width, highlightthickness=0, bd=0,
                           background=self.cget("bg"))
        sb = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Enter>", lambda e: canvas.bind_all(
            "<MouseWheel>", lambda ev: canvas.yview_scroll(-1 * (ev.delta // 120), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return canvas, inner

    def _palette_groups(self):
        """(group, keys, title) for the current species; 'hair' only when it has its own hairColor list."""
        groups = [("body", BODY_KEYS, "Fur (bodyColor)"), ("eye", EYE_KEYS, "Eyes (undyColor)")]
        if HAIR_KEYS:
            groups.append(("hair", HAIR_KEYS, "Hair (hairColor)"))
        return groups

    def _build_color_rows(self):
        self.fur_rows.clear()
        for group, keys, title in self._palette_groups():
            self.fur_rows.header(title)
            for key, desc in keys:
                self.fur_rows.add((group, key), key, desc)
        self.rows_canvas.yview_moveto(0)

    def _build_clothing_tab(self, tab):
        tab.columnconfigure(0, weight=1)
        top = ttk.LabelFrame(tab, text="Items (double-click to wear / take off)", padding=6)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self.cl_list = ttk.Treeview(top, columns=("worn",), style="Palette.Treeview", height=7,
                                    selectmode="browse")
        self.cl_list.column("#0", width=230)
        self.cl_list.column("worn", width=70, anchor="center")
        self.cl_list.heading("#0", text="Item")
        self.cl_list.heading("worn", text="Wearing")
        self.cl_list.grid(row=0, column=0, sticky="ew")
        lsb = ttk.Scrollbar(top, orient="vertical", command=self.cl_list.yview)
        lsb.grid(row=0, column=1, sticky="ns")
        self.cl_list.configure(yscrollcommand=lsb.set)
        self.cl_list.bind("<<TreeviewSelect>>", lambda e: self._cl_list_selected())
        self.cl_list.bind("<Double-1>", self._cl_list_double)
        wb = ttk.Frame(top)
        wb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        for i in range(3):
            wb.columnconfigure(i, weight=1)
        self.wear_btn = ttk.Button(wb, text="Wear", command=self.cl_toggle_wear)
        self.wear_btn.grid(row=0, column=0, sticky="ew")
        ttk.Button(wb, text="Wear whole outfit", command=self.cl_wear_outfit).grid(
            row=0, column=1, sticky="ew", padx=3)
        ttk.Button(wb, text="Undress", command=self.undress).grid(row=0, column=2, sticky="ew")
        self.cl_sync_check = ttk.Checkbutton(top, text="Keep chest & legs color options identical", width=44)
        self.cl_sync_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.cl_icons = {}

        lf = ttk.LabelFrame(tab, text="Color options (index = in-game color)", padding=6)
        lf.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        lf.columnconfigure(0, weight=1)
        self.cl_tree = ttk.Treeview(lf, show="tree", style="Palette.Treeview", height=7, selectmode="browse")
        self.cl_tree.column("#0", width=250)
        self.cl_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.cl_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.cl_tree.configure(yscrollcommand=sb.set)
        self.cl_tree.bind("<<TreeviewSelect>>", lambda e: self._cl_option_selected())
        bf = ttk.Frame(lf)
        bf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for i in range(4):
            bf.columnconfigure(i, weight=1)
        ttk.Button(bf, text="Duplicate", command=self.cl_add).grid(row=0, column=0, sticky="ew")
        ttk.Button(bf, text="Delete", command=self.cl_delete).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(bf, text="Up", command=lambda: self.cl_move(-1)).grid(row=0, column=2, sticky="ew")
        ttk.Button(bf, text="Down", command=lambda: self.cl_move(1)).grid(row=0, column=3, sticky="ew", padx=(3, 0))

        ed = ttk.LabelFrame(tab, text="Option", padding=6)
        ed.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ed.columnconfigure(1, weight=1)
        ttk.Label(ed, text="Name").grid(row=0, column=0, sticky="w")
        self.cl_name_var = tk.StringVar()
        ne = ttk.Entry(ed, textvariable=self.cl_name_var)
        ne.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ne.bind("<Return>", lambda e: self.cl_rename())
        ne.bind("<FocusOut>", lambda e: self.cl_rename())
        # fixed height + scroll: items have anything from 3 to 14+ color keys, and the panel must not grow
        holder = ttk.Frame(ed)
        holder.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.cl_rows_canvas, rows_frame = self._scroll_area(holder, height=170, width=290)
        self.cl_rows = ColorRows(self, rows_frame, self.cl_pick, self.cl_hex)

        ck = ttk.LabelFrame(tab, text="Sprite checks", padding=6)
        ck.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        ck.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)
        self.cl_checks = tk.Text(ck, height=9, width=46, wrap="word", font=("Segoe UI", 9),
                                 relief="flat", background=self.cget("bg"))
        self.cl_checks.grid(row=0, column=0, sticky="nsew")
        csb = ttk.Scrollbar(ck, orient="vertical", command=self.cl_checks.yview)
        csb.grid(row=0, column=1, sticky="ns")
        self.cl_checks.configure(yscrollcommand=csb.set, state="disabled")
        for lvl, color in (("error", "#C0392B"), ("warn", "#B9770E"), ("info", "#555555"), ("ok", "#1E8449")):
            self.cl_checks.tag_configure(lvl, foreground=color)
        cbf = ttk.Frame(ck)
        cbf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.fix_case_btn = ttk.Button(cbf, text="Fix file-name case", command=self.cl_fix_case, state="disabled")
        self.fix_case_btn.pack(side="left")
        ttk.Button(cbf, text="Check all items", command=self.cl_check_all).pack(side="left", padx=4)

    def status(self, msg):
        self.status_var.set(msg)

    def _tab_changed(self):
        if self.tabs.index("current") == 1 and self.cl_item is not None:
            self._run_checks()

    # ================================================================== species loading
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
        self.species_mtime = SPECIES_FILE.stat().st_mtime_ns
        lists = {"body": data.get("bodyColor", []), "eye": data.get("undyColor", [])}
        if HAIR_KEYS:
            # hairColor entries can be "" (no recolor) in the vanilla style; treat those as identity
            lists["hair"] = [h if isinstance(h, dict) else {} for h in data.get("hairColor", [])]
        pals = []
        for i in range(max(len(v) for v in lists.values())):
            pal = {}
            for group, keys, _title in self._palette_groups():
                src = lists[group]
                d = dict(src[i]) if i < len(src) else {}
                for k, _ in keys:
                    d[k] = (norm_hex(str(d.get(k, d.get(k.lower(), k)))) or k)
                # drop lowercase duplicates of the keys we normalised
                pal[group] = {k: v for k, v in d.items() if k.upper() == k or k.upper() not in d}
            pals.append(pal)
        self.palettes = pals
        self.saved_palettes = copy.deepcopy(pals)
        self.selected = min(self.selected, max(0, len(pals) - 1))
        self.status(f"Loaded {len(self.palettes)} palettes from {SPECIES_FILE.name}.")
        self.refresh_palette_list()
        self.refresh_part_lists()
        self._state_changed()

    # ---- per-species clothing offsets (preview/export only)
    def _all_offsets(self):
        data = {k: dict(v) for k, v in DEFAULT_OFFSETS.items()}
        try:
            for k, v in json.loads(OFFSETS_FILE.read_text(encoding="utf-8")).items():
                data.setdefault(k, {}).update(v)
        except (OSError, ValueError):
            pass
        return data

    def _load_offsets(self):
        o = self._all_offsets().get(SPECIES, {})
        for key, var in self.offset_vars.items():
            var.set(int(o.get(key, 0)))

    def _offsets_changed(self):
        cur = self._clothing_offsets()
        data = self._all_offsets()
        if data.get(SPECIES, {}) != cur:
            data[SPECIES] = cur
            try:
                OFFSETS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            except OSError as ex:
                self.status(f"Couldn't save clothing offsets: {ex}")
        self.render()

    def _clothing_offsets(self):
        out = {}
        for key, var in self.offset_vars.items():
            try:
                out[key] = int(var.get())
            except (tk.TclError, ValueError):
                out[key] = 0
        for key in SHRINK_FIELDS:
            out[key] = max(0, out.get(key, 0))
        return out

    def switch_species(self, name):
        """Swap the whole palette side of the editor to another species (clothing edits are kept)."""
        if name == SPECIES:
            return
        if self.species_dirty():
            ans = messagebox.askyesnocancel(
                "Unsaved palettes", f"Save your {SPECIES} palette changes before switching to {name}?")
            if ans is None or (ans and self._save_species() is None):
                self.species_var.set(SPECIES)
                return
        try:
            set_species(name)
        except Exception as ex:
            messagebox.showerror("Species", str(ex))
            self.species_var.set(SPECIES)
            return
        self.selected = 0
        self.eye_var.set("Same as fur palette")
        self.hair_color_var.set("Same as fur palette")
        self.hair_options, self.marking_options = {}, {}
        self._build_color_rows()
        self._load_offsets()
        self.load_from_disk()
        self.update_dirty()
        self.render()

    # ================================================================== parts lists
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
        mopts = {NONE: None}
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
            self.marking_var.set(NONE)

    def _gender_changed(self):
        self.refresh_part_lists()
        self._checks_dirty = True
        self.render()

    # ================================================================== species palettes
    def _pal_strip(self, pal):
        return swatch_strip([[pal[g][k] for k, _ in keys] for g, keys, _t in self._palette_groups()], size=11, gap=5)

    def refresh_palette_list(self):
        self.tree.delete(*self.tree.get_children())
        self.swatch_photos = []
        for i, pal in enumerate(self.palettes):
            ph = self._pal_strip(pal)
            self.swatch_photos.append(ph)
            mark = " *" if i >= len(self.saved_palettes) or pal != self.saved_palettes[i] else ""
            self.tree.insert("", "end", iid=str(i), text=f" {i}{mark}", image=ph)
        if self.palettes:
            self.selected = max(0, min(self.selected, len(self.palettes) - 1))
            self.tree.selection_set(str(self.selected))
            self.tree.see(str(self.selected))
        choices = ["Same as fur palette"] + [f"Palette {i}" for i in range(len(self.palettes))]
        for cb, var in ((self.eye_cb, self.eye_var), (self.hair_color_cb, self.hair_color_var)):
            cb["values"] = choices
            if var.get() not in choices:
                var.set("Same as fur palette")
        self.hair_color_cb.configure(state="readonly" if HAIR_KEYS else "disabled")
        # species with their own hair colors don't tint hair with the fur palette
        self.color_hair_check.configure(state="disabled" if HAIR_KEYS else "normal")
        self.refresh_editor()
        self.update_dirty()

    def _update_row(self, i):
        ph = self._pal_strip(self.palettes[i])
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
        for (g, k) in self.fur_rows.widgets:
            self.fur_rows.set((g, k), pal[g][k])

    def set_color(self, group, key, hexv):
        pal = self.palettes[self.selected]
        if pal[group][key] == hexv:
            return
        pal[group][key] = hexv
        self._update_row(self.selected)
        self.refresh_editor()
        self.update_dirty()
        self.render()

    def pick_color(self, ident):
        if not self.palettes:
            return
        group, key = ident
        cur = self.palettes[self.selected][group][key]
        res = colorchooser.askcolor(color="#" + cur, title=f"Palette {self.selected}: {key}", parent=self)
        if res and res[1]:
            self.set_color(group, key, norm_hex(res[1]))

    def hex_entered(self, ident):
        if not self.palettes:
            return
        group, key = ident
        h = norm_hex(self.fur_rows.get_text(ident))
        if h is None:
            self.bell()
            self.status(f"'{self.fur_rows.get_text(ident)}' isn't a hex color (use RRGGBB).")
            self.fur_rows.set(ident, self.palettes[self.selected][group][key])
            return
        self.set_color(group, key, h)

    def add_palette(self, base=False):
        if base or not self.palettes:
            pal = {g: {k: k for k, _ in keys} for g, keys, _t in self._palette_groups()}
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

    # ================================================================== clothing
    def load_items(self, keep=None):
        keep = keep or (self.cl_item.path if self.cl_item else None)
        self.items = sc.find_items(MOD_DIR)
        if VANILLA_DIR.is_dir():
            # vanilla shirts/pants (what character creation offers), read-only, from the unpacked assets
            self.items += sc.find_items(VANILLA_DIR, kinds={"chest", "legs"}, readonly=True, source="vanilla")
        # chest/legs pairs living in the same folder get a "keep identical" toggle (editable items only)
        self.cl_sync = {}
        by_dir = {}
        for it in self.items:
            if not it.readonly:
                by_dir.setdefault(it.path.parent, []).append(it)
        for group in by_dir.values():
            chests = [i for i in group if i.kind == "chest"]
            legs = [i for i in group if i.kind == "legs"]
            if len(chests) == 1 and len(legs) == 1:
                key = frozenset((chests[0].path, legs[0].path))
                self.cl_sync[key] = tk.BooleanVar(value=chests[0].options == legs[0].options)
        chest_labels = [NONE] + [it.label for it in self.items if it.kind == "chest"]
        legs_labels = [NONE] + [it.label for it in self.items if it.kind == "legs"]
        self.shirt_cb["values"] = chest_labels
        self.pants_cb["values"] = legs_labels
        if self.shirt_var.get() not in chest_labels:
            self.shirt_var.set(NONE)
        if self.pants_var.get() not in legs_labels:
            self.pants_var.set(NONE)
        self._fill_item_list()
        target = next((it for it in self.items if it.path == keep), None) if keep else None
        self.cl_item = None
        if target:
            self.cl_list.selection_set(self._iid(target))
            self.cl_list.see(self._iid(target))
            self._select_item(target)
        self._refresh_preview_color_lists()
        self.update_dirty()

    # ---- item list
    def _iid(self, item):
        return f"item:{self.items.index(item)}"

    def _item_icon(self, item):
        """16x16 inventory icon (from e.g. 'icons.png:chest'), or None."""
        icon = item.data.get("inventoryIcon")
        if not isinstance(icon, str):
            return None
        wanted = sc.resolve_ref(item.mod_dir, item.path.parent, icon)
        disk, _exact = sc.exact_or_case_match(wanted)
        img = self.cache.get(disk) if disk else None
        if img is None:
            return None
        frame = icon.split(":", 1)[1].split("?")[0] if ":" in icon else None
        if frame:
            boxes, _ = sc.find_frames(item.mod_dir, wanted)
            box = (boxes or sc.parse_frames(sc._ICONS)).get(frame)
            if box and box[2] <= img.width and box[3] <= img.height:
                img = img.crop(box)
        img = img.copy()
        img.thumbnail((16, 16), Image.NEAREST)
        return ImageTk.PhotoImage(img)

    def _fill_item_list(self):
        sel = self.cl_list.selection()
        self.cl_list.delete(*self.cl_list.get_children())
        self.cl_icons = {}
        folders = {}
        for it in self.items:
            folders.setdefault((it.source, it.path.parent), []).append(it)
        order = {"head": 0, "chest": 1, "legs": 2, "back": 3}
        sources = {}
        for (source, folder), its in folders.items():
            if source not in sources:
                sid = f"src:{source}"
                title = " Mod outfits" if source == "mod" else f" {source.title()} outfits (read-only)"
                self.cl_list.insert("", "end", iid=sid, text=title, open=(source == "mod"))
                sources[source] = sid
            fid = f"dir:{folder}"
            self.cl_list.insert(sources[source], "end", iid=fid, text=f" {folder.name}", open=(source == "mod"))
            for it in sorted(its, key=lambda i: order.get(i.kind, 9)):
                ph = self._item_icon(it)
                iid = self._iid(it)
                if ph:
                    self.cl_icons[iid] = ph
                self.cl_list.insert(fid, "end", iid=iid,
                                    text=f" {it.data.get('shortdescription', it.item_name)}  ({it.kind})",
                                    **({"image": ph} if ph else {}))
        if sel and self.cl_list.exists(sel[0]):
            self.cl_list.selection_set(sel[0])
        self.refresh_worn_marks()

    def _worn_items(self):
        return [i for i in (self._item_by_label(self.shirt_var.get()), self._item_by_label(self.pants_var.get()))
                if i is not None]

    def refresh_worn_marks(self):
        worn = self._worn_items()
        for it in self.items:
            iid = self._iid(it)
            if self.cl_list.exists(iid):
                self.cl_list.set(iid, "worn", "✔ wearing" if it in worn else "")
        if self.cl_item is not None:
            self.wear_btn.configure(text="Take off" if self.cl_item in worn else "Wear")

    def _row_item(self, iid):
        if iid and iid.startswith("item:"):
            return self.items[int(iid.split(":")[1])]
        return None

    def _cl_list_selected(self):
        sel = self.cl_list.selection()
        if not sel:
            return
        item = self._row_item(sel[0])
        if item is None:  # folder row -> edit its first item
            kids = self.cl_list.get_children(sel[0])
            item = self._row_item(kids[0]) if kids else None
        if item is not None and item is not self.cl_item:
            self._select_item(item)

    def _cl_list_double(self, event):
        iid = self.cl_list.identify_row(event.y)
        if not iid:
            return "break"
        item = self._row_item(iid)
        if item is None:
            self.cl_wear_outfit(folder_iid=iid)
        else:
            self._set_worn(item, item not in self._worn_items())
        return "break"  # don't collapse/expand folders on double-click

    def _set_worn(self, item, wear, option_index=None):
        if item.kind not in ("chest", "legs"):
            self.status(f"Previewing {item.kind} items isn't supported yet.")
            return
        var = self.shirt_var if item.kind == "chest" else self.pants_var
        cvar = self.shirt_color if item.kind == "chest" else self.pants_color
        cb = self.shirt_color_cb if item.kind == "chest" else self.pants_color_cb
        if wear:
            if var.get() != item.label:
                var.set(item.label)
                cvar.set("")
            self._refresh_preview_color_lists()
            if option_index is not None:
                vals = list(cb["values"])
                if option_index < len(vals):
                    cvar.set(vals[option_index])
        elif var.get() == item.label:
            var.set(NONE)
            self._refresh_preview_color_lists()
        self.refresh_worn_marks()
        self.render()

    def cl_toggle_wear(self):
        if self.cl_item is not None:
            self._set_worn(self.cl_item, self.cl_item not in self._worn_items(),
                           option_index=self.cl_selected)

    def cl_wear_outfit(self, folder_iid=None):
        if folder_iid is None:
            if self.cl_item is None:
                return
            folder_iid = f"dir:{self.cl_item.path.parent}"
        partner, sync = self._partner(self.cl_item) if self.cl_item is not None else (None, None)
        linked = partner if (sync is not None and sync.get()) else None
        for kid in self.cl_list.get_children(folder_iid):
            it = self._row_item(kid)
            if it is not None and it.kind in ("chest", "legs"):
                # the item being edited (and its linked partner) use the color option being edited
                idx = self.cl_selected if it is self.cl_item or it is linked else None
                self._set_worn(it, True, option_index=idx)

    def undress(self):
        self.shirt_var.set(NONE)
        self.pants_var.set(NONE)
        self._refresh_preview_color_lists()
        self.refresh_worn_marks()
        self.render()

    def _item_by_label(self, label):
        return next((it for it in self.items if it.label == label), None)

    def _partner(self, item):
        for key, var in self.cl_sync.items():
            if item.path in key:
                other = next(p for p in key if p != item.path) if len(key) > 1 else None
                return next((i for i in self.items if i.path == other), None), var
        return None, None

    def _select_item(self, item):
        """Open an item for editing. Doesn't change what the character is wearing."""
        self.cl_item = item
        worn_cb = {"chest": (self.shirt_var, self.shirt_color_cb, self.shirt_color),
                   "legs": (self.pants_var, self.pants_color_cb, self.pants_color)}.get(item.kind)
        # start on the color that's being previewed, if it's worn
        self.cl_selected = 0
        if worn_cb and worn_cb[0].get() == item.label:
            vals = list(worn_cb[1]["values"])
            if worn_cb[2].get() in vals:
                self.cl_selected = vals.index(worn_cb[2].get())
        partner, var = self._partner(item)
        if var is not None:
            self.cl_sync_check.configure(variable=var, state="normal",
                                         text=f"Keep color options identical with "
                                              f"{partner.data.get('shortdescription', '')} ({partner.kind})")
        else:
            self.cl_sync_check.configure(state="disabled", text="Keep chest & legs color options identical")
        self.refresh_cl_options()
        self.refresh_worn_marks()
        self._checks_dirty = True
        self._run_checks()

    def refresh_cl_options(self):
        item = self.cl_item
        self.cl_tree.delete(*self.cl_tree.get_children())
        self.cl_photos = []
        if item is None:
            return
        keys = item.color_keys()
        for i, opt in enumerate(item.options):
            cols = [norm_hex(opt["colors"].get(k, k)) or "000000" for k in keys]
            ph = swatch_strip([cols]) if cols else None
            self.cl_photos.append(ph)
            saved = item.saved_options[i] if i < len(item.saved_options) else None
            mark = " *" if opt != saved else ""
            self.cl_tree.insert("", "end", iid=str(i), text=f" {i}  {opt.get('name') or ''}{mark}",
                                **({"image": ph} if ph else {}))
        if item.options:
            self.cl_selected = max(0, min(self.cl_selected, len(item.options) - 1))
            # programmatic selection fires <<TreeviewSelect>> later; ignore it (it's not a user click)
            self._ignore_opt_select = getattr(self, "_ignore_opt_select", 0) + 1
            self.cl_tree.selection_set(str(self.cl_selected))
            self.cl_tree.see(str(self.cl_selected))
            self.after_idle(self._unignore_opt_select)
        self._refresh_cl_editor()

    def _unignore_opt_select(self):
        self._ignore_opt_select = max(0, getattr(self, "_ignore_opt_select", 1) - 1)

    def _refresh_cl_editor(self):
        item = self.cl_item
        self.cl_rows.clear()
        self.cl_rows_canvas.yview_moveto(0)
        if item is None or not item.options:
            self.cl_name_var.set("")
            return
        opt = item.options[self.cl_selected]
        self.cl_name_var.set(opt.get("name", ""))
        if "raw" in opt:
            ttk.Label(self.cl_rows.parent, text=f"Directive string option (not editable here):\n{opt['raw']}",
                      wraplength=280).grid(row=0, column=0, columnspan=4, sticky="w")
            return
        for k in item.color_keys():
            base = norm_hex(k) or "000000"
            self.cl_rows.add(k, base, f"#{base}")
            self.cl_rows.set(k, norm_hex(opt["colors"].get(k, k)) or base)

    def _cl_option_selected(self):
        sel = self.cl_tree.selection()
        if not sel or self.cl_item is None or getattr(self, "_ignore_opt_select", 0):
            return
        idx = int(sel[0])
        changed = idx != self.cl_selected
        self.cl_selected = idx
        if changed:
            self._refresh_cl_editor()
        # picking a color previews it: put the item on (if it isn't already) in that color
        self._set_worn(self.cl_item, True, option_index=idx)
        # a linked partner that's being worn follows the same color index
        partner, sync = self._partner(self.cl_item)
        if partner is not None and sync is not None and sync.get() and partner in self._worn_items():
            self._set_worn(partner, True, option_index=idx)

    def _cl_changed(self, structure=False):
        """Called after editing self.cl_item.options; mirrors to the partner if synced."""
        item = self.cl_item
        partner, sync = self._partner(item)
        if partner is not None and sync is not None and sync.get():
            partner.options = copy.deepcopy(item.options)
        if structure:
            self.refresh_cl_options()
        else:
            self.refresh_cl_options()
        self._refresh_preview_color_lists()
        self.update_dirty()
        self.render()

    def cl_pick(self, key):
        if self._readonly_item():
            return
        opt = self.cl_item.options[self.cl_selected]
        cur = norm_hex(opt["colors"].get(key, key)) or "000000"
        res = colorchooser.askcolor(color="#" + cur, title=f"{opt.get('name', '')}: {key}", parent=self)
        if res and res[1]:
            self._cl_set(key, norm_hex(res[1]))

    def cl_hex(self, key):
        if self.cl_item is None or not self.cl_item.options:
            return
        h = norm_hex(self.cl_rows.get_text(key))
        opt = self.cl_item.options[self.cl_selected]
        if h is None:
            self.bell()
            self.status(f"'{self.cl_rows.get_text(key)}' isn't a hex color (use RRGGBB).")
            self.cl_rows.set(key, norm_hex(opt["colors"].get(key, key)) or "000000")
            return
        self._cl_set(key, h)

    def _cl_set(self, key, hexv):
        if self._readonly_item():
            return
        opt = self.cl_item.options[self.cl_selected]
        old = opt["colors"].get(key, key)
        if (norm_hex(old) or "") == hexv:
            return
        # keep the file's style: lowercase like the existing values
        opt["colors"][key] = hexv.lower() if old == old.lower() else hexv
        self._cl_changed()
        self._set_worn(self.cl_item, True, option_index=self.cl_selected)  # show what's being edited

    def cl_rename(self):
        if self.cl_item is None or not self.cl_item.options:
            return
        if self.cl_item.readonly:
            self.cl_name_var.set(self.cl_item.options[self.cl_selected].get("name", ""))
            return
        name = self.cl_name_var.get().strip().replace("\n", " ")
        opt = self.cl_item.options[self.cl_selected]
        if opt.get("name", "") != name:
            opt["name"] = name
            self._cl_changed()

    def cl_add(self):
        if self._readonly_item():
            return
        if self.cl_item is None:
            return
        if self.cl_item.options:
            new = copy.deepcopy(self.cl_item.options[self.cl_selected])
            new["name"] = (new.get("name") or "OPTION") + " COPY"
        else:
            new = {"name": "DEFAULT", "colors": {}}
        self.cl_item.options.append(new)
        self.cl_selected = len(self.cl_item.options) - 1
        self._cl_changed(structure=True)

    def cl_delete(self):
        if self._readonly_item():
            return
        if self.cl_item is None or not self.cl_item.options:
            return
        opt = self.cl_item.options[self.cl_selected]
        if not messagebox.askyesno("Delete color option",
                                   f"Delete option {self.cl_selected} ({opt.get('name', '')})?\n"
                                   "(Nothing is written until you Save.)"):
            return
        del self.cl_item.options[self.cl_selected]
        self.cl_selected = max(0, self.cl_selected - 1)
        self._cl_changed(structure=True)

    def cl_move(self, d):
        if self._readonly_item():
            return
        if self.cl_item is None:
            return
        o = self.cl_item.options
        j = self.cl_selected + d
        if 0 <= j < len(o):
            o[self.cl_selected], o[j] = o[j], o[self.cl_selected]
            self.cl_selected = j
            self._cl_changed(structure=True)

    def _readonly_item(self):
        """True (and says so) when the edited item is a read-only vanilla item."""
        if self.cl_item is not None and self.cl_item.readonly:
            self.bell()
            self.status(f"{self.cl_item.path.name} is a {self.cl_item.source} item: preview and export only, "
                        "its color options can't be edited here.")
            if self.cl_item.options:
                self._refresh_cl_editor()
            return True
        return False

    def _option_labels(self, item):
        return [f"{i}  {o.get('name') or ''}".rstrip() for i, o in enumerate(item.options)] if item else []

    def _refresh_preview_color_lists(self):
        for item_var, cb, var in ((self.shirt_var, self.shirt_color_cb, self.shirt_color),
                                  (self.pants_var, self.pants_color_cb, self.pants_color)):
            item = self._item_by_label(item_var.get())
            labels = self._option_labels(item)
            old = list(cb["values"])
            idx = old.index(var.get()) if var.get() in old else 0
            cb["values"] = labels
            var.set(labels[min(idx, len(labels) - 1)] if labels else "")

    def _preview_item_changed(self, kind):
        var = self.shirt_color if kind == "chest" else self.pants_color
        var.set("")
        self._refresh_preview_color_lists()
        self.refresh_worn_marks()
        self.render()

    def _run_checks(self):
        item = self.cl_item
        if item is None:
            return
        arms = {"frontSleeve": self.cache.get(HUMANOID_DIR / "frontarm.png"),
                "backSleeve": self.cache.get(HUMANOID_DIR / "backarm.png")}
        try:
            results = sc.check_item(item, self.cache.get, arms)
        except Exception as ex:
            results = [("error", f"check failed: {ex}")]
        t = self.cl_checks
        t.configure(state="normal")
        t.delete("1.0", "end")
        icons = {"error": "✖ ", "warn": "⚠ ", "info": "ℹ ", "ok": "✔ "}
        for lvl, msg in results:
            t.insert("end", icons.get(lvl, "") + msg + "\n", lvl)
        t.configure(state="disabled")
        self.fix_case_btn.configure(state="normal" if getattr(item, "case_issues", None) else "disabled")
        self._checks_dirty = False

    def cl_check_all(self):
        arms = {"frontSleeve": self.cache.get(HUMANOID_DIR / "frontarm.png"),
                "backSleeve": self.cache.get(HUMANOID_DIR / "backarm.png")}
        t = self.cl_checks
        t.configure(state="normal")
        t.delete("1.0", "end")
        total = 0
        for it in [i for i in self.items if not i.readonly]:  # the mod's own items
            res = [r for r in sc.check_item(it, self.cache.get, arms) if r[0] in ("error", "warn")]
            total += len(res)
            t.insert("end", f"{it.label}\n", "info")
            if not res:
                t.insert("end", "  ✔ OK\n", "ok")
            for lvl, msg in res:
                t.insert("end", f"  {'✖' if lvl == 'error' else '⚠'} {msg}\n", lvl)
        t.configure(state="disabled")
        self.status(f"Checked {len([i for i in self.items if not i.readonly])} mod items: {total} errors/warnings. "
                    "(Select an item to see its details again.)")

    def cl_fix_case(self):
        item = self.cl_item
        issues = getattr(item, "case_issues", None)
        if not issues:
            return
        lines = "\n".join(f"  {Path(d).name}  ->  {Path(w).name}" for w, d in issues)
        if not messagebox.askyesno("Fix file-name case",
                                   f"Rename these files to match what the item config asks for?\n\n{lines}"):
            return
        try:
            done = sc.fix_case(issues)
        except Exception as ex:
            messagebox.showerror("Rename failed", str(ex))
            return
        for w, d in issues:
            self.cache.forget(d)
            self.cache.forget(w)
        self.status("Renamed: " + "; ".join(done) if done else "Nothing to rename.")
        self._run_checks()
        self.render()

    # ================================================================== dirty / save
    def species_dirty(self):
        return self.palettes != self.saved_palettes

    def dirty_items(self):
        return [it for it in self.items if it.is_dirty()]

    def is_dirty(self):
        return self.species_dirty() or bool(self.dirty_items())

    def update_dirty(self):
        parts = []
        if self.species_dirty():
            parts.append(f"{SPECIES} palettes")
        n = len(self.dirty_items())
        if n:
            parts.append(f"{n} clothing item{'s' if n > 1 else ''}")
        self.dirty_label.config(text=("Unsaved: " + ", ".join(parts)) if parts else "")
        self.title(("* " if parts else "") + f"Species Editor - {SPECIES.title()}")

    def revert(self):
        if self.is_dirty() and not messagebox.askyesno("Revert", "Discard all unsaved changes "
                                                                 "(palettes and clothing)?"):
            return
        self.palettes = copy.deepcopy(self.saved_palettes)
        for it in self.items:
            it.options = copy.deepcopy(it.saved_options)
        self.refresh_palette_list()
        self.refresh_cl_options()
        self._refresh_preview_color_lists()
        self.update_dirty()
        self.render()

    def save(self):
        msgs = []
        if self.species_dirty():
            m = self._save_species()
            if m:
                msgs.append(m)
        for it in self.dirty_items():
            try:
                it.save()
                msgs.append(it.path.name)
            except Exception as ex:
                messagebox.showerror("Save failed", f"Could not save {it.path}:\n{ex}")
        self.refresh_palette_list()
        self.refresh_cl_options()
        self.update_dirty()
        self.status("Saved: " + ", ".join(msgs) if msgs else "Nothing to save.")

    def _save_species(self):
        if not self.palettes:
            return None
        try:
            data, raw = load_species()  # re-read so other edits to the file are kept
        except Exception as ex:
            messagebox.showerror("Save failed", f"Could not read {SPECIES_FILE}:\n{ex}")
            return None
        if sc.strip_json_comments(raw) != raw and not messagebox.askyesno(
                "Comments will be lost", "The species file contains comments, which will be removed. Continue?"):
            return None
        data["bodyColor"] = [{k: p["body"][k] for k in p["body"]} for p in self.palettes]
        data["undyColor"] = [{k: p["eye"][k] for k in p["eye"]} for p in self.palettes]
        if HAIR_KEYS:
            data["hairColor"] = [{k: p["hair"][k] for k in p["hair"]} for p in self.palettes]
        newline = "\r\n" if "\r\n" in raw else "\n"
        text = json.dumps(data, indent=2)
        if raw.endswith(("\n", "\r\n")):
            text += "\n"
        try:
            with open(SPECIES_FILE, "w", encoding="utf-8", newline=newline) as f:
                f.write(text)
        except Exception as ex:
            messagebox.showerror("Save failed", f"Could not write {SPECIES_FILE}:\n{ex}")
            return None
        self.species = data
        self.species_mtime = SPECIES_FILE.stat().st_mtime_ns
        self.saved_palettes = copy.deepcopy(self.palettes)
        return SPECIES_FILE.name

    def on_close(self):
        if self.is_dirty():
            ans = messagebox.askyesnocancel("Unsaved changes", "Save changes before closing?")
            if ans is None:
                return
            if ans:
                self.save()
                if self.is_dirty():
                    return
        self.destroy()

    # ================================================================== animation
    def _state_changed(self):
        _base, count, _cycle = STATES[self.state_var.get()]
        self.frame_scale.config(to=count)
        self.anim_frame = 0
        self.frame_var.set(1)
        self.render()

    def _frame_scrubbed(self):
        self.anim_frame = self.frame_var.get() - 1
        self.render()

    def step_frame(self, d):
        _base, count, _cycle = STATES[self.state_var.get()]
        self.playing.set(False)
        self.anim_frame = (self.anim_frame + d) % count
        self.frame_var.set(self.anim_frame + 1)
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

    # ================================================================== polling
    def _poll(self):
        try:
            changed = self.cache.poll()
            if changed:
                self._checks_dirty = True
            # species file changed outside the editor?
            try:
                m = SPECIES_FILE.stat().st_mtime_ns
            except OSError:
                m = self.species_mtime
            if m != self.species_mtime:
                if self.species_dirty():
                    self.species_mtime = m
                    self.status("species file changed on disk; you have unsaved palette edits, so it wasn't "
                                "reloaded (Revert discards your edits; Save overwrites the palettes).")
                    try:
                        self.species, _ = load_species()
                    except Exception:
                        pass
                else:
                    self.load_from_disk()
                    self.status("species file changed on disk - reloaded.")
                changed = True
            # clothing configs changed outside the editor?
            for it in self.items:
                if it.readonly:
                    continue
                try:
                    m = it.path.stat().st_mtime_ns
                except OSError:
                    continue
                if m != it.mtime:
                    if it.is_dirty():
                        it.mtime = m
                        self.status(f"{it.path.name} changed on disk; you have unsaved edits to it, so it "
                                    "wasn't reloaded.")
                    else:
                        try:
                            it.reload()
                            self.status(f"{it.path.name} changed on disk - reloaded.")
                        except Exception as ex:
                            self.status(f"{it.path.name} changed on disk but couldn't be parsed: {ex}")
                        if it is self.cl_item:
                            self.refresh_cl_options()
                        self._refresh_preview_color_lists()
                    self._checks_dirty = True
                    changed = True
            # new hair/markings files appearing
            self.refresh_part_lists()
            if self._checks_dirty and self.tabs.index("current") == 1:
                self._run_checks()
            if changed:
                self.render()
        finally:
            self.after(500, self._poll)

    # ================================================================== rendering
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

    def _crop(self, path, box):
        img = self.cache.get(path)
        if img is None or box is None:
            return None
        if box[2] > img.width or box[3] > img.height:
            return None
        return img.crop(box)

    def _item_layers(self, item, color_label, cb):
        """-> (mapping, {role: (disk_path, frames)}) for a previewed clothing item."""
        if item is None:
            return None, {}
        labels = list(cb["values"])
        idx = labels.index(color_label) if color_label in labels else 0
        mapping = {}
        if item.options and idx < len(item.options):
            for k, v in item.options[idx]["colors"].items():
                kk, vv = norm_hex(k), norm_hex(v)
                if kk and vv:
                    mapping[hex_rgba(kk)] = hex_rgba(vv)
        layers = {}
        for role in item.refs(self.gender.get()):
            wanted, disk, _exact = item.image_path(self.gender.get(), role)
            if disk is None:
                continue
            boxes, _where = sc.find_frames(item.mod_dir, wanted)
            if boxes is None:  # in-game this would fail; still preview with vanilla frames by role
                fallback = {"body": sc._CHEST, "legs": sc._PANTS, "frontSleeve": sc._ARM_GRID,
                            "backSleeve": sc._ARM_GRID, "head": sc._HEAD, "back": sc._BACK}.get(role)
                boxes = sc.parse_frames(fallback) if fallback else {}
            layers[role] = (disk, boxes)
        return mapping, layers

    def compose(self):
        gender = self.gender.get()
        state = self.state_var.get()
        base, count, _ = STATES[state]
        seq = (self.anim_frame % count) + 1
        pers = next(p for p in PERSONALITIES if p[0] == self.personality.get())

        pal = self.palettes[self.selected] if self.palettes else None

        def chosen(var):
            sel = var.get()
            if sel.startswith("Palette "):
                idx = int(sel.split()[1])
                if idx < len(self.palettes):
                    return self.palettes[idx]
            return pal

        mapping = self._mapping(pal, chosen(self.eye_var))
        if HAIR_KEYS:
            # own hairColor list: hair uses only that palette (markings, if any, use the body palette)
            hp = chosen(self.hair_color_var)
            hair_only = {hex_rgba(k): hex_rgba(v) for k, v in (hp or {}).get("hair", {}).items() if k != v}
            hair_mapping, marking_mapping = hair_only, mapping
        else:
            hair_mapping = marking_mapping = mapping if self.color_hair.get() else {}

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

        # chest armor frame
        if state == "Run":
            chest_name = "run"
        elif state == "Idle":
            chest_name = pers[1]
        elif state == "Duck":
            chest_name = "duck"
        elif state in ("Swim", "SwimIdle"):
            chest_name = "swim"
        else:
            chest_name = "chest.1"

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
        head_box = HEAD_FRAMES["climb" if climbing else "normal"]
        # game y is up, image y is down
        head_xy = (PAD + head_off[0], PAD - (bob + head_off[1]))
        arm_xy = (PAD + arm_off[0], PAD - arm_off[1])
        body_xy = (PAD, PAD)
        chest_xy = (PAD, PAD - (0 if state == "Duck" else bob))
        # species clothing offset (preview only): shirt + sleeves move with the upper body, pants on their own
        off = self._clothing_offsets()
        shirt_xy = (chest_xy[0], chest_xy[1] + off["chest"])
        front_sleeve_xy = (arm_xy[0], arm_xy[1] + off["frontSleeve"])
        back_sleeve_xy = (arm_xy[0], arm_xy[1] + off["backSleeve"])
        pants_xy = (body_xy[0], body_xy[1] + off["legs"])

        size = FRAME + 2 * PAD
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        missing = []

        def draw(path, box, xy, m, label, transform=None):
            if path is None:
                return
            crop = self._crop(path, box)
            if crop is None:
                missing.append(label)
                return
            if transform:
                crop = transform(crop)
            canvas.alpha_composite(recolor(crop, m), xy)

        shirt_map, shirt = self._item_layers(self._item_by_label(self.shirt_var.get()),
                                             self.shirt_color.get(), self.shirt_color_cb)
        pants_map, pants = self._item_layers(self._item_by_label(self.pants_var.get()),
                                             self.pants_color.get(), self.pants_color_cb)
        char = not self.clothing_only.get()
        show_arms = self.show_arms.get() and not climbing

        def armor(layers, role, frame, xy, m, transform=None):
            if role in layers:
                disk, boxes = layers[role]
                draw(disk, boxes.get(frame), xy, m, f"{disk.name}:{frame}", transform)

        shrink_shirt = (lambda im: shrink_rows(im, off["shrink"])) if off["shrink"] else None
        shrink_pants = (lambda im: shrink_rows(im, off["legsShrink"])) if off["legsShrink"] else None

        # Layer order matches Starbound's Humanoid::render:
        # back arm + back sleeve, head, emote, hair, body, legs armor, chest armor,
        # facial hair (markings), [facial mask], [head armor], front arm + front sleeve.
        if show_arms:
            if char:
                draw(HUMANOID_DIR / "backarm.png", ARM_FRAMES.get(arm_name), arm_xy, mapping, "backarm")
            armor(shirt, "backSleeve", arm_name, back_sleeve_xy, shirt_map)
        if char:
            draw(HUMANOID_DIR / f"{gender}head.png", head_box, head_xy, mapping, f"{gender}head")
            if not climbing:
                _l, ebase, ecount, _c = self._current_emote()
                ename = f"{ebase}.{(self.emote_frame % ecount) + 1}"
                draw(HUMANOID_DIR / "emote.png", EMOTE_FRAMES.get(ename), head_xy, mapping, "emote")
            draw(self.hair_options.get(self.hair_var.get()), head_box, head_xy, hair_mapping, "hair")
            draw(HUMANOID_DIR / f"{gender}body.png", BODY_FRAMES.get(body_name), body_xy, mapping, f"{gender}body")
        armor(pants, "legs", body_name, pants_xy, pants_map, shrink_pants)
        armor(shirt, "body", chest_name, shirt_xy, shirt_map, shrink_shirt)
        if char:
            draw(self.marking_options.get(self.marking_var.get()), head_box, head_xy, marking_mapping, "markings")
        if show_arms:
            if char:
                draw(HUMANOID_DIR / "frontarm.png", ARM_FRAMES.get(arm_name), arm_xy, mapping, "frontarm")
            armor(shirt, "frontSleeve", arm_name, front_sleeve_xy, shirt_map)

        if self.face_left.get():
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)

        info = f"body: {body_name}"
        if show_arms:
            info += f"   arms: {arm_name}"
        if shirt:
            info += f"   chest: {chest_name}"
        if climbing:
            info += "   (arms are part of the climb body frames)"
        if missing:
            info += "   missing: " + ", ".join(missing)
        return canvas, info

    def export_image(self):
        """Save just the composited sprite: native pixel size, transparent, cropped to the character
        (no canvas background, padding or zoom)."""
        try:
            img, _info = self.compose()
        except Exception as ex:
            messagebox.showerror("Export failed", f"Couldn't render the preview:\n{ex}")
            return
        bbox = img.getchannel("A").getbbox()
        if bbox is None:
            messagebox.showinfo("Export", "Nothing is drawn, so there's nothing to export.")
            return
        big = img.crop(bbox)
        state = self.state_var.get()
        frame = "" if STATES[state][1] == 1 else f"{self.anim_frame + 1}"
        name = f"{SPECIES}_{self.gender.get()}_{state.lower()}{frame}.png"
        initial_dir = getattr(self, "_export_dir", None)
        if not initial_dir:
            pics = Path.home() / "Pictures"
            initial_dir = str(pics if pics.is_dir() else Path.home())
        path = filedialog.asksaveasfilename(parent=self, title="Export preview image", defaultextension=".png",
                                            initialdir=initial_dir, initialfile=name,
                                            filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            big.save(path, format="PNG")
        except Exception as ex:
            messagebox.showerror("Export failed", f"Couldn't save {path}:\n{ex}")
            return
        self._export_dir = str(Path(path).parent)
        self.status(f"Exported {big.width}x{big.height} image to {path}")

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
        cw, ch = cv.winfo_width(), cv.winfo_height()
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
