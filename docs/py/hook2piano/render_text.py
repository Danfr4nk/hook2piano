"""Plain-text lead sheet: chord grid + melody note names, one section per block."""

from .parse import split_measures
from .theory import midi_to_name, prefers_flats


def _dur_name(beats):
    names = {4: "w", 3: "d.h", 2: "h", 1.5: "d.q", 1: "q", 0.75: "d.8",
             0.5: "8", 0.375: "d.16", 0.25: "16", 0.125: "32",
             2 / 3: "qt", 1 / 3: "8t", 1 / 6: "16t"}
    b = round(beats, 3)
    for k, v in names.items():
        if abs(b - k) < 0.015:
            return v
    return f"{b:g}b"


def render(sections):
    out = []
    for s in sections:
        keyname = f"{s.key.tonic} {s.key.scale}"
        out.append(f"{s.title} — {s.name}")
        out.append(f"Key {keyname} | {s.bpm:g} BPM | {s.beats_per_measure}/4")
        out.append("")
        for i, m in enumerate(split_measures(s)):
            flats = prefers_flats(s.key)
            chord_str = "  ".join(
                f"[{c['beat'] + 1:.2g}] {c['label']} ({c['roman']})"
                for c in m["chords"]) or "—"
            mel_str = " ".join(
                f"{n['name']}({_dur_name(n['dur'])})" for n in m["notes"]
                if n["midi"] is not None) or "—"
            lh_str = " ".join(midi_to_name(mm, flats)
                              for c in m["chords"] for mm in c["midis"])
            out.append(f"bar {i + 1:>2}: LH {chord_str}")
            if m["chords"]:
                out.append(f"        voicing: {lh_str}")
            out.append(f"        RH: {mel_str}")
        out.append("")
        warns = {w for c in s.chords for w in c.warnings}
        for w in sorted(warns):
            out.append(f"  ! {w}")
        out.append("=" * 64)
        out.append("")
    return "\n".join(out)
