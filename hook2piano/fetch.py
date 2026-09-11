"""Fetch TheoryTab data from hooktheory.com.

A TheoryTab song page (https://www.hooktheory.com/theorytab/view/<artist>/<song>)
embeds one player per analyzed section. Each player carries an opaque tab id;
the player's own data endpoint is:

    GET https://api.hooktheory.com/v1/songs/public/<tab_id>?fields=ID,xmlData,song,jsonData

which returns the full Hookpad project (chords + melody) as JSON. No auth
needed. Section names come from the headings preceding each player div.
"""

import json
import re
import urllib.request

TAB_ID_RE = re.compile(r'TheoryTabs\("tab-([^"]+)"')
DIV_RE = re.compile(r'<div id="tab-([^"]+)">')
SONG_API = "https://api.hooktheory.com/v1/songs/public/{tid}?fields=ID,xmlData,song,jsonData"
UA = {"User-Agent": "hook2piano/0.1 (+https://github.com/Danfr4nk/hook2piano)"}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def song_sections(page_url):
    """Return [(section_name, tab_id), ...] in page order for a theorytab URL."""
    html = _get(page_url).decode("utf-8", "replace")
    ids = TAB_ID_RE.findall(html)
    # Section name: last short heading-ish text before the player div.
    sections = []
    for m in DIV_RE.finditer(html):
        tid = m.group(1)
        before = html[max(0, m.start() - 3000):m.start()]
        texts = [t.strip() for t in re.findall(r">([^<>]{1,60})<", before)]
        texts = [t for t in texts if t and "Open In Hookpad" not in t]
        name = texts[-1] if texts else f"Section {len(sections) + 1}"
        # strip "Artist – " prefix if present
        if "–" in name:
            name = name.split("–")[-1].strip()
        sections.append((name, tid))
    # fall back to raw id order if div parsing missed
    if not sections:
        sections = [(f"Section {i+1}", tid) for i, tid in enumerate(ids)]
    return sections


def fetch_tab(tid):
    """Return the Hookpad project dict (parsed jsonData) for a tab id."""
    raw = _get(SONG_API.format(tid=tid))
    d = json.loads(raw)
    project = json.loads(d["jsonData"])
    project["_song_title"] = d.get("song", "")
    project["_tab_id"] = tid
    return project
