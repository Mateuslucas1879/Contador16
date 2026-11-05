"""Modelo do contador de 16 bits (logica pura, sem Qt e sem serial).

Este modulo e a "fonte da verdade" da logica de contagem no lado do PC.
E usado:
  * pela simulacao local (quando nao ha Arduino conectado);
  * pelos testes automaticos, que comparam o modelo com a logica do firmware.

Com o Arduino conectado, o valor real vem do Arduino (Timer1) e este modelo
NAO e usado para gerar dados: a interface apenas exibe o que o Arduino envia.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

BITS = 16
MAX_VALUE = 0xFFFF              # 65.535
STATES_FULL = 65_536            # estados da faixa completa (0..65535)
LIMIT_VALUE = 10_000            # valor detectado / limite superior no modo limitado
STATES_LIMIT = LIMIT_VALUE + 1  # 10.001 estados (0..10000, inclusive)


class ExecState(IntEnum):
    """Estado de execucao. REINICIALIZANDO e apenas visual (transitorio na interface)."""
    STOPPED = 0   # parado (inicio ou apos RESET)
    RUNNING = 1   # contando
    PAUSED = 2    # pausado (valor preservado)


@dataclass(frozen=True)
class Snapshot:
    """Foto do estado do contador em um instante (enviada do backend para a interface)."""
    value: int
    up: bool
    state: ExecState
    limit: bool          # limite de 10.000 ativo?
    detect: bool         # valor atual == 10.000 (sinal de deteccao)
    detections: int      # quantas vezes o valor 10.000 foi atingido desde o RESET
    t: float = 0.0       # time.monotonic() do recebimento/geracao


@dataclass(frozen=True)
class AdvanceResult:
    wraps: int = 0        # quantas vezes o ciclo reiniciou
    detections: int = 0   # quantas vezes o valor 10.000 foi atingido
    steps: int = 0


def bits_of(value: int) -> list[int]:
    """Retorna os 16 bits na ordem [Q15, Q14, ..., Q0]."""
    return [(value >> i) & 1 for i in range(BITS - 1, -1, -1)]


def progress_fraction(value: int, up: bool, limit: bool) -> float:
    """Fracao (0..1) percorrida no ciclo. UP: cresce de 0 a max; DOWN: de max a 0."""
    max_v = LIMIT_VALUE if limit else MAX_VALUE
    v = min(max(value, 0), max_v)
    frac = v / max_v if up else (max_v - v) / max_v
    return min(max(frac, 0.0), 1.0)


class CounterModel:
    """Contador de 16 bits UP/DOWN com limite opcional de 10.000.

    Regras (mesmas do firmware do Arduino):
      * Faixa completa UP:   0 -> 65535 -> 0 ...
      * Faixa completa DOWN: 65535 -> 0 -> 65535 ...
      * Limitado UP:         0 -> 10000 -> 0 ...
      * Limitado DOWN:       10000 -> 0 -> 10000 ...
      * RESET: valor inicial do sentido (UP: 0; DOWN: 65535, ou 10000 se limitado).
      * Ativar o limite com valor > 10000 leva ao valor inicial do sentido.
    """

    def __init__(self) -> None:
        self.value = 0
        self.up = True
        self.limit = False
        self.state = ExecState.STOPPED
        self.detections = 0

    # ---- propriedades derivadas -------------------------------------------------
    @property
    def modulus(self) -> int:
        return STATES_LIMIT if self.limit else STATES_FULL

    @property
    def max_value(self) -> int:
        return self.modulus - 1

    @property
    def detect(self) -> bool:
        return self.value == LIMIT_VALUE

    def initial_value(self) -> int:
        return 0 if self.up else self.max_value

    # ---- comandos ----------------------------------------------------------------
    def start(self) -> None:
        self.state = ExecState.RUNNING

    def pause(self) -> None:
        if self.state == ExecState.RUNNING:
            self.state = ExecState.PAUSED   # preserva o valor

    def toggle_run(self) -> None:
        if self.state == ExecState.RUNNING:
            self.pause()
        else:
            self.start()

    def reset(self) -> None:
        self.state = ExecState.STOPPED
        self.value = self.initial_value()
        self.detections = 0

    def set_up(self, up: bool) -> None:
        self.up = bool(up)

    def set_limit(self, enabled: bool) -> None:
        self.limit = bool(enabled)
        if self.limit and self.value > LIMIT_VALUE:
            self.value = self.initial_value()

    # ---- avanco no tempo ---------------------------------------------------------
    def advance(self, steps: int) -> AdvanceResult:
        """Aplica `steps` pulsos de clock de uma vez (aritmetica modular).

        Equivale a chamar o passo unitario `steps` vezes, mas em tempo O(1).
        So avanca se o estado for RUNNING.
        """
        if steps <= 0 or self.state != ExecState.RUNNING:
            return AdvanceResult()
        m, v, t = self.modulus, self.value, LIMIT_VALUE
        if self.up:
            wraps = (v + steps) // m
            det = (v + steps - t) // m - (v - t) // m
            self.value = (v + steps) % m
        else:
            wraps = (steps - v + m - 1) // m if steps > v else 0
            det = (v - 1 - t) // m - (v - steps - 1 - t) // m
            self.value = (v - steps) % m
        self.detections = (self.detections + det) & 0xFFFF
        return AdvanceResult(wraps=wraps, detections=det, steps=steps)

    def snapshot(self, t: float = 0.0) -> Snapshot:
        return Snapshot(self.value, self.up, self.state, self.limit,
                        self.detect, self.detections, t)
