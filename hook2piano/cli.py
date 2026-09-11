"""CLI for hook2piano."""

import argparse
import os
import sys

from . import fetch, parse
from . import render_text


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="hook2piano",
        description="Turn a Hooktheory TheoryTab into a one-page piano sheet "
                    "(LH chords + RH melody).")
    ap.add_argument("url", help="TheoryTab song URL, e.g. "
                    "https://www.hooktheory.com/theorytab/view/tlc/this-is-how-it-works")
    ap.add_argument("--section", "-s", default=None,
                    help="only render this section (substring match, case-insensitive)")
    ap.add_argument("--text", "-t", action="store_true",
                    help="print the text lead sheet instead of writing HTML")
    ap.add_argument("-o", "--out", default=None,
                    help="output HTML path (default: <song>.html in cwd)")
    args = ap.parse_args(argv)

    print("fetching sections…", file=sys.stderr)
    sections = fetch.song_sections(args.url)
    print(f"  found {len(sections)} section(s): " +
          ", ".join(n for n, _ in sections), file=sys.stderr)
    if args.section:
        sections = [(n, t) for n, t in sections
                    if args.section.lower() in n.lower()]
        if not sections:
            sys.exit(f"no section matching {args.section!r}")

    parsed = []
    for name, tid in sections:
        print(f"  fetching tab {tid} ({name})…", file=sys.stderr)
        proj = fetch.fetch_tab(tid)
        parsed.append(parse.parse_section(name, proj))

    if args.text:
        print(render_text.render(parsed))
        return

    from . import render_html
    out = args.out or (parsed[0].title.lower().replace(" ", "-") + ".html")
    html = render_html.render(parsed)
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {os.path.abspath(out)}", file=sys.stderr)


if __name__ == "__main__":
    main()
