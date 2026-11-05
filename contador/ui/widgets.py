"""Widgets desenhados com QPainter (sem dependencias extras)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPen,
                         QRadialGradient)
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import theme as T


def repolish(widget: QWidget) -> None:
    """Reaplica o QSS depois de mudar uma propriedade dinamica (ex.: state)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def draw_text(p: QPainter, x: float, y: float, w: float, h: float,
              align: Qt.AlignmentFlag, text: str) -> None:
    p.drawText(QRectF(x, y, w, h), int(align.value), text)


class Card(QFrame):
    """Cartao com titulo; coloque o conteudo em `card.body` (QVBoxLayout)."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 12, 16, 14)
        self.body.setSpacing(8)
        if title:
            lbl = QLabel(title.upper())
            lbl.setObjectName("cardTitle")
            self.body.addWidget(lbl)


class BitTile(QWidget):
    """Indicador de um bit (Qn): aceso/ciano = 1, apagado/escuro = 0."""

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self._on = False
        self.setMinimumSize(44, 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(96)

    def set_on(self, on: bool) -> None:
        if on != self._on:
            self._on = on
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        tile = QRectF(3, 3, w - 6, h - 38)
        if self._on:
            glow = QRadialGradient(tile.center(), tile.width())
            glow.setColorAt(0, QColor(34, 211, 238, 90))
            glow.setColorAt(1, QColor(34, 211, 238, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(tile.adjusted(-3, -3, 3, 3), 12, 12)
            grad = QLinearGradient(tile.topLeft(), tile.bottomLeft())
            grad.setColorAt(0, QColor("#67E8F9"))
            grad.setColorAt(1, QColor("#0891B2"))
            p.setBrush(grad)
            p.setPen(QPen(QColor(T.CYAN), 1.5))
            p.drawRoundedRect(tile, 9, 9)
            p.setPen(QColor("#04202B"))
        else:
            p.setBrush(QColor(T.BIT_OFF))
            p.setPen(QPen(QColor(T.BIT_OFF_BORDER), 1.2))
            p.drawRoundedRect(tile, 9, 9)
            p.setPen(QColor("#3A4770"))
        f = QFont(self.font())
        f.setPointSize(18)
        f.setBold(True)
        p.setFont(f)
        draw_text(p, tile.x(), tile.y(), tile.width(), tile.height(),
                  Qt.AlignmentFlag.AlignCenter, "1" if self._on else "0")

        f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor(T.TEXT if self._on else T.MUTED))
        draw_text(p, 0, h - 33, w, 16, Qt.AlignmentFlag.AlignCenter, f"Q{self.index}")
        f.setBold(False)
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QColor(T.MUTED))
        draw_text(p, 0, h - 16, w, 14, Qt.AlignmentFlag.AlignCenter, str(1 << self.index))


class LedIndicator(QWidget):
    """Led redondo com brilho quando aceso."""

    def __init__(self, color: str = T.GREEN, size: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on = False
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def set_on(self, on: bool) -> None:
        if on != self._on:
            self._on = on
            self.update()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(4, 4, self.width() - 8, self.height() - 8)
        if self._on:
            glow = QRadialGradient(r.center(), r.width() * 0.95)
            c = QColor(self._color)
            c.setAlpha(140)
            glow.setColorAt(0, c)
            c.setAlpha(0)
            glow.setColorAt(1, c)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(0, 0, self.width(), self.height()))
            p.setBrush(self._color)
            p.setPen(QPen(self._color.lighter(150), 1.5))
        else:
            p.setBrush(QColor(T.BIT_OFF))
            p.setPen(QPen(QColor(T.BIT_OFF_BORDER), 1.5))
        p.drawEllipse(r)


class GaugeWidget(QWidget):
    """Medidor circular (270 graus) do percentual do ciclo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pct = 0.0
        self.setMinimumSize(150, 150)

    def set_value(self, pct: float) -> None:
        pct = max(0.0, min(100.0, pct))
        if abs(pct - self._pct) > 1e-6:
            self._pct = pct
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h)
        rect = QRectF((w - side) / 2 + 16, (h - side) / 2 + 16, side - 32, side - 32)
        pen = QPen(QColor(T.TRACK), 13)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 225 * 16, -270 * 16)
        if self._pct > 0:
            pen.setColor(QColor(T.CYAN))
            p.setPen(pen)
            p.drawArc(rect, 225 * 16, int(-270 * 16 * self._pct / 100.0))
        p.setPen(QColor(T.TEXT))
        f = QFont(self.font())
        f.setPointSize(20)
        f.setBold(True)
        p.setFont(f)
        draw_text(p, rect.x(), rect.y() + rect.height() * 0.30, rect.width(), rect.height() * 0.3,
                  Qt.AlignmentFlag.AlignCenter, f"{self._pct:.1f}%")
        f.setPointSize(9)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(T.MUTED))
        draw_text(p, rect.x(), rect.y() + rect.height() * 0.58, rect.width(), rect.height() * 0.2,
                  Qt.AlignmentFlag.AlignCenter, "do ciclo")
