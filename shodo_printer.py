#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
書道3Dプリンター - GUIアプリケーション
漢字のストロークをSVGから抽出し、曲率に基づいて太さを調整、G-codeを生成
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import math
import re
import urllib.request
import urllib.parse
from xml.etree import ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import copy

# ==================== データ構造 ====================

@dataclass
class Point:
    """2D座標点"""
    x: float
    y: float

    def distance_to(self, other: 'Point') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

@dataclass
class StrokePoint:
    """ストローク上の点（太さ情報付き）"""
    x: float
    y: float
    width: float  # 線の太さ（射出量に影響）
    curvature: float = 0.0  # 曲率

@dataclass
class Stroke:
    """一つの筆画"""
    points: List[StrokePoint] = field(default_factory=list)
    stroke_type: str = "normal"  # normal, tome, hane, harai
    start_effect: str = "none"  # none, tome (入り)
    end_effect: str = "none"  # none, tome, hane, harai (終わり)

@dataclass
class Character:
    """一文字分のデータ"""
    char: str
    strokes: List[Stroke] = field(default_factory=list)
    original_svg_paths: List[str] = field(default_factory=list)

# ==================== SVGパス解析 ====================

class SVGPathParser:
    """SVGパスをパースして座標点に変換"""

    @staticmethod
    def parse_path(d: str) -> List[List[Point]]:
        """SVGパスのd属性をパースして座標リストに変換"""
        paths = []
        current_path = []
        current_x, current_y = 0.0, 0.0
        start_x, start_y = 0.0, 0.0

        # コマンドと引数を抽出
        commands = re.findall(r'([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+)', d)

        i = 0
        current_cmd = None

        while i < len(commands):
            token = commands[i][0] or commands[i][1]

            if token.isalpha():
                current_cmd = token
                i += 1
            else:
                # 数値を処理
                if current_cmd in ('M', 'm'):
                    x = float(token)
                    i += 1
                    y = float(commands[i][1]) if i < len(commands) else 0
                    i += 1

                    if current_cmd == 'm':
                        x += current_x
                        y += current_y

                    if current_path:
                        paths.append(current_path)
                    current_path = [Point(x, y)]
                    current_x, current_y = x, y
                    start_x, start_y = x, y
                    current_cmd = 'L' if current_cmd == 'M' else 'l'

                elif current_cmd in ('L', 'l'):
                    x = float(token)
                    i += 1
                    y = float(commands[i][1]) if i < len(commands) else 0
                    i += 1

                    if current_cmd == 'l':
                        x += current_x
                        y += current_y

                    current_path.append(Point(x, y))
                    current_x, current_y = x, y

                elif current_cmd == 'H':
                    x = float(token)
                    i += 1
                    current_path.append(Point(x, current_y))
                    current_x = x

                elif current_cmd == 'h':
                    dx = float(token)
                    i += 1
                    current_x += dx
                    current_path.append(Point(current_x, current_y))

                elif current_cmd == 'V':
                    y = float(token)
                    i += 1
                    current_path.append(Point(current_x, y))
                    current_y = y

                elif current_cmd == 'v':
                    dy = float(token)
                    i += 1
                    current_y += dy
                    current_path.append(Point(current_x, current_y))

                elif current_cmd in ('C', 'c'):
                    # 3次ベジェ曲線
                    coords = []
                    for _ in range(6):
                        if i < len(commands):
                            coords.append(float(commands[i][1] if commands[i][1] else commands[i][0]))
                            i += 1

                    if len(coords) == 6:
                        x1, y1, x2, y2, x, y = coords
                        if current_cmd == 'c':
                            x1 += current_x
                            y1 += current_y
                            x2 += current_x
                            y2 += current_y
                            x += current_x
                            y += current_y

                        # ベジェ曲線を離散化
                        bezier_points = SVGPathParser.cubic_bezier(
                            Point(current_x, current_y),
                            Point(x1, y1),
                            Point(x2, y2),
                            Point(x, y),
                            20
                        )
                        current_path.extend(bezier_points[1:])
                        current_x, current_y = x, y

                elif current_cmd in ('Q', 'q'):
                    # 2次ベジェ曲線
                    coords = []
                    for _ in range(4):
                        if i < len(commands):
                            coords.append(float(commands[i][1] if commands[i][1] else commands[i][0]))
                            i += 1

                    if len(coords) == 4:
                        x1, y1, x, y = coords
                        if current_cmd == 'q':
                            x1 += current_x
                            y1 += current_y
                            x += current_x
                            y += current_y

                        bezier_points = SVGPathParser.quadratic_bezier(
                            Point(current_x, current_y),
                            Point(x1, y1),
                            Point(x, y),
                            20
                        )
                        current_path.extend(bezier_points[1:])
                        current_x, current_y = x, y

                elif current_cmd in ('S', 's'):
                    # スムーズ3次ベジェ
                    coords = []
                    for _ in range(4):
                        if i < len(commands):
                            coords.append(float(commands[i][1] if commands[i][1] else commands[i][0]))
                            i += 1

                    if len(coords) == 4:
                        x2, y2, x, y = coords
                        if current_cmd == 's':
                            x2 += current_x
                            y2 += current_y
                            x += current_x
                            y += current_y

                        # 制御点を反射
                        x1 = current_x
                        y1 = current_y

                        bezier_points = SVGPathParser.cubic_bezier(
                            Point(current_x, current_y),
                            Point(x1, y1),
                            Point(x2, y2),
                            Point(x, y),
                            20
                        )
                        current_path.extend(bezier_points[1:])
                        current_x, current_y = x, y

                elif current_cmd in ('Z', 'z'):
                    if current_path:
                        current_path.append(Point(start_x, start_y))
                        paths.append(current_path)
                        current_path = []
                    current_x, current_y = start_x, start_y
                    i += 1
                else:
                    i += 1

        if current_path:
            paths.append(current_path)

        return paths

    @staticmethod
    def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, n: int) -> List[Point]:
        """3次ベジェ曲線を離散化"""
        points = []
        for i in range(n + 1):
            t = i / n
            t2 = t * t
            t3 = t2 * t
            mt = 1 - t
            mt2 = mt * mt
            mt3 = mt2 * mt

            x = mt3 * p0.x + 3 * mt2 * t * p1.x + 3 * mt * t2 * p2.x + t3 * p3.x
            y = mt3 * p0.y + 3 * mt2 * t * p1.y + 3 * mt * t2 * p2.y + t3 * p3.y
            points.append(Point(x, y))
        return points

    @staticmethod
    def quadratic_bezier(p0: Point, p1: Point, p2: Point, n: int) -> List[Point]:
        """2次ベジェ曲線を離散化"""
        points = []
        for i in range(n + 1):
            t = i / n
            mt = 1 - t

            x = mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x
            y = mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y
            points.append(Point(x, y))
        return points

# ==================== 漢字SVG取得（animCJK/KanjiVG） ====================

class KanjiSVGFetcher:
    """漢字のストロークSVGを取得"""

    ANIMCJK_BASE = "https://raw.githubusercontent.com/parsimonhi/animCJK/master/svgsJa/"
    KANJIVG_BASE = "https://raw.githubusercontent.com/KanjiVG/kanjivg/master/kanji/"

    @staticmethod
    def get_unicode_hex(char: str) -> str:
        """文字のUnicodeコードポイントを16進数で取得"""
        return format(ord(char), '05x')

    @staticmethod
    def fetch_from_animcjk(char: str) -> Optional[str]:
        """animCJKからSVGを取得"""
        hex_code = KanjiSVGFetcher.get_unicode_hex(char)
        url = f"{KanjiSVGFetcher.ANIMCJK_BASE}{hex_code}.svg"

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            print(f"animCJK fetch error: {e}")
            return None

    @staticmethod
    def fetch_from_kanjivg(char: str) -> Optional[str]:
        """KanjiVGからSVGを取得"""
        hex_code = KanjiSVGFetcher.get_unicode_hex(char)
        url = f"{KanjiSVGFetcher.KANJIVG_BASE}{hex_code}.svg"

        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            print(f"KanjiVG fetch error: {e}")
            return None

    @staticmethod
    def fetch_svg(char: str) -> Optional[str]:
        """SVGを取得（animCJK優先）"""
        svg = KanjiSVGFetcher.fetch_from_animcjk(char)
        if svg:
            return svg
        return KanjiSVGFetcher.fetch_from_kanjivg(char)

    @staticmethod
    def extract_stroke_paths(svg_content: str) -> List[str]:
        """SVGからストロークパスを抽出"""
        paths = []

        try:
            # 名前空間を処理
            svg_content = re.sub(r'xmlns[^"]*="[^"]*"', '', svg_content)
            root = ET.fromstring(svg_content)

            # すべてのpath要素を探す
            for elem in root.iter():
                if elem.tag.endswith('path') or elem.tag == 'path':
                    d = elem.get('d')
                    if d:
                        paths.append(d)
        except Exception as e:
            print(f"SVG parse error: {e}")

        return paths

# ==================== 曲率計算 ====================

class CurvatureCalculator:
    """曲率を計算し、太さを決定"""

    @staticmethod
    def calculate_curvature(p1: Point, p2: Point, p3: Point) -> float:
        """3点から曲率を計算"""
        # 外接円の半径の逆数として曲率を計算
        a = p1.distance_to(p2)
        b = p2.distance_to(p3)
        c = p3.distance_to(p1)

        if a < 0.001 or b < 0.001 or c < 0.001:
            return 0.0

        # 面積（ヘロンの公式）
        s = (a + b + c) / 2
        area_sq = s * (s - a) * (s - b) * (s - c)

        if area_sq <= 0:
            return 0.0

        area = math.sqrt(area_sq)

        # 曲率 = 4 * area / (a * b * c)
        curvature = 4 * area / (a * b * c)
        return curvature

    @staticmethod
    def points_to_stroke(points: List[Point],
                         base_width: float = 0.4,
                         curvature_factor: float = 5.0) -> Stroke:
        """座標点リストをStrokeに変換し、曲率に基づいて太さを計算"""
        stroke = Stroke()

        n = len(points)
        if n == 0:
            return stroke

        for i in range(n):
            curvature = 0.0

            if 0 < i < n - 1:
                curvature = CurvatureCalculator.calculate_curvature(
                    points[i-1], points[i], points[i+1]
                )

            # 曲率が大きいほど太く
            width = base_width * (1 + curvature * curvature_factor)
            width = min(width, base_width * 3)  # 最大3倍まで

            stroke.points.append(StrokePoint(
                x=points[i].x,
                y=points[i].y,
                width=width,
                curvature=curvature
            ))

        return stroke

    @staticmethod
    def apply_effects(stroke: Stroke) -> Stroke:
        """とめ・はね・はらいの効果を適用"""
        if not stroke.points:
            return stroke

        n = len(stroke.points)

        # 始点の効果（とめ/入り）
        if stroke.start_effect == "tome":
            # 最初の数点を太くする
            for i in range(min(5, n)):
                factor = 1.5 - 0.1 * i
                stroke.points[i].width *= factor

        # 終点の効果
        if stroke.end_effect == "tome":
            # 終わりを太くして止める
            for i in range(max(0, n - 5), n):
                factor = 1.0 + 0.1 * (i - (n - 5))
                stroke.points[i].width *= factor

        elif stroke.end_effect == "hane":
            # はね：急激に細くして跳ね上げ
            for i in range(max(0, n - 8), n):
                progress = (i - (n - 8)) / 8
                stroke.points[i].width *= (1 - progress * 0.8)
                # Y座標を少し上げる（跳ね上げ）
                stroke.points[i].y -= progress * 2

        elif stroke.end_effect == "harai":
            # はらい：徐々に細くする
            harai_start = max(0, n - n // 3)
            for i in range(harai_start, n):
                progress = (i - harai_start) / (n - harai_start)
                stroke.points[i].width *= (1 - progress * 0.9)

        return stroke

# ==================== G-code生成 ====================

class GCodeGenerator:
    """G-codeを生成"""

    def __init__(self):
        # プリンター設定（Bambu Lab A1 mini用）
        self.nozzle_diameter = 0.2  # mm
        self.layer_height = 0.06  # mm
        self.line_width = 0.22  # mm
        self.filament_diameter = 1.75  # mm
        self.flow_ratio = 0.98

        # 印刷設定
        self.print_speed = 30  # mm/s
        self.travel_speed = 150  # mm/s
        self.retract_length = 0.8  # mm
        self.retract_speed = 30  # mm/s

        # 位置設定
        self.bed_size_x = 180  # mm
        self.bed_size_y = 180  # mm
        self.z_height = 0.2  # 印刷高さ

        # スケール（SVG座標→実座標）
        self.scale = 0.1  # 1SVG単位 = 0.1mm
        self.offset_x = 90  # mm (中央)
        self.offset_y = 90  # mm (中央)

    def calculate_extrusion(self, distance: float, width: float) -> float:
        """押出量を計算"""
        # 断面積 = 線幅 × レイヤー高さ
        cross_section = width * self.layer_height
        # フィラメント断面積
        filament_area = math.pi * (self.filament_diameter / 2) ** 2
        # 押出長さ = 距離 × 断面積比 × フロー補正
        extrusion = distance * cross_section / filament_area * self.flow_ratio
        return extrusion

    def transform_point(self, p: StrokePoint) -> Tuple[float, float]:
        """SVG座標を実座標に変換"""
        x = p.x * self.scale + self.offset_x
        y = (109 - p.y) * self.scale + self.offset_y  # SVGはY軸反転
        return x, y

    def generate_header(self) -> str:
        """G-codeヘッダーを生成"""
        return f"""; Generated by Shodo 3D Printer
; Nozzle: {self.nozzle_diameter}mm
; Layer height: {self.layer_height}mm

; === Start G-code ===
G28 ; Home all axes
M104 S220 ; Set hotend temperature
M140 S60 ; Set bed temperature
M109 S220 ; Wait for hotend
M190 S60 ; Wait for bed
G92 E0 ; Reset extruder

G1 Z5 F3000 ; Lift nozzle
G1 X0 Y0 F{self.travel_speed * 60} ; Move to start
G1 Z{self.z_height} F1000 ; Lower to print height

; === Print Start ===
"""

    def generate_footer(self) -> str:
        """G-codeフッターを生成"""
        return f"""
; === Print End ===
G1 E-{self.retract_length} F{self.retract_speed * 60} ; Retract
G1 Z10 F3000 ; Lift nozzle
G1 X0 Y{self.bed_size_y} F{self.travel_speed * 60} ; Move to corner
M104 S0 ; Turn off hotend
M140 S0 ; Turn off bed
M84 ; Disable motors
; === End G-code ===
"""

    def generate_stroke(self, stroke: Stroke, e_position: float) -> Tuple[str, float]:
        """1ストローク分のG-codeを生成"""
        gcode = []
        current_e = e_position

        if not stroke.points:
            return "", current_e

        # 最初の点に移動（リトラクト→移動→デリトラクト）
        first_x, first_y = self.transform_point(stroke.points[0])
        gcode.append(f"G1 E{current_e - self.retract_length:.5f} F{self.retract_speed * 60} ; Retract")
        gcode.append(f"G0 X{first_x:.3f} Y{first_y:.3f} F{self.travel_speed * 60} ; Travel to stroke start")
        gcode.append(f"G1 E{current_e:.5f} F{self.retract_speed * 60} ; Unretract")

        # ストロークを描画
        for i in range(1, len(stroke.points)):
            prev = stroke.points[i - 1]
            curr = stroke.points[i]

            prev_x, prev_y = self.transform_point(prev)
            curr_x, curr_y = self.transform_point(curr)

            distance = math.sqrt((curr_x - prev_x)**2 + (curr_y - prev_y)**2)

            if distance > 0.01:  # 微小移動は無視
                # 太さに応じて押出量を調整
                extrusion = self.calculate_extrusion(distance, curr.width)
                current_e += extrusion

                # 速度も太さに応じて調整（太いところはゆっくり）
                speed_factor = 1.0 / (curr.width / self.line_width)
                speed = self.print_speed * speed_factor * 60
                speed = max(speed, 10 * 60)  # 最低速度

                gcode.append(f"G1 X{curr_x:.3f} Y{curr_y:.3f} E{current_e:.5f} F{speed:.0f}")

        return "\n".join(gcode), current_e

    def generate(self, characters: List[Character]) -> str:
        """全文字のG-codeを生成"""
        gcode_parts = [self.generate_header()]
        current_e = 0.0

        for char in characters:
            gcode_parts.append(f"\n; === Character: {char.char} ===")
            for i, stroke in enumerate(char.strokes):
                gcode_parts.append(f"; Stroke {i + 1}")
                stroke_gcode, current_e = self.generate_stroke(stroke, current_e)
                gcode_parts.append(stroke_gcode)

        gcode_parts.append(self.generate_footer())
        return "\n".join(gcode_parts)

# ==================== GUI ====================

class ShodoApp:
    """メインGUIアプリケーション"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("書道3Dプリンター")
        self.root.geometry("1400x900")

        self.characters: List[Character] = []
        self.selected_char_index = -1
        self.selected_stroke_index = -1
        self.selected_point_index = -1

        self.gcode_generator = GCodeGenerator()

        self.setup_ui()

    def setup_ui(self):
        """UIをセットアップ"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左パネル：入力と設定
        left_panel = ttk.Frame(main_frame, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # 文字入力
        input_frame = ttk.LabelFrame(left_panel, text="文字入力", padding=10)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        self.char_entry = ttk.Entry(input_frame, font=("", 24))
        self.char_entry.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(input_frame, text="パス抽出", command=self.extract_paths).pack(fill=tk.X)

        # ストローク一覧
        stroke_frame = ttk.LabelFrame(left_panel, text="ストローク一覧", padding=10)
        stroke_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.stroke_listbox = tk.Listbox(stroke_frame, font=("", 12))
        self.stroke_listbox.pack(fill=tk.BOTH, expand=True)
        self.stroke_listbox.bind('<<ListboxSelect>>', self.on_stroke_select)

        # ストローク効果設定
        effect_frame = ttk.LabelFrame(left_panel, text="効果設定", padding=10)
        effect_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(effect_frame, text="始点:").grid(row=0, column=0, sticky=tk.W)
        self.start_effect_var = tk.StringVar(value="none")
        start_combo = ttk.Combobox(effect_frame, textvariable=self.start_effect_var,
                                   values=["none", "tome"], state="readonly")
        start_combo.grid(row=0, column=1, sticky=tk.EW, padx=5)
        start_combo.bind('<<ComboboxSelected>>', self.on_effect_change)

        ttk.Label(effect_frame, text="終点:").grid(row=1, column=0, sticky=tk.W)
        self.end_effect_var = tk.StringVar(value="none")
        end_combo = ttk.Combobox(effect_frame, textvariable=self.end_effect_var,
                                 values=["none", "tome", "hane", "harai"], state="readonly")
        end_combo.grid(row=1, column=1, sticky=tk.EW, padx=5)
        end_combo.bind('<<ComboboxSelected>>', self.on_effect_change)

        effect_frame.columnconfigure(1, weight=1)

        # 太さ調整
        width_frame = ttk.LabelFrame(left_panel, text="太さ調整", padding=10)
        width_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(width_frame, text="基本太さ:").grid(row=0, column=0, sticky=tk.W)
        self.base_width_var = tk.DoubleVar(value=0.4)
        base_width_scale = ttk.Scale(width_frame, from_=0.1, to=1.0,
                                      variable=self.base_width_var,
                                      command=self.on_width_change)
        base_width_scale.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.base_width_label = ttk.Label(width_frame, text="0.40mm")
        self.base_width_label.grid(row=0, column=2)

        ttk.Label(width_frame, text="曲率係数:").grid(row=1, column=0, sticky=tk.W)
        self.curve_factor_var = tk.DoubleVar(value=5.0)
        curve_scale = ttk.Scale(width_frame, from_=0.0, to=20.0,
                                variable=self.curve_factor_var,
                                command=self.on_width_change)
        curve_scale.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.curve_factor_label = ttk.Label(width_frame, text="5.0")
        self.curve_factor_label.grid(row=1, column=2)

        width_frame.columnconfigure(1, weight=1)

        # G-code設定
        gcode_frame = ttk.LabelFrame(left_panel, text="G-code設定", padding=10)
        gcode_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(gcode_frame, text="スケール:").grid(row=0, column=0, sticky=tk.W)
        self.scale_var = tk.DoubleVar(value=0.1)
        scale_entry = ttk.Entry(gcode_frame, textvariable=self.scale_var, width=10)
        scale_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(gcode_frame, text="mm/SVG単位").grid(row=0, column=2, sticky=tk.W)

        ttk.Label(gcode_frame, text="レイヤー高:").grid(row=1, column=0, sticky=tk.W)
        self.layer_height_var = tk.DoubleVar(value=0.06)
        layer_combo = ttk.Combobox(gcode_frame, textvariable=self.layer_height_var,
                                   values=[0.06, 0.10, 0.14], width=8)
        layer_combo.grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(gcode_frame, text="mm").grid(row=1, column=2, sticky=tk.W)

        ttk.Label(gcode_frame, text="印刷速度:").grid(row=2, column=0, sticky=tk.W)
        self.speed_var = tk.IntVar(value=30)
        speed_entry = ttk.Entry(gcode_frame, textvariable=self.speed_var, width=10)
        speed_entry.grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Label(gcode_frame, text="mm/s").grid(row=2, column=2, sticky=tk.W)

        # 出力ボタン
        button_frame = ttk.Frame(left_panel)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="プレビュー更新",
                   command=self.update_preview).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="G-code生成",
                   command=self.generate_gcode).pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="G-code保存",
                   command=self.save_gcode).pack(fill=tk.X, pady=2)

        # 中央パネル：プレビュー
        center_panel = ttk.Frame(main_frame)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        preview_label = ttk.Label(center_panel, text="プレビュー")
        preview_label.pack()

        self.canvas = tk.Canvas(center_panel, bg="white", width=600, height=600)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind('<Button-1>', self.on_canvas_click)
        self.canvas.bind('<B1-Motion>', self.on_canvas_drag)

        # 右パネル：点の編集
        right_panel = ttk.Frame(main_frame, width=250)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)

        point_frame = ttk.LabelFrame(right_panel, text="選択点の編集", padding=10)
        point_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(point_frame, text="X座標:").grid(row=0, column=0, sticky=tk.W)
        self.point_x_var = tk.DoubleVar(value=0)
        self.point_x_entry = ttk.Entry(point_frame, textvariable=self.point_x_var, width=10)
        self.point_x_entry.grid(row=0, column=1, padx=5)
        self.point_x_entry.bind('<Return>', self.on_point_edit)

        ttk.Label(point_frame, text="Y座標:").grid(row=1, column=0, sticky=tk.W)
        self.point_y_var = tk.DoubleVar(value=0)
        self.point_y_entry = ttk.Entry(point_frame, textvariable=self.point_y_var, width=10)
        self.point_y_entry.grid(row=1, column=1, padx=5)
        self.point_y_entry.bind('<Return>', self.on_point_edit)

        ttk.Label(point_frame, text="太さ:").grid(row=2, column=0, sticky=tk.W)
        self.point_width_var = tk.DoubleVar(value=0.4)
        self.point_width_entry = ttk.Entry(point_frame, textvariable=self.point_width_var, width=10)
        self.point_width_entry.grid(row=2, column=1, padx=5)
        self.point_width_entry.bind('<Return>', self.on_point_edit)

        ttk.Button(point_frame, text="適用", command=self.on_point_edit).grid(row=3, column=0, columnspan=2, pady=5)

        # 点の追加/削除
        point_edit_frame = ttk.Frame(right_panel)
        point_edit_frame.pack(fill=tk.X)

        ttk.Button(point_edit_frame, text="点を追加", command=self.add_point).pack(fill=tk.X, pady=2)
        ttk.Button(point_edit_frame, text="点を削除", command=self.delete_point).pack(fill=tk.X, pady=2)

        # G-codeプレビュー
        gcode_preview_frame = ttk.LabelFrame(right_panel, text="G-codeプレビュー", padding=5)
        gcode_preview_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.gcode_text = tk.Text(gcode_preview_frame, font=("Courier", 9), width=30, height=20)
        gcode_scroll = ttk.Scrollbar(gcode_preview_frame, orient=tk.VERTICAL,
                                      command=self.gcode_text.yview)
        self.gcode_text.configure(yscrollcommand=gcode_scroll.set)
        self.gcode_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        gcode_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def extract_paths(self):
        """入力文字からパスを抽出"""
        text = self.char_entry.get().strip()
        if not text:
            messagebox.showwarning("警告", "文字を入力してください")
            return

        self.characters = []
        self.stroke_listbox.delete(0, tk.END)

        for char in text:
            svg_content = KanjiSVGFetcher.fetch_svg(char)

            if svg_content:
                paths = KanjiSVGFetcher.extract_stroke_paths(svg_content)
                character = Character(char=char, original_svg_paths=paths)

                for i, path_d in enumerate(paths):
                    point_lists = SVGPathParser.parse_path(path_d)
                    for points in point_lists:
                        if len(points) >= 2:
                            stroke = CurvatureCalculator.points_to_stroke(
                                points,
                                self.base_width_var.get(),
                                self.curve_factor_var.get()
                            )
                            character.strokes.append(stroke)
                            self.stroke_listbox.insert(tk.END,
                                f"{char} - 画{len(character.strokes)}")

                self.characters.append(character)
            else:
                # SVGが見つからない場合、簡単な代替を生成
                messagebox.showinfo("情報", f"'{char}'のSVGが見つかりません。手動でパスを設定してください。")
                character = Character(char=char)
                self.characters.append(character)

        self.update_preview()

    def on_stroke_select(self, event):
        """ストローク選択時"""
        selection = self.stroke_listbox.curselection()
        if not selection:
            return

        index = selection[0]

        # どの文字のどのストロークか計算
        stroke_count = 0
        for char_idx, char in enumerate(self.characters):
            for stroke_idx, stroke in enumerate(char.strokes):
                if stroke_count == index:
                    self.selected_char_index = char_idx
                    self.selected_stroke_index = stroke_idx
                    self.selected_point_index = -1

                    # 効果設定を更新
                    self.start_effect_var.set(stroke.start_effect)
                    self.end_effect_var.set(stroke.end_effect)

                    self.update_preview()
                    return
                stroke_count += 1

    def on_effect_change(self, event=None):
        """効果設定変更時"""
        if self.selected_char_index < 0 or self.selected_stroke_index < 0:
            return

        stroke = self.characters[self.selected_char_index].strokes[self.selected_stroke_index]
        stroke.start_effect = self.start_effect_var.get()
        stroke.end_effect = self.end_effect_var.get()

        # 効果を適用（元のストロークを再計算）
        char = self.characters[self.selected_char_index]
        if self.selected_stroke_index < len(char.original_svg_paths):
            path_d = char.original_svg_paths[self.selected_stroke_index]
            point_lists = SVGPathParser.parse_path(path_d)
            if point_lists:
                new_stroke = CurvatureCalculator.points_to_stroke(
                    point_lists[0],
                    self.base_width_var.get(),
                    self.curve_factor_var.get()
                )
                new_stroke.start_effect = stroke.start_effect
                new_stroke.end_effect = stroke.end_effect
                new_stroke = CurvatureCalculator.apply_effects(new_stroke)
                char.strokes[self.selected_stroke_index] = new_stroke

        self.update_preview()

    def on_width_change(self, event=None):
        """太さ設定変更時"""
        self.base_width_label.config(text=f"{self.base_width_var.get():.2f}mm")
        self.curve_factor_label.config(text=f"{self.curve_factor_var.get():.1f}")

        # 全ストロークを再計算
        for char in self.characters:
            for i, stroke in enumerate(char.strokes):
                if i < len(char.original_svg_paths):
                    path_d = char.original_svg_paths[i]
                    point_lists = SVGPathParser.parse_path(path_d)
                    if point_lists:
                        new_stroke = CurvatureCalculator.points_to_stroke(
                            point_lists[0],
                            self.base_width_var.get(),
                            self.curve_factor_var.get()
                        )
                        new_stroke.start_effect = stroke.start_effect
                        new_stroke.end_effect = stroke.end_effect
                        new_stroke = CurvatureCalculator.apply_effects(new_stroke)
                        char.strokes[i] = new_stroke

        self.update_preview()

    def on_canvas_click(self, event):
        """キャンバスクリック時"""
        if self.selected_char_index < 0 or self.selected_stroke_index < 0:
            return

        stroke = self.characters[self.selected_char_index].strokes[self.selected_stroke_index]

        # クリック位置に最も近い点を探す
        canvas_scale = 5  # キャンバス表示スケール
        offset_x = 50
        offset_y = 50

        min_dist = float('inf')
        closest_idx = -1

        for i, p in enumerate(stroke.points):
            px = p.x * canvas_scale + offset_x
            py = p.y * canvas_scale + offset_y
            dist = math.sqrt((event.x - px)**2 + (event.y - py)**2)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i

        if min_dist < 20:  # 20ピクセル以内
            self.selected_point_index = closest_idx
            p = stroke.points[closest_idx]
            self.point_x_var.set(round(p.x, 2))
            self.point_y_var.set(round(p.y, 2))
            self.point_width_var.set(round(p.width, 3))
            self.update_preview()

    def on_canvas_drag(self, event):
        """キャンバスドラッグ時"""
        if (self.selected_char_index < 0 or
            self.selected_stroke_index < 0 or
            self.selected_point_index < 0):
            return

        stroke = self.characters[self.selected_char_index].strokes[self.selected_stroke_index]

        canvas_scale = 5
        offset_x = 50
        offset_y = 50

        # 新しい座標を計算
        new_x = (event.x - offset_x) / canvas_scale
        new_y = (event.y - offset_y) / canvas_scale

        stroke.points[self.selected_point_index].x = new_x
        stroke.points[self.selected_point_index].y = new_y

        self.point_x_var.set(round(new_x, 2))
        self.point_y_var.set(round(new_y, 2))

        self.update_preview()

    def on_point_edit(self, event=None):
        """点の座標/太さ編集"""
        if (self.selected_char_index < 0 or
            self.selected_stroke_index < 0 or
            self.selected_point_index < 0):
            return

        stroke = self.characters[self.selected_char_index].strokes[self.selected_stroke_index]
        p = stroke.points[self.selected_point_index]

        p.x = self.point_x_var.get()
        p.y = self.point_y_var.get()
        p.width = self.point_width_var.get()

        self.update_preview()

    def add_point(self):
        """選択点の後に新しい点を追加"""
        if self.selected_char_index < 0 or self.selected_stroke_index < 0:
            return

        stroke = self.characters[self.selected_char_index].strokes[self.selected_stroke_index]

        if self.selected_point_index < 0:
            insert_idx = len(stroke.points)
        else:
            insert_idx = self.selected_point_index + 1

        # 前後の点の中間に追加
        if insert_idx > 0 and insert_idx <= len(stroke.points):
            prev = stroke.points[insert_idx - 1]
            if insert_idx < len(stroke.points):
                next_p = stroke.points[insert_idx]
                new_x = (prev.x + next_p.x) / 2
                new_y = (prev.y + next_p.y) / 2
                new_width = (prev.width + next_p.width) / 2
            else:
                new_x = prev.x + 5
                new_y = prev.y
                new_width = prev.width
        else:
            new_x = 50
            new_y = 50
            new_width = self.base_width_var.get()

        new_point = StrokePoint(x=new_x, y=new_y, width=new_width)
        stroke.points.insert(insert_idx, new_point)

        self.selected_point_index = insert_idx
        self.update_preview()

    def delete_point(self):
        """選択点を削除"""
        if (self.selected_char_index < 0 or
            self.selected_stroke_index < 0 or
            self.selected_point_index < 0):
            return

        stroke = self.characters[self.selected_char_index].strokes[self.selected_stroke_index]

        if len(stroke.points) > 2:  # 最低2点は必要
            del stroke.points[self.selected_point_index]
            self.selected_point_index = min(self.selected_point_index, len(stroke.points) - 1)
            self.update_preview()

    def update_preview(self):
        """プレビューを更新"""
        self.canvas.delete("all")

        canvas_scale = 5
        offset_x = 50
        offset_y = 50

        # グリッドを描画
        for i in range(0, 600, 50):
            self.canvas.create_line(i, 0, i, 600, fill="#f0f0f0")
            self.canvas.create_line(0, i, 600, i, fill="#f0f0f0")

        # 各文字のストロークを描画
        for char_idx, char in enumerate(self.characters):
            for stroke_idx, stroke in enumerate(char.strokes):
                is_selected = (char_idx == self.selected_char_index and
                              stroke_idx == self.selected_stroke_index)

                # ストロークを描画（太さを視覚化）
                for i in range(len(stroke.points) - 1):
                    p1 = stroke.points[i]
                    p2 = stroke.points[i + 1]

                    x1 = p1.x * canvas_scale + offset_x
                    y1 = p1.y * canvas_scale + offset_y
                    x2 = p2.x * canvas_scale + offset_x
                    y2 = p2.y * canvas_scale + offset_y

                    # 太さを視覚化（幅に応じた太さで描画）
                    width = (p1.width + p2.width) / 2 * canvas_scale * 2

                    color = "#ff0000" if is_selected else "#000000"
                    self.canvas.create_line(x1, y1, x2, y2,
                                           width=max(1, width),
                                           fill=color,
                                           capstyle=tk.ROUND)

                # 選択されたストロークの点を表示
                if is_selected:
                    for i, p in enumerate(stroke.points):
                        px = p.x * canvas_scale + offset_x
                        py = p.y * canvas_scale + offset_y

                        if i == self.selected_point_index:
                            # 選択された点
                            self.canvas.create_oval(px-6, py-6, px+6, py+6,
                                                   fill="#00ff00", outline="#008800")
                        else:
                            # 通常の点
                            self.canvas.create_oval(px-4, py-4, px+4, py+4,
                                                   fill="#0088ff", outline="#004488")

        # 文字を表示
        if self.characters:
            text = "".join(c.char for c in self.characters)
            self.canvas.create_text(300, 550, text=text, font=("", 24), fill="#888888")

    def generate_gcode(self):
        """G-codeを生成してプレビュー表示"""
        if not self.characters:
            messagebox.showwarning("警告", "先に文字を入力してパスを抽出してください")
            return

        # 設定を更新
        self.gcode_generator.scale = self.scale_var.get()
        self.gcode_generator.layer_height = self.layer_height_var.get()
        self.gcode_generator.print_speed = self.speed_var.get()

        gcode = self.gcode_generator.generate(self.characters)

        self.gcode_text.delete(1.0, tk.END)
        self.gcode_text.insert(tk.END, gcode)

        messagebox.showinfo("完了", "G-codeを生成しました")

    def save_gcode(self):
        """G-codeをファイルに保存"""
        gcode = self.gcode_text.get(1.0, tk.END).strip()
        if not gcode:
            self.generate_gcode()
            gcode = self.gcode_text.get(1.0, tk.END).strip()

        if not gcode:
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".gcode",
            filetypes=[("G-code files", "*.gcode"), ("All files", "*.*")],
            initialfile="shodo_output.gcode"
        )

        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(gcode)
            messagebox.showinfo("完了", f"G-codeを保存しました:\n{filename}")

# ==================== メイン ====================

def main():
    root = tk.Tk()
    app = ShodoApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
