"""Thread de comunicacao serial (PySerial), separada da interface.

A leitura/escrita acontece em uma QThread, entao a interface nunca trava
esperando o Arduino. A thread:
  * abre a porta pedida e reabre automaticamente se ela cair (a cada 2 s);
  * envia os comandos que estao na fila;
  * separa o fluxo de bytes em linhas e as emite pelo sinal `line_received`;
  * avisa mudancas de conexao pelo sinal `link_event(tipo, mensagem)`.

Tipos de `link_event`: "open", "closed", "error" (falha ao abrir; vai tentar
de novo) e "lost" (a porta caiu com a conexao aberta).
"""
from __future__ import annotations

import queue
import threading
import time

import serial
from serial import SerialException
from serial.tools import list_ports
from PyQt6.QtCore import QThread, pyqtSignal


def list_serial_ports() -> list[tuple[str, str]]:
    """Lista (dispositivo, descricao) das portas seriais disponiveis."""
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    return [(p.device, p.description or p.device) for p in ports]


class SerialWorker(QThread):
    line_received = pyqtSignal(str)
    link_event = pyqtSignal(str, str)

    RECONNECT_S = 2.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._want = False
        self._port: str | None = None
        self._baud = 115200
        self._stop_flag = False
        self._tx: "queue.Queue[bytes]" = queue.Queue(maxsize=64)

    # ---- API chamada pela thread da interface ------------------------------------
    def open_port(self, port: str, baud: int) -> None:
        with self._lock:
            self._port, self._baud, self._want = port, int(baud), True

    def close_port(self) -> None:
        with self._lock:
            self._want = False

    def send(self, data: bytes) -> bool:
        """Enfileira bytes para envio. Retorna False se a fila estiver cheia."""
        try:
            self._tx.put_nowait(data)
            return True
        except queue.Full:
            return False

    def stop(self) -> None:
        self._stop_flag = True
        self.wait(2000)

    # ---- laco da thread ------------------------------------------------------------
    def run(self) -> None:  # noqa: C901 (laco unico, mantido simples de ler)
        ser: serial.Serial | None = None
        current: tuple[str | None, int] | None = None
        announced = False
        next_try = 0.0
        buf = bytearray()

        while not self._stop_flag:
            with self._lock:
                want, port, baud = self._want, self._port, self._baud

            # porta mudou enquanto aberta -> fecha para reabrir com os novos dados
            if ser is not None and (not want or current != (port, baud)):
                self._close(ser)
                ser = None
            if not want:
                if announced:
                    announced = False
                    self.link_event.emit("closed", "Porta fechada")
                self._drain_tx()
                self.msleep(50)
                continue

            if ser is None:
                if time.monotonic() < next_try:
                    self.msleep(50)
                    continue
                try:
                    ser = serial.Serial(port, baud, timeout=0.02, write_timeout=0.5)
                    current = (port, baud)
                    buf.clear()
                    self._drain_tx()
                    announced = True
                    self.link_event.emit("open", f"{port} @ {baud} baud")
                except (SerialException, OSError, ValueError) as exc:
                    ser = None
                    announced = True
                    next_try = time.monotonic() + self.RECONNECT_S
                    self.link_event.emit("error", f"Falha ao abrir {port}: {exc}")
                continue

            try:
                while True:                      # envia comandos pendentes
                    try:
                        data = self._tx.get_nowait()
                    except queue.Empty:
                        break
                    ser.write(data)
                chunk = ser.read(256)            # espera no maximo 20 ms
                if chunk:
                    buf.extend(chunk)
                    self._emit_lines(buf)
            except (SerialException, OSError) as exc:
                self._close(ser)
                ser = None
                next_try = time.monotonic() + self.RECONNECT_S
                self.link_event.emit("lost", f"Conexão perdida: {exc}")

        if ser is not None:
            self._close(ser)

    # ---- auxiliares ------------------------------------------------------------------
    def _emit_lines(self, buf: bytearray) -> None:
        while True:
            idx = buf.find(b"\n")
            if idx < 0:
                break
            raw = bytes(buf[:idx])
            del buf[:idx + 1]
            line = raw.decode("ascii", errors="ignore").strip()
            if line:
                self.line_received.emit(line)
        if len(buf) > 4096:                      # lixo sem quebra de linha
            buf.clear()

    def _drain_tx(self) -> None:
        while True:
            try:
                self._tx.get_nowait()
            except queue.Empty:
                return

    @staticmethod
    def _close(ser: "serial.Serial") -> None:
        try:
            ser.close()
        except Exception:  # fechar nunca deve derrubar a thread
            pass
