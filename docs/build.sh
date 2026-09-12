#!/bin/bash
# Assemble the web harness: copies the Python engine + vendored VexFlow into docs/.
# Run from the repo root after changing hook2piano/*.py.
set -e
cd "$(dirname "$0")/.."
mkdir -p docs/py/hook2piano docs/vendor
cp hook2piano/*.py docs/py/hook2piano/
cp vendor/vexflow.js docs/vendor/
python3 - <<'EOF'
import re
src = open('hook2piano/render_html.py').read()
m = re.search(r'<script>\n\(function\(\)\{\n(.*)\n\}\)\(\);\n</script>', src, re.S)
js = m.group(1)
head, tail = js.split('const root = document.getElementById("score");', 1)
tail = tail.strip()
assert tail.startswith('SONG.sections.forEach'), tail[:60]
out = ['"use strict";',
       '/* Extracted from hook2piano/render_html.py — do not hand-edit; rerun docs/build.sh */',
       'window.H2P = window.H2P || {};']
# drop the IIFE's inner "use strict";
first, *rest = head.split('\n', 1)
assert first.strip() == '"use strict";', first
out.append(rest[0].rstrip())
out.append('window.H2P.renderSong = function(SONG, mountEl){')
out.append('  const root = mountEl;')
out.append('  root.innerHTML = "";')
for line in tail.split('\n'):
    out.append('  ' + line if line.strip() else line)
out.append('};')
open('docs/render.js', 'w').write('\n'.join(out) + '\n')
print("regenerated docs/render.js")
EOF
echo "docs/ assembled"
