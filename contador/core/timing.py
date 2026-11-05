"""Temporizacao: como o clock de 20 s e aproximado pelo Timer1 do Arduino (16 MHz).

Referencia do roteiro:
  * faixa completa: 65.536 estados / 20 s = 3.276,8 Hz   (305,18 us por passo)
  * faixa 0..10000: 10.001 estados / 20 s = 500,05 Hz    (1,9998 ms por passo)

O Timer1 (modo CTC, prescaler 1) so gera periodos multiplos inteiros de 62,5 ns.
Portanto o numero de ciclos por passo e arredondado: 4883 e 31997.
"""
from __future__ import annotations

from .counter_model import STATES_FULL, STATES_LIMIT

CLOCK_HZ = 16_000_000
TARGET_CYCLE_S = 20.0


def states(limit: bool) -> int:
    return STATES_LIMIT if limit else STATES_FULL


def nominal_frequency(limit: bool) -> float:
    """Frequencia ideal (Hz) para completar um ciclo em 20 s."""
    return states(limit) / TARGET_CYCLE_S


def timer_cycles(limit: bool) -> int:
    """Ciclos de clock do Arduino por passo de contagem (inteiro, arredondado)."""
    return round(CLOCK_HZ / nominal_frequency(limit))


def ocr1a(limit: bool) -> int:
    """Valor gravado em OCR1A (o Timer1 conta de 0 ate OCR1A, inclusive)."""
    return timer_cycles(limit) - 1


def real_frequency(limit: bool) -> float:
    """Frequencia realmente gerada pelo Timer1 (Hz)."""
    return CLOCK_HZ / timer_cycles(limit)


def real_cycle_period(limit: bool) -> float:
    """Periodo teorico do ciclo completo com a frequencia real (s)."""
    return states(limit) * timer_cycles(limit) / CLOCK_HZ


def relative_error_pct(measured: float, reference: float = TARGET_CYCLE_S) -> float:
    return (measured - reference) / reference * 100.0
