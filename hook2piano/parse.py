"""Parse a Hookpad project dict into absolute-pitch piano events.

Produces a Song: ordered sections, each with key/meter/tempo maps, a list of
ChordEvents (absolute LH voicings) and NoteEvents (absolute RH melody).
"""

from dataclasses import dataclass, field

from .theory import (Key, chord_tones, melody_midi, melody_name, midi_to_name,
                     name_to_vf, prefers_flats, vf_key)


@dataclass
class ChordEvent:
    beat: float
    duration: float
    label: str          # "D#m/F#"
    roman: str          # "i6"
    bass_midi: int
    tone_midis: list    # full chord tones (stacked order)
    lh_midis: list      # piano LH voicing: [bass, ...close position above]
    flats: bool = False
    warnings: list = field(default_factory=list)


@dataclass
class NoteEvent:
    beat: float
    duration: float
    midi: int | None    # None = rest
    name: str           # "A#4" or "rest"
    flats: bool = False


@dataclass
class Section:
    name: str
    title: str
    key: Key
    bpm: float
    beats_per_measure: int
    chords: list        # ChordEvent
    notes: list         # NoteEvent
    end_beat: float
    pickup: bool


def _key_at(keys, beat):
    cur = keys[0]
    for k in keys:
        if k["beat"] <= beat:
            cur = k
    return cur


def _voice_lh(bass_midi, tone_midis):
    """Piano LH voicing: bass low, remaining tones in close position above.

    Bass is placed in octave 1-2 (MIDI 28-47); upper tones stack above the
    bass with minimal gaps (close position). Tones are pitch classes from
    the chord; duplicates of the bass pitch class are dropped from the top.
    """
    bass_pc = bass_midi % 12
    # drop bass tone from upper stack (keep other tones)
    upper = [m for m in tone_midis if m % 12 != bass_pc]
    # place bass: choose octave so it lands in [33, 45]
    b = bass_midi
    while b > 45:
        b -= 12
    while b < 33:
        b += 12
    voicing = [b]
    prev = b
    for m in upper:
        pc = m % 12
        cand = prev + ((pc - prev) % 12)
        if cand == prev:  # same pitch class as previous -> push up an octave
            cand += 12
        voicing.append(cand)
        prev = cand
    # keep the whole voicing within a 10th-ish span; drop doublings if huge
    return voicing


def parse_section(name, project):
    keys_raw = project.get("keys") or [{"beat": 1, "scale": "major", "tonic": "C"}]
    key_objs = [Key(k["tonic"], k["scale"]) for k in keys_raw]
    meters = project.get("meters") or [{"beat": 1, "numBeats": 4}]
    tempos = project.get("tempos") or [{"beat": 1, "bpm": 120}]
    bpm = tempos[0]["bpm"]
    bpm_beat = meters[0].get("numBeats", 4)
    end_beat = float(project.get("endBeat") or 0)
    pickup = bool(project.get("pickup"))

    chords = []
    for c in project.get("chords", []):
        if c.get("isRest"):
            continue
        kraw = _key_at(keys_raw, c["beat"])
        key = Key(kraw["tonic"], kraw["scale"])
        flats = prefers_flats(key)
        ct = chord_tones(key, c, prefer_flats=flats)
        if not ct["tones"]:
            continue
        tone_midis = [m for m, _ in ct["tones"]]
        bass_midi = ct["bass"][0]
        lh = _voice_lh(bass_midi, tone_midis)
        chords.append(ChordEvent(
            beat=float(c["beat"]), duration=float(c["duration"]),
            label=ct["label"], roman=ct["roman"],
            bass_midi=bass_midi, tone_midis=tone_midis,
            lh_midis=lh, flats=flats, warnings=ct["warnings"]))

    notes = []
    for n in project.get("notes", []):
        beat = float(n["beat"])
        dur = float(n["duration"])
        kraw = _key_at(keys_raw, beat)
        key = Key(kraw["tonic"], kraw["scale"])
        flats = prefers_flats(key)
        if n.get("isRest"):
            notes.append(NoteEvent(beat, dur, None, "rest", flats))
            continue
        midi = melody_midi(key, n["sd"], int(n["octave"]))
        notes.append(NoteEvent(beat, dur, midi,
                               melody_name(key, n["sd"], int(n["octave"])),
                               flats))

    if not end_beat:
        ends = [c.beat + c.duration for c in chords]
        ends += [n.beat + n.duration for n in notes]
        end_beat = max(ends) if ends else 0

    return Section(name=name, title=project.get("_song_title", ""),
                   key=key_objs[0], bpm=bpm,
                   beats_per_measure=int(bpm_beat),
                   chords=chords, notes=notes,
                   end_beat=end_beat, pickup=pickup)


def split_measures(section):
    """Split a section into per-measure event dicts (beats relative to bar).

    Chords and notes that cross barlines are clipped (no ties across bars in
    v1). Returns [{"chords": [...], "notes": [...]}] with VexFlow-ready keys.
    """
    bpm = section.beats_per_measure
    n_meas = max(1, int((section.end_beat - 1) // bpm) + 1)
    measures = []
    for m in range(n_meas):
        b0 = 1 + m * bpm
        b1 = b0 + bpm
        mch, mnt = [], []
        for c in section.chords:
            if c.beat < b1 and c.beat + c.duration > b0:
                start = max(c.beat, b0) - b0
                dur = min(c.beat + c.duration, b1) - max(c.beat, b0)
                if dur > 1e-6:
                    mch.append({
                        "beat": round(start, 6), "dur": round(dur, 6),
                        "label": c.label, "roman": c.roman,
                        "midis": c.lh_midis,
                        "vfkeys": [list(vf_key(mm, c.flats))
                                   for mm in c.lh_midis],
                    })
        for n in section.notes:
            if n.beat < b1 and n.beat + n.duration > b0:
                start = max(n.beat, b0) - b0
                dur = min(n.beat + n.duration, b1) - max(n.beat, b0)
                if dur > 1e-6:
                    key, acc = name_to_vf(n.name)
                    mnt.append({
                        "beat": round(start, 6), "dur": round(dur, 6),
                        "midi": n.midi, "key": key, "acc": acc,
                        "name": n.name,
                    })
        measures.append({"chords": mch, "notes": mnt})
    return measures
