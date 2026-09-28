# shodo-printer — 書道3Dプリンター

Turns kanji **stroke data into brush-like calligraphy drawn by a 3D printer**. Each stroke is taken from stroke-order SVGs, its width is varied by curvature (like pressure on a brush), and the result is written as single-layer G-code for a small FDM printer (Bambu Lab A1 mini, 0.2 mm nozzle).

漢字の筆順データからストロークを取り出し、曲率に応じて太さを変えて、筆で書いたような文字を 3D プリンタで描く G-code を作ります。

## Status

**Prototype / experiment.** Two independent implementations of the same idea: the browser version (`index.html`) is the more complete one; the Python/tkinter version is an earlier, simpler take. No tests. Whether the output prints well is untested beyond the author's own experiments.

✅ **Works**
- Fetch stroke SVGs for typed characters from animCJK (Japanese set) with KanjiVG as fallback (needs internet)
- Parse SVG paths (lines, cubic / quadratic Béziers) into point sequences; width from local curvature × a curvature factor
- Per-stroke start/end effects: *tome* (入り/止め), *hane* (はね), *harai* (はらい taper)
- Preview, stroke selection, and point editing (drag / add / delete) in both versions
- G-code export (`.gcode`) with extrusion computed from width × layer height

🚧 **Partial or rough**
- **Browser version**: horizontal / vertical (縦書き) layout, character size / spacing / line spacing / chars per line, drag-to-move, layer height & Z height, speed, optional retraction, and a Bambu-style start G-code block. Output is plain `.gcode`; how it is sent to the A1 mini is up to you (untested paths)
- **Python version**: generic Marlin-style start/end G-code (`G28`, `M104`, …) rather than Bambu's; all settings hard-coded in `GCodeGenerator`

📝 **Not implemented yet**
- Multi-layer / raised-relief output — everything is a single layer (`total layer number: 1`)
- Reading `printer_config.json` — neither version loads it; it documents the intended profiles only
- Offline stroke data / caching

⚠️ **Known issues & limitations**
- Python version: every character is drawn at the same bed position (fixed centre offset), so multi-character input overlaps; use the browser version for text
- Python version: extrusion is computed for a 0.06 mm layer while the nozzle is placed at Z 0.2 mm — expect thin lines unless you edit `GCodeGenerator`
- Python version: changing the width sliders recomputes strokes from the SVG, discarding manual point edits
- Bed size fixed to 180 × 180 mm (A1 mini); other printers need code changes
- Characters missing from both stroke sources can't be drawn (the app asks you to add points manually)

## Background

Made in December 2025 as a personal experiment in making a 3D printer "write" calligraphy.

## Files

- `index.html` — browser version (recommended)
- `shodo_printer.py` — desktop GUI (Python 3 / tkinter, standard library only)
- `printer_config.json` — intended printer & quality profiles (fine 0.06 mm / standard 0.10 mm / draft 0.14 mm); not read by the code yet

## Usage

```bash
open index.html              # or any browser; needs internet for stroke data
python3 shodo_printer.py     # desktop version
```

Type characters, extract strokes, adjust width / effects / layout, export G-code, then print.

## Stroke data

Stroke SVGs are **downloaded at runtime**, not bundled:
- [KanjiVG](https://github.com/KanjiVG/kanjivg) — © Ulrich Apel, CC BY-SA 3.0
- [animCJK](https://github.com/parsimonhi/animCJK) — see that repository for its license

Please respect those licenses when you share printed output or derived data.

## Related

- [bambu-midi-music](https://github.com/bob-takuya/bambu-midi-music) — another "make a Bambu printer do something unusual" experiment (play MIDI on its buzzer)

## License

Code: MIT — see [LICENSE](LICENSE). (Stroke data belongs to the projects above.)
