"""Diagramas de blocos (arquitetura) e de comunicacao Python <-> Arduino.

Desenhados com QPainter em coordenadas logicas 900x420 e escalados para o widget.
A cor da seta USB acompanha o estado real da conexao.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from . import theme as T

W, H = 900.0, 420.0


class DiagramWidget(QWidget):
    """kind = 'arch' (blocos do sistema) ou 'comm' (troca de mensagens)."""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.link_kind = "closed"      # sim | connecting | connected | lost | error | closed
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_link_kind(self, kind: str) -> None:
        if kind != self.link_kind:
            self.link_kind = kind
            self.update()

    # ---- primitivas ----
    def _text(self, p, x, y, w, h, text, size=10, bold=False, color=T.TEXT,
              align=Qt.AlignmentFlag.AlignCenter):
        f = QFont(self.font())
        f.setPointSizeF(size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, w, h), int(align.value), text)

    def _box(self, p, x, y, w, h, title, lines=(), accent=T.CYAN, fill=T.CARD):
        p.setBrush(QColor(fill))
        p.setPen(QPen(QColor(accent), 1.6))
        p.drawRoundedRect(QRectF(x, y, w, h), 12, 12)
        self._text(p, x, y + 8, w, 22, title, 11, True, accent)
        for i, line in enumerate(lines):
            self._text(p, x + 8, y + 36 + i * 21, w - 16, 20, line, 9, False, T.TEXT)

    def _arrow(self, p, x1, y1, x2, y2, color=T.MUTED, label="", both=False, label_dy=-18):
        p.setPen(QPen(QColor(color), 2.2))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        ang = math.atan2(y2 - y1, x2 - x1)
        for (x, y, a) in ([(x2, y2, ang)] + ([(x1, y1, ang + math.pi)] if both else [])):
            tri = QPolygonF([
                QPointF(x, y),
                QPointF(x - 11 * math.cos(a - 0.4), y - 11 * math.sin(a - 0.4)),
                QPointF(x - 11 * math.cos(a + 0.4), y - 11 * math.sin(a + 0.4)),
            ])
            p.setBrush(QColor(color))
            p.drawPolygon(tri)
        if label:
            self._text(p, (x1 + x2) / 2 - 80, (y1 + y2) / 2 + label_dy, 160, 18, label, 9, True, color)

    def _link_color(self) -> str:
        return {"connected": T.GREEN, "sim": T.PURPLE, "connecting": T.AMBER,
                "lost": T.RED, "error": T.RED}.get(self.link_kind, T.MUTED)

    # ---- desenho ----
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / W, self.height() / H)
        p.translate((self.width() - W * scale) / 2, (self.height() - H * scale) / 2)
        p.scale(scale, scale)
        (self._paint_arch if self.kind == "arch" else self._paint_comm)(p)

    def _paint_arch(self, p: QPainter) -> None:
        lc = self._link_color()
        self._text(p, 0, 0, W, 26, "Arquitetura do sistema", 13, True)
        self._box(p, 10, 130, 190, 150, "Botoes fisicos",
                  ["START/PAUSE  -> D2", "UP/DOWN      -> D3", "RESET        -> D4",
                   "LIMITE 10.000 -> D5", "INPUT_PULLUP (ativo em 0)"], T.AMBER)
        self._box(p, 280, 60, 270, 290, "Arduino Uno (ATmega328P)",
                  ["Timer1 - modo CTC (hardware)", "3.276,67 Hz  |  500,05 Hz (limite)",
                   "Contador uint16 (0..65.535)", "UP/DOWN, START/PAUSE, RESET",
                   "Deteccao do valor 10.000", "Medida do periodo do ciclo",
                   "Serial 115200 baud"], T.CYAN)
        self._box(p, 640, 40, 255, 340, "Computador - Python 3 + PyQt6", (), T.PURPLE)
        inner = [("SerialWorker (QThread)", "PySerial, reconexao", T.GREEN),
                 ("Backend", "SerialBackend | SimBackend", T.CYAN),
                 ("CounterModel", "logica da simulacao local", T.PURPLE),
                 ("MainWindow (UI)", "bits, graficos, log, controles", T.AMBER)]
        for i, (t, s, c) in enumerate(inner):
            y = 78 + i * 74
            p.setBrush(QColor(T.CARD_ALT))
            p.setPen(QPen(QColor(c), 1.3))
            p.drawRoundedRect(QRectF(655, y, 225, 62), 9, 9)
            self._text(p, 655, y + 6, 225, 20, t, 10, True, c)
            self._text(p, 655, y + 30, 225, 20, s, 9, False, T.MUTED)
        for i in range(3):
            p.setPen(QPen(QColor(T.MUTED), 1.4))
            p.drawLine(QPointF(767, 140 + i * 74), QPointF(767, 152 + i * 74))
        self._arrow(p, 200, 205, 280, 205, T.AMBER, "pulsos dos botoes")
        self._arrow(p, 550, 205, 640, 205, lc, "USB / Serial", both=True)
        self._text(p, 20, 360, 600, 40,
                   "Sem Arduino: o SimBackend executa a mesma logica (CounterModel) no PC.\n"
                   "Com Arduino: so o valor recebido pela serial e exibido (nenhum dado simulado).",
                   9, False, T.MUTED, Qt.AlignmentFlag.AlignLeft)

    def _paint_comm(self, p: QPainter) -> None:
        self._text(p, 0, 0, W, 26, "Comunicacao Python <-> Arduino (protocolo serial em texto)", 13, True)
        px, ax = 200, 700
        self._box(p, px - 90, 36, 180, 44, "Python / PyQt6", (), T.PURPLE)
        self._box(p, ax - 90, 36, 180, 44, "Arduino Uno", (), T.CYAN)
        for x, c in ((px, T.PURPLE), (ax, T.CYAN)):
            p.setPen(QPen(QColor(c), 1.4, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, 80), QPointF(x, 400))
        lc = self._link_color()
        msgs = [
            (104, True, "PING", "PONG  /  H,CONTADOR16,1", T.AMBER),
            (176, True, "START | PAUSE | RESET | UP | DOWN | LIM1 | LIM0", None, T.GREEN),
            (232, False, "S,valor,up,estado,limite,det,ndet   (20 Hz e a cada mudanca)", None, lc),
            (288, False, "B,START | DIR | RESET | LIMIT   (botao fisico acionado)", None, T.AMBER),
            (344, False, "C,periodo_us   (fim de cada ciclo; mede os 20 s)", None, T.PURPLE),
        ]
        for y, to_arduino, text, reply, color in msgs:
            if to_arduino:
                self._arrow(p, px + 4, y, ax - 4, y, color)
            else:
                self._arrow(p, ax - 4, y, px + 4, y, color)
            self._text(p, px + 10, y - 22, ax - px - 20, 18, text, 9, True, color)
            if reply:
                self._arrow(p, ax - 4, y + 22, px + 4, y + 22, T.CYAN)
                self._text(p, px + 10, y + 24, ax - px - 20, 18, reply, 9, False, T.CYAN)
        self._text(p, 20, 392, 860, 24,
                   "Sem frames por 1,5 s => 'comunicacao perdida' e novas tentativas (PING a cada 0,5 s). "
                   "Porta caiu => reabre a cada 2 s.",
                   9, False, T.MUTED, Qt.AlignmentFlag.AlignLeft)
