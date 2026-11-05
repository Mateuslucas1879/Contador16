"""Janela principal (PyQt6): painel, graficos, historico e diagramas.

Esta camada SO apresenta e envia comandos. Ela nao conta: o valor vem do backend
ativo (SimBackend = simulacao local; SerialBackend = Arduino real).
"""
from __future__ import annotations

import csv
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QGridLayout,
                             QHBoxLayout, QHeaderView, QLabel, QMainWindow, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QTabWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from ..comm.backends import BaseBackend, SerialBackend, SimBackend
from ..comm.protocol import BAUD_DEFAULT, BAUD_OPTIONS
from ..comm.serial_worker import list_serial_ports
from ..core import timing
from ..core.counter_model import (BITS, LIMIT_VALUE, MAX_VALUE, ExecState, Snapshot,
                                  progress_fraction)
from . import theme as T
from .charts import CycleChart, TracePlot
from .diagrams import DiagramWidget
from .widgets import BitTile, Card, GaugeWidget, LedIndicator, repolish

LINK_TEXT = {"sim": "SIMULAÇÃO LOCAL", "connecting": "CONECTANDO…", "connected": "ARDUINO CONECTADO",
             "lost": "COMUNICAÇÃO PERDIDA", "error": "FALHA NA PORTA", "closed": "DESCONECTADO"}


def br(x: float, nd: int = 2) -> str:
    """Formata numero no padrao brasileiro (1.234,56)."""
    return f"{x:,.{nd}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_int(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def fmt_time(s: float) -> str:
    m = int(s // 60)
    return f"{m:02d}:{s - m * 60:06.3f}"


class EventLog:
    """Historico de eventos: tabela na tela + lista para exportar em CSV."""

    HEADERS = ("Data", "Hora", "Modo", "Limite", "Valor", "Ação")
    MAX_ROWS = 5000

    def __init__(self, table: QTableWidget) -> None:
        self.table = table
        self.rows: list[tuple[str, ...]] = []
        table.setColumnCount(len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        for col, width in enumerate((100, 110, 70, 80, 170)):
            table.setColumnWidth(col, width)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

    def add(self, mode: str, limit: str, value: str, action: str) -> None:
        now = datetime.now()
        row = (now.strftime("%d/%m/%Y"), now.strftime("%H:%M:%S.%f")[:-3], mode, limit, value, action)
        self.rows.append(row)
        if len(self.rows) > self.MAX_ROWS:
            del self.rows[0]
            self.table.removeRow(0)
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, text in enumerate(row):
            self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.scrollToBottom()

    def clear(self) -> None:
        self.rows.clear()
        self.table.setRowCount(0)

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:   # utf-8-sig: Excel abre com acentos
            w = csv.writer(fh, delimiter=";")
            w.writerow(self.HEADERS)
            w.writerows(self.rows)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Contador de 16 bits — EEL280 · Experimento 5")
        self.resize(1440, 920)

        self.sim = SimBackend(self)
        self.ser = SerialBackend(self)
        self.backend: BaseBackend | None = None
        self._link_kind = "closed"
        self._last_link: tuple[str, str] | None = None
        self._reset_runtime()

        self._build_ui()
        self._build_shortcuts()

        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self._last_port_refresh = 0.0

        self.mode_combo.currentIndexChanged.connect(lambda _i: self._set_mode(self.mode_combo.currentData()))
        self._set_mode("sim")

    # ======================================================================
    # Estado de execucao da interface
    # ======================================================================
    def _reset_runtime(self) -> None:
        self.snap: Snapshot | None = None
        self._elapsed = 0.0
        self._prev_t: float | None = None
        self._cycles = 0
        self._periods: list[float] = []
        self._ui_frames = 0
        self._ui_rate = 0.0
        self._rate_t = time.monotonic()
        self._reinit_until = 0.0
        self._det_hold_until = 0.0
        self._last_ndet: int | None = None
        self._last_measured_hz: float | None = None

    # ======================================================================
    # Construcao da interface
    # ======================================================================
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_header())

        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.hide()
        lay.addWidget(self.banner)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_dashboard(), "Painel")
        self.tabs.addTab(self._build_charts_tab(), "Gráficos")
        self.tabs.addTab(self._build_log_tab(), "Histórico")
        self.tabs.addTab(self._build_arch_tab(), "Arquitetura")
        lay.addWidget(self.tabs, 1)
        self.statusBar().showMessage("Pronto.")

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setObjectName("header")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel("Contador de 16 bits")
        t.setObjectName("appTitle")
        s = QLabel("EEL280 · Experimento 5 — supervisão UP/DOWN com Arduino Uno")
        s.setObjectName("appSub")
        titles.addWidget(t)
        titles.addWidget(s)
        lay.addLayout(titles)
        lay.addStretch(1)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Simulação local", "sim")
        self.mode_combo.addItem("Arduino (serial)", "serial")
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(260)
        self.btn_refresh = QPushButton("Atualizar portas")
        self.baud_combo = QComboBox()
        for b in BAUD_OPTIONS:
            self.baud_combo.addItem(f"{b} baud", b)
        self.baud_combo.setCurrentIndex(BAUD_OPTIONS.index(BAUD_DEFAULT))
        self.btn_connect = QPushButton("Conectar")
        self.link_chip = QLabel("DESCONECTADO")
        self.link_chip.setObjectName("linkChip")
        self.link_chip.setProperty("kind", "closed")
        for w in (QLabel("Modo:"), self.mode_combo, QLabel("Porta:"), self.port_combo,
                  self.btn_refresh, self.baud_combo, self.btn_connect, self.link_chip):
            lay.addWidget(w)
        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        return hdr

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # ---- linha 1: valor, estado, deteccao, progresso ----
        row1 = QHBoxLayout()
        row1.setSpacing(14)
        vc = Card("Valor atual")
        self.lbl_dec = QLabel("—")
        self.lbl_dec.setObjectName("bigValue")
        self.lbl_hex = QLabel("0x----")
        self.lbl_hex.setObjectName("hexValue")
        self.lbl_bin = QLabel("---- ---- ---- ----")
        self.lbl_bin.setObjectName("binValue")
        hexrow = QHBoxLayout()
        hexrow.addWidget(self.lbl_hex)
        hexrow.addStretch(1)
        vc.body.addWidget(self.lbl_dec)
        vc.body.addLayout(hexrow)
        vc.body.addWidget(self.lbl_bin)
        row1.addWidget(vc, 4)

        sc = Card("Estado de execução")
        self.chip_state = QLabel("PARADO")
        self.chip_state.setObjectName("chip")
        self.chip_state.setProperty("state", "parado")
        self.lbl_dir = QLabel("UP  ▲")
        self.lbl_dir.setObjectName("mid")
        self.lbl_range = QLabel("")
        self.lbl_range.setObjectName("muted")
        sc.body.addWidget(self.chip_state, 0, Qt.AlignmentFlag.AlignLeft)
        sc.body.addWidget(self.lbl_dir)
        sc.body.addWidget(self.lbl_range)
        sc.body.addStretch(1)
        row1.addWidget(sc, 3)

        dc = Card("Detecção do limite 10.000")
        drow = QHBoxLayout()
        self.led_detect = LedIndicator(T.AMBER, 40)
        self.lbl_detect = QLabel("aguardando 10.000")
        self.lbl_detect.setObjectName("mid")
        drow.addWidget(self.led_detect)
        drow.addWidget(self.lbl_detect, 1)
        lrow = QHBoxLayout()
        self.led_limit = LedIndicator(T.GREEN, 22)
        self.lbl_limit_state = QLabel("Limite desativado")
        lrow.addWidget(self.led_limit)
        lrow.addWidget(self.lbl_limit_state, 1)
        self.lbl_ndet = QLabel("Detecções desde o RESET: 0")
        self.lbl_ndet.setObjectName("muted")
        dc.body.addLayout(drow)
        dc.body.addLayout(lrow)
        dc.body.addWidget(self.lbl_ndet)
        dc.body.addStretch(1)
        row1.addWidget(dc, 3)

        gc = Card("Progresso do ciclo")
        self.gauge = GaugeWidget()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        gc.body.addWidget(self.gauge, 1)
        gc.body.addWidget(self.progress)
        row1.addWidget(gc, 3)
        root.addLayout(row1)

        # ---- linha 2: display de 16 bits ----
        bc = Card("Display virtual de 16 bits — Q15 … Q0 (aceso = 1, apagado = 0)")
        brow = QHBoxLayout()
        brow.setSpacing(6)
        self.tiles: dict[int, BitTile] = {}
        for i in range(BITS - 1, -1, -1):
            tile = BitTile(i)
            self.tiles[i] = tile
            brow.addWidget(tile)
            if i % 4 == 0 and i != 0:
                brow.addSpacing(14)             # separa os nibbles
        bc.body.addLayout(brow)
        root.addWidget(bc)

        # ---- linha 3: controles, tempos, grafico ao vivo ----
        row3 = QHBoxLayout()
        row3.setSpacing(14)
        row3.addWidget(self._build_controls(), 0)
        row3.addWidget(self._build_times(), 0)
        pc = Card("Evolução da contagem (ao vivo)")
        self.trace = TracePlot(window_s=30.0)
        pc.body.addWidget(self.trace, 1)
        row3.addWidget(pc, 1)
        root.addLayout(row3, 1)
        return page

    def _build_controls(self) -> Card:
        c = Card("Controles")
        c.setFixedWidth(330)
        self.btn_up = QPushButton("▲  UP")
        self.btn_down = QPushButton("▼  DOWN")
        self.btn_start = QPushButton("▶  START")
        self.btn_pause = QPushButton("❚❚  PAUSE")
        self.btn_reset = QPushButton("↺  RESET")
        self.btn_limit = QPushButton("Limite 10.000: DESLIGADO")
        for b, role in ((self.btn_start, "start"), (self.btn_pause, "pause"), (self.btn_reset, "reset")):
            b.setProperty("role", role)
        self._ctrl_buttons = [self.btn_up, self.btn_down, self.btn_start, self.btn_pause,
                              self.btn_reset, self.btn_limit]
        for b in self._ctrl_buttons:
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # a barra de espaco fica so com o atalho START/PAUSE
        lbl_dir = QLabel("Sentido")
        lbl_dir.setObjectName("muted")
        lbl_run = QLabel("Execução")
        lbl_run.setObjectName("muted")
        lbl_lim = QLabel("Limite")
        lbl_lim.setObjectName("muted")
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        r1.addWidget(self.btn_up)
        r1.addWidget(self.btn_down)
        r2.addWidget(self.btn_start)
        r2.addWidget(self.btn_pause)
        c.body.addWidget(lbl_dir)
        c.body.addLayout(r1)
        c.body.addWidget(lbl_run)
        c.body.addLayout(r2)
        c.body.addWidget(self.btn_reset)
        c.body.addWidget(lbl_lim)
        c.body.addWidget(self.btn_limit)
        hint = QLabel("Atalhos: Espaço = START/PAUSE · U = UP · D = DOWN · R = RESET · L = LIMITE.\n"
                      "Os botões físicos do Arduino fazem o mesmo e aparecem aqui.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        c.body.addWidget(hint)
        c.body.addStretch(1)

        self.btn_up.clicked.connect(lambda: self._user("UP", lambda b: b.set_up(True)))
        self.btn_down.clicked.connect(lambda: self._user("DOWN", lambda b: b.set_up(False)))
        self.btn_start.clicked.connect(lambda: self._user("START", lambda b: b.start()))
        self.btn_pause.clicked.connect(lambda: self._user("PAUSE", lambda b: b.pause()))
        self.btn_reset.clicked.connect(lambda: self._user("RESET", lambda b: b.reset(), reset=True))
        self.btn_limit.clicked.connect(self._toggle_limit)
        return c

    def _build_times(self) -> Card:
        c = Card("Tempos e frequências")
        c.setFixedWidth(430)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        names = [("elapsed", "Tempo em execução"), ("cycle", "Tempo no ciclo atual"),
                 ("period", "Período do ciclo (estimado)"), ("last", "Último ciclo medido"),
                 ("fnom", "Frequência nominal (roteiro)"), ("freal", "Frequência do clock (Timer1)"),
                 ("fmeas", "Frequência medida"), ("ui", "Atualização da interface"),
                 ("cycles", "Ciclos completos")]
        self.tv: dict[str, QLabel] = {}
        for r, (key, text) in enumerate(names):
            k = QLabel(text)
            k.setObjectName("muted")
            v = QLabel("—")
            v.setObjectName("metric")
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(k, r, 0)
            grid.addWidget(v, r, 1)
            self.tv[key] = v
        c.body.addLayout(grid)
        c.body.addStretch(1)
        return c

    def _build_charts_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)
        c1 = Card("Evolução da contagem — últimos 60 s")
        self.trace_big = TracePlot(window_s=60.0)
        c1.body.addWidget(self.trace_big, 1)
        c2 = Card("Período medido de cada ciclo (alvo: 20 s)")
        self.cycle_chart = CycleChart(timing.TARGET_CYCLE_S)
        c2.body.addWidget(self.cycle_chart, 1)
        lay.addWidget(c1, 3)
        lay.addWidget(c2, 2)
        return page

    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        bar = QHBoxLayout()
        b_exp = QPushButton("Exportar CSV…")
        b_clr = QPushButton("Limpar histórico")
        bar.addWidget(b_exp)
        bar.addWidget(b_clr)
        bar.addStretch(1)
        self.table = QTableWidget(0, 6)
        self.log = EventLog(self.table)
        lay.addLayout(bar)
        lay.addWidget(self.table, 1)
        b_exp.clicked.connect(self._export_csv)
        b_clr.clicked.connect(self.log.clear)
        return page

    def _build_arch_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)
        self.diag_arch = DiagramWidget("arch")
        self.diag_comm = DiagramWidget("comm")
        for title, d in (("Diagrama de blocos da arquitetura", self.diag_arch),
                         ("Diagrama de comunicação Python ↔ Arduino", self.diag_comm)):
            card = Card(title)
            d.setMinimumHeight(380)
            card.body.addWidget(d, 1)
            lay.addWidget(card)
        scroll.setWidget(page)
        return scroll

    def _build_shortcuts(self) -> None:
        def sc(key: str, fn) -> None:
            QShortcut(QKeySequence(key), self, activated=fn)
        sc("Space", self._toggle_run)
        sc("U", self.btn_up.click)
        sc("D", self.btn_down.click)
        sc("R", self.btn_reset.click)
        sc("L", self.btn_limit.click)

    # ======================================================================
    # Backend: troca de modo e ligacao de sinais
    # ======================================================================
    def _set_mode(self, mode: str) -> None:
        new = self.sim if mode == "sim" else self.ser
        if new is self.backend:
            return
        if self.backend is not None:
            self._unbind(self.backend)
            self.backend.deactivate()
        self.backend = new
        self._reset_runtime()
        self.trace.clear()
        self.trace_big.clear()
        self.cycle_chart.clear()
        self._last_link = None
        is_serial = mode == "serial"
        for w in (self.port_combo, self.baud_combo, self.btn_refresh, self.btn_connect):
            w.setEnabled(is_serial)
        if is_serial:
            self._refresh_ports()
        self._bind(new)
        new.activate()
        self._render()

    def _bind(self, b: BaseBackend) -> None:
        b.state_changed.connect(self._on_state)
        b.link_changed.connect(self._on_link)
        b.cycle_completed.connect(self._on_cycle)
        b.button_event.connect(self._on_button)
        b.notice.connect(self._on_notice)

    def _unbind(self, b: BaseBackend) -> None:
        for sig, slot in ((b.state_changed, self._on_state), (b.link_changed, self._on_link),
                          (b.cycle_completed, self._on_cycle), (b.button_event, self._on_button),
                          (b.notice, self._on_notice)):
            try:
                sig.disconnect(slot)
            except TypeError:
                pass

    # ======================================================================
    # Portas seriais
    # ======================================================================
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        ports = list_serial_ports()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        if not ports:
            self.port_combo.addItem("Nenhuma porta encontrada", None)
        for dev, desc in ports:
            self.port_combo.addItem(f"{dev} — {desc}", dev)
        idx = self.port_combo.findData(current)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)
        self.port_combo.blockSignals(False)
        self._last_port_refresh = time.monotonic()

    def _on_connect_clicked(self) -> None:
        if self._link_kind in ("connecting", "connected", "lost", "error"):
            self.ser.disconnect_port()
            return
        port = self.port_combo.currentData()
        baud = self.baud_combo.currentData()
        if not port:
            self.statusBar().showMessage("Nenhuma porta serial selecionada.", 5000)
            return
        self.ser.connect_port(str(port), int(baud))

    # ======================================================================
    # Slots do backend
    # ======================================================================
    def _on_link(self, kind: str, text: str) -> None:
        self._link_kind = kind
        self.link_chip.setText(LINK_TEXT.get(kind, kind.upper()))
        self.link_chip.setProperty("kind", kind)
        repolish(self.link_chip)
        self.diag_arch.set_link_kind(kind)
        self.diag_comm.set_link_kind(kind)
        if kind in ("lost", "error"):
            self.banner.setText(f"⚠  {text}")
            self.banner.show()
        else:
            self.banner.hide()
        ready = kind in ("sim", "connected")
        for b in self._ctrl_buttons:
            b.setEnabled(ready)
        self.btn_connect.setText("Desconectar" if kind in ("connecting", "connected", "lost", "error")
                                 else "Conectar")
        if (kind, text) != self._last_link:
            self._last_link = (kind, text)
            self._log(f"COMUNICAÇÃO: {text}")
        self._render()

    def _on_state(self, snap: Snapshot) -> None:
        prev = self.snap
        if prev is not None and prev.state == ExecState.RUNNING and self._prev_t is not None:
            self._elapsed += max(0.0, snap.t - self._prev_t)
        self._prev_t = snap.t
        if prev is not None and prev.limit != snap.limit:
            self._periods.clear()               # periodo muda de referencia (10.001 x 65.536 estados)
        if self._last_ndet is not None and snap.detections > self._last_ndet:
            self._det_hold_until = time.monotonic() + 0.45   # a deteccao dura microssegundos: segura o LED
            self._log(f"DETECÇÃO do valor 10.000 (total {snap.detections})")
        self._last_ndet = snap.detections
        self.snap = snap
        self._ui_frames += 1
        self.trace.add_point(snap.t, snap.value)
        self.trace_big.add_point(snap.t, snap.value)
        ymax = LIMIT_VALUE if snap.limit else MAX_VALUE
        self.trace.set_ymax(ymax)
        self.trace_big.set_ymax(ymax)
        self._render()

    def _on_cycle(self, seconds: float) -> None:
        self._cycles += 1
        if seconds > 0:
            self._periods.append(seconds)
            self.cycle_chart.add_period(seconds)
            states = timing.states(self.snap.limit if self.snap else False)
            self._last_measured_hz = states / seconds
            err = timing.relative_error_pct(seconds)
            self._log(f"FIM DE CICLO — período medido {br(seconds, 3)} s (erro {br(err, 3)} %)")
        else:
            self._log("FIM DE CICLO — reinício do contador")

    def _on_button(self, name: str) -> None:
        text = {"START": "START/PAUSE", "DIR": "UP/DOWN", "RESET": "RESET", "LIMIT": "LIMITE 10.000"}.get(name, name)
        if name == "RESET":
            self._begin_reset()
        self._log(f"{text} (botão físico)")

    def _on_notice(self, level: str, text: str) -> None:
        self.statusBar().showMessage(text, 6000)
        if level in ("warn", "error"):
            self._log(f"AVISO: {text}")

    # ======================================================================
    # Acoes do usuario
    # ======================================================================
    def _user(self, label: str, fn, reset: bool = False) -> None:
        b = self.backend
        if b is None or not b.is_ready():
            self.statusBar().showMessage("Sem comunicação com o Arduino: comando não enviado.", 5000)
            return
        if reset:
            self._begin_reset()          # antes do comando: o chip REINICIALIZANDO aparece junto com o novo estado
        fn(b)
        self._log(f"{label} (virtual)")

    def _toggle_limit(self) -> None:
        cur = bool(self.snap.limit) if self.snap else False
        self._user(f"LIMITE 10.000 {'DESLIGADO' if cur else 'LIGADO'}", lambda b: b.set_limit(not cur))

    def _toggle_run(self) -> None:
        if self.snap is not None and self.snap.state == ExecState.RUNNING:
            self.btn_pause.click()
        else:
            self.btn_start.click()

    def _begin_reset(self) -> None:
        self._elapsed = 0.0
        self._reinit_until = time.monotonic() + 0.6
        self._last_ndet = 0
        self.trace.clear()
        self.trace_big.clear()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar histórico", "historico_contador.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        try:
            self.log.export_csv(path)
            self.statusBar().showMessage(f"Histórico salvo em {path}", 6000)
        except OSError as exc:
            self.statusBar().showMessage(f"Não foi possível salvar: {exc}", 8000)

    def _log(self, action: str) -> None:
        s = self.snap
        if s is not None:
            mode, lim, val = "UP" if s.up else "DOWN", "10.000" if s.limit else "65.535", \
                f"{fmt_int(s.value)} (0x{s.value:04X})"
        else:
            mode, lim, val = "—", "—", "—"
        self.log.add(mode, lim, val, action)
        self.statusBar().showMessage(f"{datetime.now():%H:%M:%S}  {action}", 5000)

    # ======================================================================
    # Atualizacao da tela
    # ======================================================================
    def _on_tick(self) -> None:
        now = time.monotonic()
        if now - self._rate_t >= 1.0:
            self._ui_rate = self._ui_frames / (now - self._rate_t)
            self._ui_frames = 0
            self._rate_t = now
        self._render_chip()
        self._render_times()
        if (self.backend is self.ser and self._link_kind == "closed" and now - self._last_port_refresh > 3
                and not self.port_combo.view().isVisible()):
            self._refresh_ports()                # detecta Arduino plugado depois de abrir o programa

    def _render(self) -> None:
        s = self.snap
        if s is None:
            self.lbl_dec.setText("—")
            self.lbl_hex.setText("0x----")
            self.lbl_bin.setText("---- ---- ---- ----")
            for t in self.tiles.values():
                t.set_on(False)
            self.gauge.set_value(0)
            self.progress.setValue(0)
            self.progress.setFormat("—")
            self.led_detect.set_on(False)
            self.led_limit.set_on(False)
            self._render_chip()
            self._render_times()
            return
        v = s.value
        self.lbl_dec.setText(fmt_int(v))
        self.lbl_hex.setText(f"0x{v:04X}")
        bits = f"{v:016b}"
        self.lbl_bin.setText(" ".join(bits[i:i + 4] for i in range(0, 16, 4)))
        for i, tile in self.tiles.items():
            tile.set_on(bool((v >> i) & 1))

        self.lbl_dir.setText("UP  ▲  (crescente)" if s.up else "DOWN  ▼  (decrescente)")
        top = LIMIT_VALUE if s.limit else MAX_VALUE
        self.lbl_range.setText(f"Faixa 0 … {fmt_int(top)}  ({fmt_int(top + 1)} estados)")
        self._set_active(self.btn_up, s.up)
        self._set_active(self.btn_down, not s.up)
        self._set_active(self.btn_start, s.state == ExecState.RUNNING)
        self._set_active(self.btn_pause, s.state == ExecState.PAUSED)
        self._set_active(self.btn_limit, s.limit)
        self.btn_limit.setText(f"Limite 10.000: {'LIGADO' if s.limit else 'DESLIGADO'}")
        self.led_limit.set_on(s.limit)
        self.lbl_limit_state.setText("Limite ativo: 0 … 10.000" if s.limit else "Limite desativado (0 … 65.535)")

        lit = s.detect or time.monotonic() < self._det_hold_until
        self.led_detect.set_on(lit)
        self.lbl_detect.setText("10.000 DETECTADO" if lit else "aguardando 10.000")
        self.lbl_ndet.setText(f"Detecções desde o RESET: {s.detections}")

        pct = progress_fraction(v, s.up, s.limit) * 100
        self.gauge.set_value(pct)
        self.progress.setValue(int(pct * 10))
        self.progress.setFormat(f"{br(pct, 1)} %")
        self._render_chip()
        self._render_times()

    @staticmethod
    def _set_active(btn: QPushButton, active: bool) -> None:
        if btn.property("active") != active:
            btn.setProperty("active", active)
            repolish(btn)

    def _render_chip(self) -> None:
        if self.snap is None or self._link_kind not in ("sim", "connected"):
            key = "semcom"
            text = {"connecting": "AGUARDANDO ARDUINO", "closed": "DESCONECTADO"}.get(self._link_kind,
                                                                                      "SEM COMUNICAÇÃO")
        elif time.monotonic() < self._reinit_until:
            key, text = "reinicializando", "REINICIALIZANDO"
        else:
            key, text = {ExecState.STOPPED: ("parado", "PARADO"), ExecState.RUNNING: ("contando", "CONTANDO"),
                         ExecState.PAUSED: ("pausado", "PAUSADO")}[self.snap.state]
        if self.chip_state.text() != text:
            self.chip_state.setText(text)
        if self.chip_state.property("state") != key:
            self.chip_state.setProperty("state", key)
            repolish(self.chip_state)

    def _period_estimate(self) -> tuple[float, str]:
        limit = self.snap.limit if self.snap else False
        if self._periods:
            recent = self._periods[-5:]
            return sum(recent) / len(recent), f"média de {len(recent)} ciclo(s)"
        return timing.real_cycle_period(limit), "teórico (Timer1)"

    def _render_times(self) -> None:
        s = self.snap
        limit = s.limit if s else False
        elapsed = self._elapsed
        if (s is not None and s.state == ExecState.RUNNING and self._prev_t is not None
                and self._link_kind in ("sim", "connected")):
            elapsed += min(max(time.monotonic() - self._prev_t, 0.0), 0.5)
        period, how = self._period_estimate()
        pct = progress_fraction(s.value, s.up, s.limit) if s else 0.0
        tv = self.tv
        tv["elapsed"].setText(fmt_time(elapsed))
        tv["cycle"].setText(f"{br(pct * period, 3)} s")
        tv["period"].setText(f"{br(period, 3)} s  ({how})")
        if self._periods:
            last = self._periods[-1]
            tv["last"].setText(f"{br(last, 3)} s  (erro {br(timing.relative_error_pct(last), 3)} %)")
        else:
            tv["last"].setText("—")
        tv["fnom"].setText(f"{br(timing.nominal_frequency(limit), 2)} Hz")
        tv["freal"].setText(f"{br(timing.real_frequency(limit), 2)} Hz")
        tv["fmeas"].setText("—" if self._last_measured_hz is None else f"{br(self._last_measured_hz, 2)} Hz")
        tv["ui"].setText(f"{br(self._ui_rate, 1)} quadros/s")
        tv["cycles"].setText(str(self._cycles))

    # ======================================================================
    def closeEvent(self, event) -> None:
        self.sim.deactivate()
        self.ser.shutdown()
        event.accept()
