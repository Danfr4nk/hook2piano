# hook2piano

TheoryTab → one-page piano sheet. Fetches a [Hooktheory](https://www.hooktheory.com/theorytab) chord+melody analysis and renders it as a printable grand-staff score: **left hand plays the chords, right hand plays the melody**, with chord symbols and Roman numerals on top.

## 📱 Web app (phone-friendly)

**https://danfr4nk.github.io/hook2piano/** — paste a TheoryTab URL or tab ID, pick a section, get the score. The full Python engine runs in your browser via Pyodide; the tab JSON comes straight from Hooktheory's public API (CORS-open). Nothing to install.

## How it works

1. **Fetch** — a TheoryTab song page embeds one player per analyzed section (`TheoryTabs("tab-…")`). Each player exposes its Hookpad project data through Hooktheory's public, unauthenticated project endpoint (`/v1/songs/public/<tab_id>`), which returns the full chord/note/key/tempo/meter JSON.
2. **Decode** — Hooktheory stores melody and chords in *relative* notation (scale degrees + octave + accidental against the key's scale). `theory.py` resolves these to absolute pitches, spells note names diatonically per key, and builds chord tones, labels, Roman numerals (with applied/borrowed/inversion figures), and compact close-position LH voicings.
3. **Render** — either a plain-text bar-by-bar lead sheet or a self-contained HTML page with a VexFlow grand staff (vendored, no network needed), one printable section per page.

## Install

```bash
pip install .
# or just run from the source tree:
python -m hook2piano.cli --text <url>
```

Requires Python 3.10+ and `requests`.

## Use

```bash
# Printable score (HTML, open in a browser and print / save as PDF)
hook2piano https://www.hooktheory.com/theorytab/view/radiohead/creep

# Only one section of the song
hook2piano -s "verse" <url>

# Text lead sheet to the terminal
hook2piano --text https://www.hooktheory.com/theorytab/view/tlc/this-is-how-it-works
```

Text output looks like:

```
Creep — Intro and Verse
Key G major | 95 BPM | 4/4

bar  1: LH [1] G (I)
        voicing: G2 B2 D3
        RH: G2(8) D3(8) G3(q) G3(8) B3(q) G3(8)
...
bar  7: LH [1] Cm (iv (bor. minor))
        voicing: C2 Eb2 G2
        RH: G3(8) Eb4(8) C4(8) G3(8) ...
```

## Layout

- `hook2piano/fetch.py` — scrape section IDs from a TheoryTab page, fetch public project JSON
- `hook2piano/theory.py` — scales, relative-note decoding, chord construction/naming/Roman numerals, LH voicings
- `hook2piano/parse.py` — absolute-pitch chord/note events, per-measure splitting (`split_measures`)
- `hook2piano/render_text.py` — text lead sheet
- `hook2piano/render_html.py` — self-contained VexFlow grand-staff HTML
- `vendor/vexflow.js` — vendored VexFlow 4.2.2
- `tests/` — unit tests (melody ranges, progressions, chord qualities, inversions, borrowed/applied)
- `examples/` — rendered output samples

## Notes & limits

- Chord events that cross barlines are clipped at the barline (v1: no ties across bars).
- LH voicings are a reduction: bass note + close-position chord tones above — playable, not literal.
- TheoryTab analyses are user-contributed; the tool trusts the tab's key/degree data as-is.
- Key changes mid-section are supported (each event is decoded against the key in force at its beat).

## License

MIT
