"""Identidade visual: paleta escura e folha de estilo (QSS) usada em toda a interface."""

# Paleta
BG = "#0A0F1F"
HEADER = "#0E1630"
CARD = "#111A33"
CARD_ALT = "#0D1429"
BORDER = "#1E2A4A"
TRACK = "#1B2745"
TEXT = "#E6EAF5"
MUTED = "#8B97B5"
CYAN = "#22D3EE"
GREEN = "#34D399"
AMBER = "#FBBF24"
RED = "#F87171"
PURPLE = "#A78BFA"
BIT_OFF = "#0B1226"
BIT_OFF_BORDER = "#25335A"

MONO = '"Consolas", "DejaVu Sans Mono", "Menlo", monospace'

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", "Ubuntu", "Helvetica Neue", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; }}

QFrame#header {{ background: {HEADER}; border-bottom: 1px solid {BORDER}; }}
QLabel#appTitle {{ font-size: 15pt; font-weight: 700; color: {TEXT}; }}
QLabel#appSub {{ color: {MUTED}; font-size: 9pt; }}

QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#cardTitle {{ color: {MUTED}; font-size: 8pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#bigValue {{ font-size: 40pt; font-weight: 700; color: {CYAN}; font-family: {MONO}; }}
QLabel#hexValue {{ font-size: 20pt; font-weight: 700; color: {PURPLE}; font-family: {MONO}; }}
QLabel#binValue {{ font-size: 12pt; color: {MUTED}; font-family: {MONO}; }}
QLabel#mid {{ font-size: 16pt; font-weight: 700; }}
QLabel#metric {{ font-size: 11pt; font-weight: 600; font-family: {MONO}; }}

QLabel#chip {{ border-radius: 12px; padding: 5px 14px; font-weight: 700; background: #26324F; color: {TEXT}; }}
QLabel#chip[state="contando"] {{ background: #065F46; color: #A7F3D0; }}
QLabel#chip[state="pausado"] {{ background: #78350F; color: #FDE68A; }}
QLabel#chip[state="parado"] {{ background: #26324F; color: #CBD5E1; }}
QLabel#chip[state="reinicializando"] {{ background: #1E3A8A; color: #BFDBFE; }}
QLabel#chip[state="semcom"] {{ background: #7F1D1D; color: #FECACA; }}
QLabel#linkChip {{ border-radius: 11px; padding: 4px 12px; font-weight: 700; background: #26324F; }}
QLabel#linkChip[kind="sim"] {{ background: #4C1D95; color: #DDD6FE; }}
QLabel#linkChip[kind="connected"] {{ background: #065F46; color: #A7F3D0; }}
QLabel#linkChip[kind="connecting"] {{ background: #78350F; color: #FDE68A; }}
QLabel#linkChip[kind="lost"], QLabel#linkChip[kind="error"] {{ background: #7F1D1D; color: #FECACA; }}
QLabel#banner {{ background: #7F1D1D; color: #FEE2E2; padding: 8px 16px; font-weight: 600; }}

QPushButton {{ background: #19244A; border: 1px solid #2A3A66; border-radius: 9px; padding: 10px 16px; font-weight: 600; }}
QPushButton:hover {{ background: #223163; border-color: #3B5086; }}
QPushButton:pressed {{ background: #14204A; }}
QPushButton:disabled {{ color: #55617F; background: #111933; border-color: #1B2748; }}
QPushButton[role="start"] {{ background: #0B5E3E; border-color: #14946A; }}
QPushButton[role="start"]:hover {{ background: #0E7650; }}
QPushButton[role="pause"] {{ background: #7A4A0A; border-color: #B7791F; }}
QPushButton[role="pause"]:hover {{ background: #965C0E; }}
QPushButton[role="reset"] {{ background: #6B1F2A; border-color: #B23A48; }}
QPushButton[role="reset"]:hover {{ background: #862838; }}
QPushButton[active="true"] {{ background: #0E7490; border-color: {CYAN}; color: white; }}
QPushButton[role="start"]:disabled, QPushButton[role="pause"]:disabled, QPushButton[role="reset"]:disabled {{ background: #111933; border-color: #1B2748; }}

QComboBox {{ background: {CARD_ALT}; border: 1px solid #2A3A66; border-radius: 8px; padding: 6px 10px; min-height: 22px; }}
QComboBox:disabled {{ color: #55617F; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: #1D4ED8; }}

QProgressBar {{ background: {TRACK}; border: none; border-radius: 7px; height: 14px; text-align: center; color: {TEXT}; font-size: 8pt; font-weight: 700; }}
QProgressBar::chunk {{ border-radius: 7px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0891B2, stop:1 {CYAN}); }}

QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 10px 22px; margin-right: 2px; border-bottom: 3px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 3px solid {CYAN}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QTableWidget {{ background: {CARD_ALT}; alternate-background-color: #0F1830; border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; selection-background-color: #1D3A6B; }}
QHeaderView::section {{ background: #16213F; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; padding: 7px; font-weight: 700; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2A3A66; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QStatusBar {{ background: {HEADER}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
"""
