"""Music-theory core for hook2piano.

Converts Hookpad/Hooktheory relative notation (scale degrees, chord type
codes, figured-bass inversions) into absolute MIDI pitches and note names.

Key findings (reverse-engineered from hooktheory.com's own player bundle
and verified against published melody ranges on theorytab pages):

* Melody notes: {"sd": "5", "octave": 0} with sd possibly prefixed by
  accidental markers ("f"/"b" = flat, "s"/"#" = sharp, "x" = double sharp,
  e.g. "f3", "s4"). Absolute pitch:
      MIDI = 12*octave + 60 + pc(tonic) + scale[degree-1] + accidental
  Verified: TLC "This Is How It Works" (D# minor) -> F#3-F#5;
            Beatles "Let It Be" verse (C major) -> E3-F4. Both match the
  ranges published on their TheoryTab pages exactly.
* Chords: {"root": <scale degree>, "type": 5|7|9|11|13, "inversion": n,
  "applied": 0|5|7, "borrowed": <scale name>|None, "alterations": [...],
  "suspensions": [...], "adds": [...], "omits": [...]}.
  - type = number of stacked thirds indicator: 5=triad, 7=seventh,
    9/11/13=extensions (matches the player's figured-bass table).
  - applied=5 -> the chord is an applied dominant (V of `root`): its real
    root is a perfect fifth above the target degree, quality forced major/
    dominant-7. applied=7 -> applied vii-dim: root is the leading tone
    (semitone below target), quality diminished.
    (Verified: Radiohead "Creep" B major = V/vi -> root=6, applied=5.)
  - borrowed=<scale> swaps the diatonic scale used to build the chord.
"""

from dataclasses import dataclass, field
import re

# Semitone offsets for each named scale (Hookpad's scale list, from their
# own chord-label engine).
SCALES = {
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "phrygian":         [0, 1, 3, 5, 7, 8, 10],
    "lydian":           [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "minor":            [0, 2, 3, 5, 7, 8, 10],
    "locrian":          [0, 1, 3, 5, 6, 8, 10],
    "harmonicMinor":    [0, 2, 3, 5, 7, 8, 11],
    "phrygianDominant": [0, 1, 4, 5, 7, 8, 10],
}

_LETTERS = "CDEFGAB"
_LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_PC_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_PC_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def parse_tonic(tonic):
    """'D#' -> (pitch class 3, letter 'D', accidental +1)."""
    tonic = tonic.strip()
    letter = tonic[0].upper()
    acc = 0
    for ch in tonic[1:]:
        if ch == "#":
            acc += 1
        elif ch == "b":
            acc -= 1
        elif ch == "x":
            acc += 2
    pc = (_LETTER_PC[letter] + acc) % 12
    return pc, letter, acc


def parse_degree(sd):
    """'5' -> (5, 0); 'f3' -> (3, -1); 's4' -> (4, +1); 'x2' -> (2, +2)."""
    s = str(sd).strip()
    acc = 0
    while s and s[0] in "fbs#x":
        ch = s[0]
        acc += {"f": -1, "b": -1, "s": 1, "#": 1, "x": 2}[ch]
        s = s[1:]
    return int(s), acc


def midi_to_name(midi, prefer_flats=False):
    names = _PC_NAMES_FLAT if prefer_flats else _PC_NAMES_SHARP
    return f"{names[midi % 12]}{midi // 12 - 1}"


def vf_key(midi, prefer_flats=False):
    """VexFlow key + accidental for a MIDI pitch.

    Returns (key, acc) e.g. ("a/4", "#"); VexFlow wants the accidental as
    a separate modifier, not embedded in the key string.
    """
    name = midi_to_name(midi, prefer_flats)
    m = re.match(r"^([A-G])([#bx]*)?(-?\d+)$", name)
    letter, accs, octv = m.group(1), m.group(2) or "", m.group(3)
    acc = {"#": "#", "b": "b", "x": "##", "bb": "bb"}.get(accs, "")
    if accs and not acc:  # exotic stack, e.g. "###"
        acc = "#" * accs.count("#") + "b" * accs.count("b")
    return f"{letter.lower()}/{octv}", acc


def name_to_vf(name):
    """'Eb4' -> ('e/4', 'b'); 'F#5' -> ('f/5', '#'); 'rest' -> (None, None)."""
    if name == "rest":
        return None, None
    m = re.match(r"^([A-G])([#bx]*)?(-?\d+)$", name)
    letter, accs, octv = m.group(1), m.group(2) or "", m.group(3)
    acc = {"#": "#", "b": "b", "x": "##", "bb": "bb"}.get(accs, "")
    return f"{letter.lower()}/{octv}", acc


_MAJOR_PC_NAME = {0: "C", 1: "Db", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "F#",
                  7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}
_MODE_START = {"major": 1, "dorian": 2, "phrygian": 3, "lydian": 4,
               "mixolydian": 5, "minor": 6, "locrian": 7,
               "harmonicMinor": 6, "phrygianDominant": 3}
_MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]


def key_signature(key):
    """VexFlow key-signature name for a Key (via its relative major)."""
    start = _MODE_START.get(key.scale, 1)
    rel_pc = (key.pc - _MAJOR_STEPS[start - 1]) % 12
    return _MAJOR_PC_NAME[rel_pc]


def prefers_flats(key):
    return "b" in key_signature(key)


@dataclass
class Key:
    tonic: str          # e.g. "D#"
    scale: str          # e.g. "minor"
    pc: int = field(init=False)
    letter: str = field(init=False)
    scale_steps: list = field(init=False)

    def __post_init__(self):
        self.pc, self.letter, _ = parse_tonic(self.tonic)
        if self.scale not in SCALES:
            raise ValueError(f"unknown scale {self.scale!r}")
        self.scale_steps = SCALES[self.scale]

    def degree_pitch(self, degree, accidental=0, octave=5):
        """Absolute MIDI for a scale degree.

        Hookpad melody convention: octave=0 for degree 1 == MIDI 60+pc(tonic)
        (verified empirically). `octave` here is the Hookpad octave number.
        """
        steps = self.scale_steps
        midi = 12 * octave + 60 + self.pc + steps[(degree - 1) % 7] + accidental
        return midi

    def degree_letter(self, degree):
        """Diatonic letter name for a scale degree (ignores accidentals)."""
        idx = _LETTERS.index(self.letter)
        return _LETTERS[(idx + degree - 1) % 7]

    def spell(self, degree, accidental=0):
        """Note name for a scale degree + accidental offset, e.g. 'A#4'.

        Returns (name_without_octave, accidental_int).
        """
        letter = self.degree_letter(degree)
        diatonic_pc = (self.pc + self.scale_steps[(degree - 1) % 7]) % 12
        need = (diatonic_pc + accidental - _LETTER_PC[letter]) % 12
        if need > 6:
            need -= 12
        suffix = {0: "", 1: "#", 2: "x", -1: "b", -2: "bb"}.get(need, "")
        if suffix == "":
            # Fallback for exotic offsets: spell enharmonically.
            pc = (self.pc + self.scale_steps[(degree - 1) % 7] + accidental) % 12
            return _PC_NAMES_SHARP[pc], need
        return f"{letter}{suffix}", need


# Chord-tone role -> index into the stacked-thirds tone list.
_ROLE_INDEX = {"1": 0, "3": 1, "5": 2, "7": 3, "9": 4, "11": 5, "13": 6}


def _stack_thirds(key, root_degree, n_tones, scale_steps=None):
    """Stack n_tones thirds above root_degree; returns list of
    (midi, degree, accidental) with diatonic spelling info."""
    steps = scale_steps if scale_steps is not None else key.scale_steps
    tones = []
    for i in range(n_tones):
        deg = root_degree + 2 * i
        octs, d = divmod(deg - 1, 7)
        d += 1
        midi = 12 * (octs + 5) + key.pc + steps[d - 1]
        tones.append([midi, d, 0])
    return tones


def chord_tones(key, chord, prefer_flats=False):
    """Compute absolute MIDI pitches + spelling for a Hookpad chord dict.

    Returns dict with:
      tones: list of (midi, name) in stacked order (root position)
      bass:  (midi, name) after inversion
      label: letter-name chord symbol, e.g. "D#m", "A#m7/D#"
      roman: Hooktheory-style roman numeral, e.g. "i", "V/vi"
      warnings: list of strings for unhandled fields
    """
    warnings = []
    root = int(chord["root"])
    ctype = int(chord.get("type", 5))
    inversion = int(chord.get("inversion", 0))
    applied = int(chord.get("applied", 0) or 0)
    borrowed = chord.get("borrowed") or None
    alterations = list(chord.get("alterations") or [])
    suspensions = list(chord.get("suspensions") or [])
    adds = list(chord.get("adds") or [])
    omits = list(chord.get("omits") or [])
    subs = chord.get("substitutions") or []
    pedal = chord.get("pedal")

    if subs:
        warnings.append(f"substitutions ignored: {subs}")
    if pedal is not None:
        warnings.append(f"pedal ignored: {pedal!r}")

    eff_steps = SCALES[borrowed] if borrowed in SCALES else key.scale_steps
    if borrowed and borrowed not in SCALES:
        warnings.append(f"unknown borrowed scale {borrowed!r}; using song scale")

    n_tones = {5: 3, 7: 4, 9: 5, 11: 6, 13: 7}.get(ctype, 3)

    # --- determine root pitch + base quality ---
    is_applied_dom = applied == 5
    is_applied_dim = applied == 7
    if is_applied_dom or is_applied_dim:
        # `root` is the TARGET degree; the real chord root is derived.
        target_midi = 12 * 5 + key.pc + key.scale_steps[(root - 1) % 7]
        if is_applied_dom:
            root_midi = target_midi + 7  # perfect fifth above target
            # dominant: major triad + minor 7th + mixolydian extensions
            dom_steps = [0, 4, 7, 10, 14, 17, 21]
            tones = [[root_midi + dom_steps[i], None, 0] for i in range(n_tones)]
            quality = "dom7" if n_tones >= 4 else "dom"
        else:
            root_midi = target_midi - 1  # leading tone below target
            dim_steps = [0, 3, 6, 9, 12, 15, 18]  # fully diminished stack
            tones = [[root_midi + dim_steps[i], None, 0] for i in range(n_tones)]
            quality = "dimdim7" if n_tones >= 4 else "dim"
        root_name = midi_to_name(root_midi % 12 + 60)[:-1]  # pitch-class name
    else:
        tones = _stack_thirds(key, root, n_tones, eff_steps)
        root_midi = tones[0][0]
        # diatonic quality from third + fifth intervals
        third_iv = tones[1][0] - tones[0][0]
        fifth_iv = tones[2][0] - tones[0][0]
        if third_iv == 4 and fifth_iv == 7:
            quality = "maj"
        elif third_iv == 3 and fifth_iv == 7:
            quality = "min"
        elif third_iv == 3 and fifth_iv == 6:
            quality = "dim"
        elif third_iv == 4 and fifth_iv == 8:
            quality = "aug"
        else:
            quality = "maj" if third_iv == 4 else "min"
            warnings.append(f"odd diatonic intervals {third_iv}/{fifth_iv}; guessed {quality}")
        if n_tones >= 4:
            seventh_iv = tones[3][0] - tones[0][0]
            if quality == "maj" and seventh_iv == 10:
                quality = "dom7"      # major triad + minor 7th = dominant 7th
            elif quality == "min" and seventh_iv == 9:
                quality = "mindim7"   # half-diminished
            else:
                quality += {11: "maj7", 10: "7", 9: "dim7",
                            8: "dim7"}.get(seventh_iv, "7")
        root_name = key.spell(root)[0]

    # --- alterations (e.g. '#5', 'b9') ---
    for alt in alterations:
        sign = 1 if alt[0] == "#" else -1
        role = alt[1:]
        idx = _ROLE_INDEX.get(role)
        if idx is None:
            warnings.append(f"unknown alteration {alt!r}")
            continue
        while len(tones) <= idx:  # alteration implies the extension exists
            i = len(tones)
            deg = root + 2 * i
            octs, d = divmod(deg - 1, 7)
            tones.append([12 * (octs + 5) + key.pc + eff_steps[d], d + 1, 0])
        tones[idx][0] += sign
        tones[idx][2] += sign

    # --- suspensions replace the third ---
    for sus in suspensions:
        sus = int(sus)
        if sus == 4:
            tones[1][0] = tones[0][0] + 5
        elif sus == 2:
            tones[1][0] = tones[0][0] + 2
        else:
            warnings.append(f"unknown suspension sus{sus}")
    has_sus = bool(suspensions)

    # --- adds (2->9th, 4->11th, 6->13th), diatonic to effective scale ---
    added = []
    for a in adds:
        a = int(a)
        deg = root + a - 1
        octs, d = divmod(deg - 1, 7)
        midi = 12 * (octs + 6) + key.pc + eff_steps[d]
        if all((midi - t[0]) % 12 != 0 for t in tones):
            tones.append([midi, d + 1, 0])
            added.append(a)

    # --- omits remove chord tones by role number ---
    omit_roles = {str(int(o)) for o in omits}
    keep = []
    for i, t in enumerate(tones):
        role = {0: "1", 1: "3", 2: "5", 3: "7", 4: "9", 5: "11", 6: "13"}.get(i)
        if role in omit_roles:
            continue
        keep.append(t)
    tones = keep

    # --- inversion -> bass ---
    if not tones:
        warnings.append("chord has no tones after omits")
        return {"tones": [], "bass": None, "label": "N.C.",
                "roman": "", "warnings": warnings}
    bass_idx = inversion % len(tones)
    bass_midi = tones[bass_idx][0]

    # --- labels ---
    label = _chord_label(root_name, quality, ctype, has_sus, suspensions,
                         added, omit_roles, alterations)
    if inversion:
        bass_name = midi_to_name((bass_midi % 12) + 60, prefer_flats)[:-1]
        # spell bass from its scale degree when diatonic
        label += f"/{bass_name}"
    roman = _roman_numeral(key, root, quality, applied, borrowed, inversion,
                         ctype)

    # name every tone (best-effort spelling from pitch class)
    named = []
    for midi, deg, acc in tones:
        if deg is None:
            named.append((midi, midi_to_name(midi)))
        else:
            name, _ = key.spell(deg, acc)
            named.append((midi, name))
    bass_name_full = midi_to_name(bass_midi)
    return {"tones": named, "bass": (bass_midi, bass_name_full),
            "label": label, "roman": roman, "warnings": warnings}


def _chord_label(root_name, quality, ctype, has_sus, suspensions, added,
                 omit_roles, alterations):
    q = quality
    if q == "dom":
        q = "maj"  # applied dominant triad: plain major
    elif q == "dom7":
        pass  # handled below
    if has_sus:
        sus = suspensions[0]
        base = f"{root_name}sus{sus}"
    elif q == "maj":
        base = root_name
    elif q == "min":
        base = f"{root_name}m"
    elif q == "dim":
        base = f"{root_name}dim"
    elif q == "aug":
        base = f"{root_name}aug"
    elif q == "majmaj7":
        base = f"{root_name}maj7"
    elif q == "min7":
        base = f"{root_name}m7"
    elif q == "dom7":
        base = f"{root_name}7"
    elif q == "mindim7":
        base = f"{root_name}m7b5"
    elif q == "dimdim7":
        base = f"{root_name}m7b5" if False else f"{root_name}dim7"
    elif q == "maj7":
        base = f"{root_name}maj7"
    elif q == "minmaj7":
        base = f"{root_name}mmaj7"
    else:
        base = f"{root_name}({q})"
    # extensions beyond 7
    if ctype in (9, 11, 13) and not base.endswith(("7", "9")):
        base += str(ctype)
    elif ctype in (9, 11, 13):
        # turn "X7" into "X9" etc.
        if base.endswith("7") and not base.endswith(("maj7", "m7")):
            base = base[:-1] + str(ctype)
        elif base.endswith("maj7"):
            base = base[:-4] + f"maj{ctype}"
        elif base.endswith("m7"):
            base = base[:-2] + f"m{ctype}"
    extras = []
    for a in added:
        extras.append({2: "add9", 4: "add11", 6: "add13"}.get(a, f"add{a}"))
    for o in sorted(omit_roles):
        extras.append({"3": "no3", "5": "no5", "7": "no7"}.get(o, f"no{o}"))
    for alt in alterations:
        extras.append(alt)
    if extras:
        base += "(" + ")(".join(extras) + ")"
    return base


_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]


def _diatonic_quality(key, degree):
    """Triad quality of a scale degree in the key's own scale."""
    steps = key.scale_steps
    d = (degree - 1) % 7
    third = (steps[(d + 2) % 7] - steps[d]) % 12
    fifth = (steps[(d + 4) % 7] - steps[d]) % 12
    if third == 4 and fifth == 7:
        return "maj"
    if third == 3 and fifth == 7:
        return "min"
    if third == 3 and fifth == 6:
        return "dim"
    if third == 4 and fifth == 8:
        return "aug"
    return "maj"


def _roman_numeral(key, root, quality, applied, borrowed, inversion, ctype=5):
    deg = ((root - 1) % 7) + 1
    q = quality
    if q in ("min", "min7", "minmaj7", "mindim7"):
        head = _ROMAN[deg - 1].lower()
    elif q in ("dim", "dimdim7"):
        head = _ROMAN[deg - 1].lower() + "°"
    elif q == "aug":
        head = _ROMAN[deg - 1] + "+"
    else:
        head = _ROMAN[deg - 1]
    # seventh quality + inversion figures (figured bass: 7, 65, 43, 42)
    if ctype == 7:
        if inversion:
            fig = {1: "65", 2: "43", 3: "42"}.get(inversion,
                                                  f" inv{inversion}")
        elif q == "majmaj7":
            fig = "maj7"
        elif q == "minmaj7":
            fig = "mmaj7"
        elif q == "mindim7":
            fig = "ø7"
        else:
            fig = "7"
    elif inversion:
        fig = {1: "6", 2: "64", 3: "42"}.get(inversion, f" inv{inversion}")
    else:
        fig = ""
    if applied == 5 or applied == 7:
        # target degree's own diatonic quality sets the case: V/vi, vii°/V ...
        tq = _diatonic_quality(key, root)
        tnum = _ROMAN[deg - 1]
        if tq == "min":
            tnum = tnum.lower()
        elif tq == "dim":
            tnum = tnum.lower() + "°"
        elif tq == "aug":
            tnum = tnum + "+"
        pfx = "V" if applied == 5 else "vii°"
        head = pfx + fig + "/" + tnum
    else:
        head = head + fig
    if borrowed:
        head += f" (bor. {borrowed})"
    return head


def melody_midi(key, sd, octave):
    """Absolute MIDI for a Hookpad melody note dict."""
    degree, acc = parse_degree(sd)
    return key.degree_pitch(degree, acc, octave)


def melody_name(key, sd, octave):
    degree, acc = parse_degree(sd)
    name, _ = key.spell(degree, acc)
    midi = key.degree_pitch(degree, acc, octave)
    return f"{name}{midi // 12 - 1}"
