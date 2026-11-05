"""Graficos desenhados com QPainter (sem PyQt6-Charts, para reduzir dependencias)."""
from __future__ import annotations

from collections import deque

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from . import theme as T
from .widgets import draw_text

ML, MR, MT, MB = 62, 14, 12, 28     # margens do grafico


def _frame(p: QPainter, w: int, h: int) -> tuple[float, float, float, float]:
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont(p.font())
    f.setPointSize(8)
    p.setFont(f)
    return ML, MT, w - ML - MR, h - MT - MB


class TracePlot(QWidget):
    """Evolucao do valor do contador no tempo (serra no modo UP, rampa invertida no DOWN)."""

    def __init__(self, window_s: float = 40.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.window_s = window_s
        self._data: deque[tuple[float, int]] = deque(maxlen=8000)
        self._ymax = 65535
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def add_point(self, t: float, value: int) -> None:
        self._data.append((t, value))
        self.update()

    def set_ymax(self, ymax: int) -> None:
        if ymax != self._ymax:
            self._ymax = ymax
            self.update()

    def clear(self) -> None:
        self._data.clear()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        x0, y0, pw, ph = _frame(p, self.width(), self.height())
        grid = QPen(QColor(T.BORDER), 1)
        for i in range(5):                                  # grade e rotulos do eixo Y
            y = y0 + ph * i / 4
            p.setPen(grid)
            p.drawLine(QPointF(x0, y), QPointF(x0 + pw, y))
            p.setPen(QColor(T.MUTED))
            val = int(self._ymax * (1 - i / 4))
            draw_text(p, 0, y - 8, ML - 8, 16,
                      Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                      f"{val:,}".replace(",", "."))
        for k in range(5):                                  # rotulos do eixo X (s)
            x = x0 + pw * k / 4
            p.setPen(grid)
            p.drawLine(QPointF(x, y0), QPointF(x, y0 + ph))
            p.setPen(QColor(T.MUTED))
            sec = -self.window_s * (1 - k / 4)
            draw_text(p, x - 30, y0 + ph + 4, 60, 18, Qt.AlignmentFlag.AlignCenter,
                      "agora" if k == 4 else f"{sec:.0f} s")
        if len(self._data) < 2:
            p.setPen(QColor(T.MUTED))
            draw_text(p, x0, y0, pw, ph, Qt.AlignmentFlag.AlignCenter, "aguardando dados...")
            return

        t_now = self._data[-1][0]
        t_min = t_now - self.window_s
        pen = QPen(QColor(T.CYAN), 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        prev_v = None
        last_pt = QPointF()
        for t, v in self._data:
            if t < t_min:
                continue
            pt = QPointF(x0 + (t - t_min) / self.window_s * pw,
                         y0 + ph * (1 - min(v, self._ymax) / self._ymax))
            # quebra a linha no reinicio do ciclo (salto grande) para nao desenhar o "pulo"
            if prev_v is None or abs(v - prev_v) > self._ymax * 0.5:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
            prev_v = v
            last_pt = pt
        p.drawPath(path)
        p.setBrush(QColor(T.CYAN))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(last_pt, 4, 4)


class CycleChart(QWidget):
    """Historico do periodo medido de cada ciclo, com a referencia de 20 s."""

    def __init__(self, reference: float = 20.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ref = reference
        self._vals: deque[float] = deque(maxlen=30)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def add_period(self, seconds: float) -> None:
        self._vals.append(seconds)
        self.update()

    def clear(self) -> None:
        self._vals.clear()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        x0, y0, pw, ph = _frame(p, self.width(), self.height())
        vals = list(self._vals)
        span = max([abs(v - self._ref) for v in vals] + [0.01]) * 1.4
        lo, hi = self._ref - span, self._ref + span
        grid = QPen(QColor(T.BORDER), 1)
        for i in range(5):
            y = y0 + ph * i / 4
            p.setPen(grid)
            p.drawLine(QPointF(x0, y), QPointF(x0 + pw, y))
            p.setPen(QColor(T.MUTED))
            draw_text(p, 0, y - 8, ML - 8, 16,
                      Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                      f"{hi - (hi - lo) * i / 4:.3f}")
        ry = y0 + ph * (hi - self._ref) / (hi - lo)
        dash = QPen(QColor(T.AMBER), 1.5, Qt.PenStyle.DashLine)
        p.setPen(dash)
        p.drawLine(QPointF(x0, ry), QPointF(x0 + pw, ry))
        p.setPen(QColor(T.AMBER))
        draw_text(p, x0 + 4, ry - 18, 120, 16, Qt.AlignmentFlag.AlignLeft, "20 s (alvo)")
        if not vals:
            p.setPen(QColor(T.MUTED))
            draw_text(p, x0, y0, pw, ph, Qt.AlignmentFlag.AlignCenter,
                      "complete um ciclo para medir o periodo")
            return
        n = len(vals)
        step = pw / max(n, 2)
        pts = [QPointF(x0 + step * (i + 0.5), y0 + ph * (hi - v) / (hi - lo)) for i, v in enumerate(vals)]
        p.setPen(QPen(QColor(T.GREEN), 2))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        p.setBrush(QColor(T.GREEN))
        p.setPen(Qt.PenStyle.NoPen)
        for pt in pts:
            p.drawEllipse(pt, 4, 4)
        p.setPen(QColor(T.MUTED))
        draw_text(p, x0, y0 + ph + 4, pw, 18, Qt.AlignmentFlag.AlignCenter,
                  f"ultimos {n} ciclos (eixo Y em segundos)")
