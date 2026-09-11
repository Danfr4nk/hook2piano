"""Unit tests for hook2piano's theory engine.

Ground truth comes from verified Hooktheory tabs:
- TLC "This Is How It Works" (tab nZgWr__wmry): D# minor, melody range F#3-F#5
- Beatles "Let It Be" verse (tab _NgbRXeYgQA): melody range E3-F4
- Radiohead "Creep" (tab nJmBYYkXpoA): G-B-C-Cm progression
"""

import unittest

from hook2piano.theory import (Key, chord_tones, melody_midi, midi_to_name,
                               prefers_flats, vf_key)


def ct(key, **kw):
    """Build a Hookpad-style chord dict and run chord_tones."""
    d = {"root": 1, "beat": 1, "duration": 4, "type": 5}
    d.update(kw)
    return chord_tones(key, d)


class TestMelodyDecoding(unittest.TestCase):
    def test_tlc_range_endpoints(self):
        # D# minor: degree 3, octave -1 == F#3 ; degree 3, octave 1 == F#5
        # (verified against the live tab: computed range F#3-F#5 matches
        # Hooktheory's published melody range exactly)
        key = Key("D#", "minor")
        self.assertEqual(melody_midi(key, "3", -1), 54)   # F#3
        self.assertEqual(melody_midi(key, "3", 1), 78)    # F#5
        self.assertEqual(midi_to_name(54), "F#3")
        self.assertEqual(midi_to_name(78), "F#5")

    def test_letitbe_range_endpoints(self):
        # C major: degree 3, octave -1 == E3 ; degree 4, octave 0 == F4
        key = Key("C", "major")
        self.assertEqual(melody_midi(key, "3", -1), 52)   # E3
        self.assertEqual(melody_midi(key, "4", 0), 65)     # F4

    def test_hookpad_formula_spot_check(self):
        # MIDI = 12*octave + 60 + tonic_pc + scale[degree-1] + accidental
        key = Key("G", "major")
        self.assertEqual(melody_midi(key, "1", 0), 67)     # G4
        self.assertEqual(melody_midi(key, "5", 0), 74)     # D5


class TestTriads(unittest.TestCase):
    def test_g_major_triad(self):
        key = Key("G", "major")
        r = ct(key, root=1)
        self.assertEqual([m % 12 for m, _ in r["tones"]], [7, 11, 2])
        self.assertEqual(r["label"], "G")
        self.assertEqual(r["roman"], "I")

    def test_diatonic_qualities(self):
        key = Key("C", "major")
        # ii = Dm, iii = Em, IV = F, V = G, vi = Am, viio = Bdim
        expect = {2: ("Dm", "ii"), 3: ("Em", "iii"), 4: ("F", "IV"),
                  5: ("G", "V"), 6: ("Am", "vi"), 7: ("Bdim", "vii°")}
        for deg, (label, roman) in expect.items():
            r = ct(key, root=deg)
            self.assertEqual(r["label"], label, f"degree {deg}")
            self.assertEqual(r["roman"], roman, f"degree {deg}")

    def test_minor_key(self):
        key = Key("D#", "minor")
        r = ct(key, root=1)
        self.assertEqual(r["label"], "D#m")
        self.assertEqual(r["roman"], "i")
        r = ct(key, root=5)
        self.assertEqual(r["label"], "A#m")
        self.assertEqual(r["roman"], "v")


class TestSevenths(unittest.TestCase):
    def test_diatonic_dominant_seventh_is_dom7_not_maj7(self):
        # G7 in C major must be "G7" (minor 7th), not "Gmaj7"
        key = Key("C", "major")
        r = ct(key, root=5, type=7)
        self.assertEqual([m % 12 for m, _ in r["tones"]], [7, 11, 2, 5])
        self.assertEqual(r["label"], "G7")
        self.assertEqual(r["roman"], "V7")

    def test_major_seventh(self):
        key = Key("C", "major")
        r = ct(key, root=1, type=7)
        self.assertEqual([m % 12 for m, _ in r["tones"]], [0, 4, 7, 11])
        self.assertEqual(r["label"], "Cmaj7")

    def test_minor_seventh(self):
        key = Key("G", "major")
        r = ct(key, root=6, type=7)
        self.assertEqual(r["label"], "Em7")

    def test_seventh_inversion_figures(self):
        key = Key("C", "major")
        r = ct(key, root=5, type=7, inversion=1)
        self.assertEqual(r["roman"], "V65")
        r = ct(key, root=5, type=7, inversion=3)
        self.assertEqual(r["roman"], "V42")


class TestInversions(unittest.TestCase):
    def test_first_inversion_triad(self):
        key = Key("D#", "minor")
        r = ct(key, root=1, inversion=1)
        self.assertEqual(r["label"], "D#m/F#")
        self.assertEqual(r["roman"], "i6")
        self.assertEqual(r["bass"][0] % 12, 6)  # F# in bass

    def test_second_inversion_triad(self):
        key = Key("C", "major")
        r = ct(key, root=1, inversion=2)
        self.assertEqual(r["roman"], "I64")
        self.assertEqual(r["label"], "C/G")


class TestAppliedChords(unittest.TestCase):
    def test_applied_dominant_triad(self):
        # Creep bar 3: root=6, applied=5 in G major -> B major, V/vi
        key = Key("G", "major")
        r = ct(key, root=6, applied=5)
        self.assertEqual([m % 12 for m, _ in r["tones"]], [11, 3, 6])
        self.assertEqual(r["label"], "B")
        self.assertEqual(r["roman"], "V/vi")

    def test_applied_dominant_seventh(self):
        key = Key("G", "major")
        r = ct(key, root=6, applied=5, type=7)
        self.assertEqual(r["label"], "B7")
        self.assertEqual(r["roman"], "V7/vi")


class TestBorrowedChords(unittest.TestCase):
    def test_borrowed_minor_iv(self):
        # Creep bar 7: degree 4 borrowed="minor" in G major -> Cm, iv
        key = Key("G", "major")
        r = ct(key, root=4, borrowed="minor")
        self.assertEqual([m % 12 for m, _ in r["tones"]], [0, 3, 7])
        self.assertEqual(r["label"], "Cm")
        self.assertIn("iv", r["roman"])

    def test_borrowed_mixolydian(self):
        key = Key("G", "major")
        r = ct(key, root=4, borrowed="mixolydian")
        self.assertEqual(r["label"], "C")


class TestSuspensionsAddsOmits(unittest.TestCase):
    def test_sus4(self):
        key = Key("G", "major")
        r = ct(key, root=1, suspensions=["4"])
        self.assertEqual(r["label"], "Gsus4")

    def test_sus4_roman(self):
        key = Key("C", "major")
        r = ct(key, root=4, suspensions=["4"])
        self.assertTrue(r["roman"].startswith("IV"))

    def test_add_and_omit(self):
        key = Key("C", "major")
        r = ct(key, root=1, adds=["9"], omits=["5"])
        self.assertNotIn("warnings", [w for w in r["warnings"]
                                     if "unhandled" in w])


class TestEnharmonics(unittest.TestCase):
    def test_flat_key_prefers_flats(self):
        key = Key("Eb", "major")
        self.assertTrue(prefers_flats(key))
        self.assertEqual(midi_to_name(63, prefer_flats=True), "Eb4")
        k, acc = vf_key(63, prefer_flats=True)
        self.assertEqual((k, acc), ("e/4", "b"))

    def test_sharp_key_prefers_sharps(self):
        key = Key("G", "major")
        self.assertFalse(prefers_flats(key))
        k, acc = vf_key(66, prefer_flats=False)
        self.assertEqual((k, acc), ("f/4", "#"))


if __name__ == "__main__":
    unittest.main()
