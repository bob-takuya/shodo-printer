# shodo-printer — 書道3Dプリンター

Turns kanji **stroke data into brush-like 3D-printed calligraphy**. Each stroke is taken from stroke-order SVGs, its width is varied by curvature (like pressure on a brush), and the result is written as G-code for a small FDM printer.
Made in December 2025.

漢字の筆順データからストロークを取り出し、曲率に応じて太さを変えて、筆で書いたような文字を 3D プリントする G-code を作ります。

- `shodo_printer.py` — desktop GUI (Python / tkinter)
- `index.html` — browser version
- `printer_config.json` — printer & quality profiles (default: Bambu Lab A1 mini, 0.2 mm nozzle; fine 0.06 mm / standard 0.10 mm layers)

## Usage
```bash
python3 shodo_printer.py      # or open index.html in a browser
```
Type characters, choose a profile, export G-code, print.

## Stroke data
Stroke SVGs are **downloaded at runtime**, not bundled:
- [KanjiVG](https://github.com/KanjiVG/kanjivg) — © Ulrich Apel, CC BY-SA 3.0
- [animCJK](https://github.com/parsimonhi/animCJK) — see that repository for its license

Please respect those licenses when you share printed output or derived data.

## License
Code: MIT — see [LICENSE](LICENSE). (Stroke data belongs to the projects above.)
