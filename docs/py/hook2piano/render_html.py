"""Render sections as a printable one-page-per-section piano score.

Uses a vendored VexFlow build (vendor/vexflow.js, inlined so the output HTML
is fully self-contained). Grand staff per system: RH melody on treble,
LH chord voicings on bass, chord symbols annotated above.
"""

import json
import os

from .parse import split_measures
from .theory import key_signature

_VENDOR = os.path.join(os.path.dirname(__file__), "..", "vendor", "vexflow.js")


def sections_to_js(sections):
    """Convert parsed Sections to the JSON-serializable SONG structure the
    VexFlow renderer consumes. Shared by the CLI and the web harness
    (which calls this from Pyodide)."""
    js_sections = []
    for s in sections:
        js_sections.append({
            "name": s.name, "title": s.title,
            "keySig": key_signature(s.key),
            "keyName": f"{s.key.tonic} {s.key.scale}",
            "bpm": s.bpm, "beatsPerMeasure": s.beats_per_measure,
            "measures": split_measures(s),
        })
    return {"sections": js_sections}


def render(sections):
    with open(_VENDOR) as f:
        vexflow = f.read()

    data = json.dumps(sections_to_js(sections))

    return _PAGE.replace("__VEXFLOW__", vexflow).replace("__DATA__", data)


_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>hook2piano</title>
<style>
  body { font-family: Georgia, serif; margin: 0; padding: 12px 18px; color: #111; }
  .section { page-break-after: always; }
  .section:last-child { page-break-after: avoid; }
  h1 { font-size: 22px; margin: 0 0 2px; }
  h2 { font-size: 15px; font-weight: normal; margin: 0 0 10px; color: #444; }
  .prog { font-size: 12px; color: #555; margin: 0 0 8px; }
  @media print {
    body { padding: 0; }
    .noprint { display: none; }
  }
</style>
</head><body>
<div class="noprint" style="margin-bottom:10px;font-size:13px;color:#666">
  hook2piano &mdash; print this page (or save as PDF) for the one-page piano sheet.
  Treble = right hand melody, Bass = left hand chords, chord symbols on top.
</div>
<div id="score"></div>
<script>__VEXFLOW__</script>
<script>const SONG = __DATA__;</script>
<script>
(function(){
"use strict";
const VF = (window.Vex && window.Vex.Flow) || window.Vex;
const W = 1020, SYS_H = 200, TOP = 46;

// ---- data helpers ----
function decompose(beats){
  const vals = [[4,"w"],[2,"h"],[1,"q"],[0.5,"8"],[0.25,"16"],[0.125,"32"]];
  let rem = Math.round(beats*1e6)/1e6;
  const out = [];
  while(rem > 1e-6){
    let placed = false;
    for(const [v,n] of vals){
      for(const dots of [2,1,0]){
        const want = v*(2-Math.pow(0.5,dots));
        if(want <= rem+1e-6){ out.push([n,dots]); rem = Math.round((rem-want)*1e6)/1e6; placed = true; break; }
      }
      if(placed) break;
    }
    if(!placed){ out.push(["32",0]); rem = 0; }
  }
  return out;
}
function vfDur(base, dots, isRest){
  return base + (isRest ? "r" : "") + (dots ? "d".repeat(dots) : "");
}

// Build StaveNotes for one event; returns {notes, ties}.
// ev = {dur, keys:[{key,acc}...] | null for rest}
function eventNotes(ev, clef){
  const parts = decompose(ev.dur);
  const notes = parts.map(([base, dots]) => {
    const isRest = !ev.keys;
    const sn = new VF.StaveNote({
      clef: clef,
      keys: isRest ? [(clef === "treble" ? "b/4" : "d/3")] : ev.keys.map(k => k.key),
      duration: vfDur(base, dots, isRest),
      auto_stem: true
    });
    if(!isRest) ev.keys.forEach((k, i) => { if(k.acc) sn.addModifier(new VF.Accidental(k.acc), i); });
    for(let d = 0; d < dots; d++) VF.Dot.buildAndAttach([sn], {all_voices: false});
    return sn;
  });
  const ties = [];
  for(let i = 0; i + 1 < notes.length; i++){
    const nKeys = notes[i].getKeys().length;
    ties.push(new VF.StaveTie({
      first_note: notes[i], last_note: notes[i+1],
      first_indexes: [...Array(nKeys).keys()],
      last_indexes: [...Array(nKeys).keys()]
    }));
  }
  return {notes, ties};
}

// Fill a full measure: events = [{beat, dur, keys|null}], returns {notes, ties, starts}
// starts: [{beat, index}] first StaveNote index of each non-rest event
function fillMeasure(events, clef, totalBeats){
  const notes = [], ties = [], starts = [];
  let cursor = 0;
  const sorted = [...events].sort((a,b) => a.beat - b.beat);
  for(const ev of sorted){
    if(ev.beat > cursor + 1e-6){
      const r = eventNotes({dur: ev.beat - cursor, keys: null}, clef);
      notes.push(...r.notes); ties.push(...r.ties);
      cursor = ev.beat;
    }
    const r = eventNotes(ev, clef);
    if(ev.keys) starts.push({beat: ev.beat, index: notes.length, label: ev.label, roman: ev.roman});
    notes.push(...r.notes); ties.push(...r.ties);
    cursor = ev.beat + ev.dur;
  }
  if(cursor < totalBeats - 1e-6){
    const r = eventNotes({dur: totalBeats - cursor, keys: null}, clef);
    notes.push(...r.notes); ties.push(...r.ties);
  }
  return {notes, ties, starts};
}

function annotateChordSymbols(tStarts, bStarts, tNotes, bNotes, chords){
  chords.forEach(c => {
    const text = c.label + (c.roman ? " (" + c.roman + ")" : "");
    const ann = new VF.Annotation(text);
    ann.setFont("Georgia", 11, "bold");
    ann.setVerticalJustification(VF.AnnotationVerticalJustify.TOP);
    const hit = tStarts.find(s => Math.abs(s.beat - c.beat) < 1e-6);
    if(hit && tNotes[hit.index]){ tNotes[hit.index].addModifier(ann, 0); return; }
    const bhit = bStarts.find(s => Math.abs(s.beat - c.beat) < 1e-6);
    if(bhit && bNotes[bhit.index]) bNotes[bhit.index].addModifier(ann, 0);
  });
}

const root = document.getElementById("score");
SONG.sections.forEach(sec => {
  const div = document.createElement("div");
  div.className = "section";
  const prog = [...new Set(sec.measures.flatMap(m => m.chords.map(c => c.label)))].join(" \u2013 ");
  div.innerHTML =
    "<h1>" + sec.title + ' <span style="font-weight:normal;font-size:16px">&mdash; ' + sec.name + "</span></h1>" +
    "<h2>Key of " + sec.keyName + " &nbsp;|&nbsp; " + sec.bpm + " BPM &nbsp;|&nbsp; " + sec.beatsPerMeasure + "/4</h2>" +
    '<div class="prog">Progression: ' + prog + "</div>";
  root.appendChild(div);

  const totalM = sec.measures.length;
  const systems = Math.min(5, Math.max(1, Math.ceil(totalM / 5)));
  const mps = Math.ceil(totalM / systems);
  const renderer = new VF.Renderer(div, VF.Renderer.Backends.SVG);
  renderer.resize(W, TOP + systems * SYS_H + 20);
  const ctx = renderer.getContext();

  for(let s = 0; s < systems; s++){
    const midx = [];
    for(let i = 0; i < mps && s * mps + i < totalM; i++) midx.push(s * mps + i);
    const y = TOP + s * SYS_H;
    const mw = (W - 20) / midx.length;
    midx.forEach((mi, k) => {
      const m = sec.measures[mi];
      const x = 10 + k * mw;
      const ts = new VF.Stave(x, y, mw);
      const bs = new VF.Stave(x, y + 100, mw);
      if(k === 0){
        ts.addClef("treble").addKeySignature(sec.keySig).addTimeSignature(sec.beatsPerMeasure + "/4");
        bs.addClef("bass").addKeySignature(sec.keySig).addTimeSignature(sec.beatsPerMeasure + "/4");
        const brace = new VF.StaveConnector(ts, bs);
        brace.setType(VF.StaveConnector.type.BRACE); brace.setContext(ctx).draw();
        const line = new VF.StaveConnector(ts, bs);
        line.setType(VF.StaveConnector.type.SINGLE_LEFT); line.setContext(ctx).draw();
      }
      ts.setContext(ctx).draw();
      bs.setContext(ctx).draw();
      ctx.save();
      ctx.setFont("Georgia", 9, "");
      ctx.fillStyle = "#999";
      ctx.fillText(String(mi + 1), x + 5, y - 10);
      ctx.restore();

      const trebleEvents = m.notes.map(n => ({
        beat: n.beat, dur: n.dur,
        keys: n.midi == null ? null : [{key: n.key, acc: n.acc}]
      }));
      const bassEvents = m.chords.map(c => ({
        beat: c.beat, dur: c.dur, label: c.label, roman: c.roman,
        keys: c.vfkeys.map(([key, acc]) => ({key, acc}))
      }));

      const t = fillMeasure(trebleEvents, "treble", sec.beatsPerMeasure);
      const b = fillMeasure(bassEvents, "bass", sec.beatsPerMeasure);
      annotateChordSymbols(t.starts, b.starts, t.notes, b.notes, m.chords);

      const tv = new VF.Voice({num_beats: sec.beatsPerMeasure, beat_value: 4}).setStrict(false);
      const bv = new VF.Voice({num_beats: sec.beatsPerMeasure, beat_value: 4}).setStrict(false);
      tv.addTickables(t.notes);
      bv.addTickables(b.notes);
      new VF.Formatter().joinVoices([tv]).joinVoices([bv]).format([tv, bv], mw - 80);
      tv.draw(ctx, ts);
      bv.draw(ctx, bs);
      t.ties.forEach(tie => tie.setContext(ctx).draw());
      b.ties.forEach(tie => tie.setContext(ctx).draw());
      try {
        VF.Beam.generateBeams(t.notes, {groups: [new VF.Fraction(1, 4)]})
          .forEach(bm => bm.setContext(ctx).draw());
      } catch(e) { /* unbeamed fallback is fine */ }
    });
  }
});
})();
</script>
</body></html>
"""
