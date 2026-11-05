"""Backends que alimentam a interface com o estado do contador.

Ha duas implementacoes com a MESMA interface (sinais e comandos):

  SimBackend    simulacao local completa (usa CounterModel e o tempo real do PC).
  SerialBackend dados REAIS do Arduino pela serial. Nenhum dado simulado e gerado:
                os comandos so seguem para o Arduino e a tela so muda quando
                chega um frame `S,...` de volta.

A interface (MainWindow) nao sabe qual dos dois esta ativo.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core.counter_model import CounterModel, ExecState, Snapshot
from ..core.timing import real_frequency
from . import protocol as P
from .serial_worker import SerialWorker


class BaseBackend(QObject):
    state_changed = pyqtSignal(object)      # Snapshot
    link_changed = pyqtSignal(str, str)     # (tipo, texto)
    cycle_completed = pyqtSignal(float)     # periodo em s (0.0 = sem medida valida)
    button_event = pyqtSignal(str)          # START / DIR / RESET / LIMIT (botao fisico)
    notice = pyqtSignal(str, str)           # (nivel info|warn|error, texto)

    name = "base"

    def activate(self) -> None: ...
    def deactivate(self) -> None: ...
    def is_ready(self) -> bool: return False

    def start(self) -> None: ...
    def pause(self) -> None: ...
    def reset(self) -> None: ...
    def set_up(self, up: bool) -> None: ...
    def set_limit(self, enabled: bool) -> None: ...


# =============================================================================
# Simulacao local
# =============================================================================
class SimBackend(BaseBackend):
    """Simula o Arduino: mesma logica (CounterModel) e mesma frequencia do Timer1."""

    name = "sim"
    TICK_MS = 16

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = CounterModel()
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._last = time.perf_counter()
        self._frac = 0.0            # passos fracionarios acumulados
        self._run_time = 0.0        # tempo total em RUNNING (s)
        self._last_wrap_rt: float | None = None

    def activate(self) -> None:
        self._last = time.perf_counter()
        self._timer.start()
        self.link_changed.emit("sim", "Simulação local ativa (sem Arduino)")
        self._emit()

    def deactivate(self) -> None:
        self._timer.stop()

    def is_ready(self) -> bool:
        return True

    def _freq(self) -> float:
        return real_frequency(self.model.limit)

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last
        self._last = now
        if self.model.state == ExecState.RUNNING:
            self._run_time += dt
            self._frac += dt * self._freq()
            n = int(self._frac)
            self._frac -= n
            if n:
                res = self.model.advance(n)
                if res.wraps:
                    self._on_wrap(res.wraps)
        self._emit()

    def _on_wrap(self, wraps: int) -> None:
        m = self.model
        steps_since = m.value if m.up else (m.max_value - m.value)
        wrap_rt = self._run_time - steps_since / self._freq()   # instante exato do wrap
        period = 0.0
        if wraps == 1 and self._last_wrap_rt is not None:
            period = wrap_rt - self._last_wrap_rt
        self._last_wrap_rt = wrap_rt
        self.cycle_completed.emit(period)

    def _emit(self) -> None:
        self.state_changed.emit(self.model.snapshot(time.monotonic()))

    # ---- comandos ----
    def start(self) -> None:
        self.model.start()
        self._emit()

    def pause(self) -> None:
        self.model.pause()
        self._emit()

    def reset(self) -> None:
        self.model.reset()
        self._frac = 0.0
        self._last_wrap_rt = None
        self._emit()

    def set_up(self, up: bool) -> None:
        self.model.set_up(up)
        self._last_wrap_rt = None
        self._emit()

    def set_limit(self, enabled: bool) -> None:
        self.model.set_limit(enabled)
        self._last_wrap_rt = None
        self._emit()


# =============================================================================
# Arduino real (serial)
# =============================================================================
class SerialBackend(BaseBackend):
    """Comunica com o firmware `contador16.ino` pela porta serial."""

    name = "serial"
    SILENCE_LIMIT_S = 1.5       # sem frames por este tempo -> comunicacao perdida

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker = SerialWorker(self)
        self._worker.line_received.connect(self._on_line)
        self._worker.link_event.connect(self._on_link_event)
        self._port_open = False
        self._alive = False
        self._last_rx = 0.0
        self._bad_frames = 0

        self._watchdog = QTimer(self)
        self._watchdog.setInterval(250)
        self._watchdog.timeout.connect(self._check_silence)

        self._ping = QTimer(self)               # acorda o Arduino enquanto nao ha frames
        self._ping.setInterval(500)
        self._ping.timeout.connect(lambda: self._send(P.CMD_PING, force=True))

    # ---- ciclo de vida ----
    def activate(self) -> None:
        if not self._worker.isRunning():
            self._worker.start()
        self._watchdog.start()
        self.link_changed.emit("closed", "Desconectado")

    def deactivate(self) -> None:
        self.disconnect_port()
        self._watchdog.stop()

    def shutdown(self) -> None:
        self._watchdog.stop()
        self._ping.stop()
        self._worker.close_port()
        self._worker.stop()

    def connect_port(self, port: str, baud: int) -> None:
        if not port:
            self.notice.emit("error", "Selecione uma porta serial.")
            return
        if baud not in P.BAUD_OPTIONS:
            self.notice.emit("error", f"Velocidade inválida: {baud}")
            return
        self._alive = False
        self._worker.open_port(port, baud)

    def disconnect_port(self) -> None:
        self._worker.close_port()
        self._ping.stop()
        self._alive = False
        self._port_open = False

    def is_ready(self) -> bool:
        return self._alive

    # ---- eventos da thread serial ----
    def _on_link_event(self, kind: str, text: str) -> None:
        if kind == "open":
            self._port_open = True
            self._alive = False
            self._last_rx = time.monotonic()
            self._ping.start()
            self.link_changed.emit("connecting", f"Porta aberta ({text}); aguardando o Arduino…")
        elif kind == "closed":
            self._port_open = False
            self._alive = False
            self._ping.stop()
            self.link_changed.emit("closed", text)
        elif kind == "error":
            self._alive = False
            self.link_changed.emit("error", text)
        elif kind == "lost":
            self._port_open = False
            self._alive = False
            self._ping.stop()
            self.link_changed.emit("lost", text)

    def _on_line(self, line: str) -> None:
        try:
            frame = P.parse_line(line)
        except P.ProtocolError as exc:
            self._bad_frames += 1
            if self._bad_frames == 1 or self._bad_frames % 20 == 0:
                self.notice.emit("warn", f"Linha inválida do Arduino ({self._bad_frames}): {exc}")
            return
        if frame is None:
            return
        self._last_rx = time.monotonic()
        if not self._alive:                      # primeiro frame valido (ou volta apos silencio)
            self._alive = True
            self._ping.stop()
            self.link_changed.emit("connected", "Arduino conectado")

        if isinstance(frame, P.StateFrame):
            self.state_changed.emit(Snapshot(frame.value, frame.up, frame.state, frame.limit,
                                             frame.detect, frame.detections, self._last_rx))
        elif isinstance(frame, P.ButtonFrame):
            self.button_event.emit(frame.name)
        elif isinstance(frame, P.CycleFrame):
            self.cycle_completed.emit(frame.period_us / 1e6)
        elif isinstance(frame, P.ErrFrame):
            self.notice.emit("warn", f"Arduino recusou um comando: {frame.text}")
        # HelloFrame / PongFrame: apenas confirmam que o Arduino esta vivo

    def _check_silence(self) -> None:
        if self._alive and time.monotonic() - self._last_rx > self.SILENCE_LIMIT_S:
            self._alive = False
            self._ping.start()
            self.link_changed.emit("lost", "Sem dados do Arduino (cabo solto ou placa reiniciando?)")

    # ---- comandos ----
    def _send(self, cmd: str, force: bool = False) -> None:
        if not (self._alive or (force and self._port_open)):
            self.notice.emit("warn", "Arduino não conectado: comando ignorado.")
            return
        if not self._worker.send(P.encode_command(cmd)):
            self.notice.emit("warn", "Fila de envio cheia: comando descartado.")

    def start(self) -> None: self._send(P.CMD_START)
    def pause(self) -> None: self._send(P.CMD_PAUSE)
    def reset(self) -> None: self._send(P.CMD_RESET)
    def set_up(self, up: bool) -> None: self._send(P.CMD_UP if up else P.CMD_DOWN)
    def set_limit(self, enabled: bool) -> None: self._send(P.CMD_LIM_ON if enabled else P.CMD_LIM_OFF)
