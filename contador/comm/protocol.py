"""Protocolo serial (texto, uma mensagem por linha, terminada em '\\n').

Por que um protocolo proprio e nao Firmata?
  O roteiro permite Firmata para E/S simples, mas aqui o Arduino precisa rodar
  o Timer1 e a logica do contador sozinho e enviar um estado completo
  (valor, sentido, estado, limite, deteccao) a 20 Hz, alem de eventos dos botoes
  fisicos e do periodo medido. Firmata nao carrega esse tipo de mensagem.

PC -> Arduino (comandos, ASCII maiusculo):
    START  PAUSE  RESET  UP  DOWN  LIM1  LIM0  PING  STATUS

Arduino -> PC:
    H,CONTADOR16,1                       saudacao ao ligar/resetar (nome, versao)
    PONG                                 resposta ao PING
    S,valor,up,estado,limite,det,ndet    estado do contador (20 Hz e a cada mudanca)
        valor  : 0..65535
        up     : 1 = UP, 0 = DOWN
        estado : 0 = parado, 1 = contando, 2 = pausado
        limite : 1 = limite de 10.000 ativo
        det    : 1 = valor atual == 10.000
        ndet   : vezes que 10.000 foi atingido desde o RESET (0..65535)
    B,START|DIR|RESET|LIMIT              botao fisico acionado
    C,periodo_us                         fim de ciclo; periodo em microssegundos
                                         (0 = sem medida valida neste ciclo)
    ERR,texto                            comando desconhecido

Niveis logicos: botoes fisicos usam INPUT_PULLUP -> ATIVOS EM NIVEL 0 (LOW).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.counter_model import ExecState, MAX_VALUE

BAUD_DEFAULT = 115_200
BAUD_OPTIONS = (9600, 19200, 38400, 57600, 115200, 230400)

CMD_START = "START"
CMD_PAUSE = "PAUSE"
CMD_RESET = "RESET"
CMD_UP = "UP"
CMD_DOWN = "DOWN"
CMD_LIM_ON = "LIM1"
CMD_LIM_OFF = "LIM0"
CMD_PING = "PING"
CMD_STATUS = "STATUS"
ALL_COMMANDS = frozenset({CMD_START, CMD_PAUSE, CMD_RESET, CMD_UP, CMD_DOWN,
                          CMD_LIM_ON, CMD_LIM_OFF, CMD_PING, CMD_STATUS})

BUTTON_NAMES = frozenset({"START", "DIR", "RESET", "LIMIT"})


class ProtocolError(ValueError):
    """Linha recebida invalida ou comando desconhecido."""


@dataclass(frozen=True)
class StateFrame:
    value: int
    up: bool
    state: ExecState
    limit: bool
    detect: bool
    detections: int


@dataclass(frozen=True)
class ButtonFrame:
    name: str


@dataclass(frozen=True)
class CycleFrame:
    period_us: int


@dataclass(frozen=True)
class HelloFrame:
    name: str
    version: str


@dataclass(frozen=True)
class PongFrame:
    pass


@dataclass(frozen=True)
class ErrFrame:
    text: str


def encode_command(cmd: str) -> bytes:
    if cmd not in ALL_COMMANDS:
        raise ProtocolError(f"comando desconhecido: {cmd!r}")
    return f"{cmd}\n".encode("ascii")


def _to_int(text: str, lo: int, hi: int, what: str) -> int:
    try:
        n = int(text)
    except ValueError as exc:
        raise ProtocolError(f"{what} nao numerico: {text!r}") from exc
    if not lo <= n <= hi:
        raise ProtocolError(f"{what} fora da faixa {lo}..{hi}: {n}")
    return n


def parse_line(line: str):
    """Converte uma linha em um frame. Linha vazia -> None. Invalida -> ProtocolError."""
    line = line.strip()
    if not line:
        return None
    if line == "PONG":
        return PongFrame()
    parts = line.split(",")
    tag = parts[0]
    if tag == "S":
        if len(parts) != 7:
            raise ProtocolError(f"frame S com {len(parts)} campos (esperado 7)")
        value = _to_int(parts[1], 0, MAX_VALUE, "valor")
        up = _to_int(parts[2], 0, 1, "up")
        state = _to_int(parts[3], 0, 2, "estado")
        limit = _to_int(parts[4], 0, 1, "limite")
        det = _to_int(parts[5], 0, 1, "det")
        ndet = _to_int(parts[6], 0, 0xFFFF, "ndet")
        return StateFrame(value, bool(up), ExecState(state), bool(limit), bool(det), ndet)
    if tag == "B":
        if len(parts) != 2 or parts[1] not in BUTTON_NAMES:
            raise ProtocolError(f"frame B invalido: {line!r}")
        return ButtonFrame(parts[1])
    if tag == "C":
        if len(parts) != 2:
            raise ProtocolError(f"frame C invalido: {line!r}")
        return CycleFrame(_to_int(parts[1], 0, 2**32 - 1, "periodo_us"))
    if tag == "H":
        if len(parts) != 3:
            raise ProtocolError(f"frame H invalido: {line!r}")
        return HelloFrame(parts[1], parts[2])
    if tag == "ERR":
        return ErrFrame(",".join(parts[1:]))
    raise ProtocolError(f"frame desconhecido: {line!r}")
