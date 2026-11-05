"""Testes da logica do contador: UP, DOWN, START, PAUSE, RESET e deteccao de 10.000.

Executar (na pasta do projeto):  python -m unittest discover -s tests -v
"""
import random
import unittest

from contador.core.counter_model import (
    CounterModel, ExecState, LIMIT_VALUE, MAX_VALUE, bits_of, progress_fraction,
)


def firmware_step(value, up, limit):
    """Passo unitario escrito igual a ISR do firmware (referencia independente).

    Retorna (novo_valor, houve_wrap, atingiu_10000).
    """
    wrap = False
    if up:
        if limit:
            if value >= LIMIT_VALUE:
                value, wrap = 0, True
            else:
                value += 1
        else:
            if value == 0xFFFF:
                wrap = True
            value = (value + 1) & 0xFFFF
    else:
        if value == 0:
            wrap = True
            value = LIMIT_VALUE if limit else 0xFFFF
        else:
            value -= 1
    return value, wrap, value == LIMIT_VALUE


def running_model(value=0, up=True, limit=False):
    m = CounterModel()
    m.value, m.up, m.limit = value, up, limit
    m.start()
    return m


class TestCountingUp(unittest.TestCase):
    def test_up_counts_and_wraps_full_range(self):
        m = running_model(0, up=True)
        m.advance(1)
        self.assertEqual(m.value, 1)
        m = running_model(MAX_VALUE, up=True)
        r = m.advance(1)
        self.assertEqual(m.value, 0)
        self.assertEqual(r.wraps, 1)

    def test_up_limited_wraps_after_10000(self):
        m = running_model(9999, up=True, limit=True)
        m.advance(1)
        self.assertEqual(m.value, 10000)
        r = m.advance(1)
        self.assertEqual(m.value, 0)
        self.assertEqual(r.wraps, 1)


class TestCountingDown(unittest.TestCase):
    def test_down_wraps_full_range(self):
        m = running_model(1, up=False)
        m.advance(1)
        self.assertEqual(m.value, 0)
        r = m.advance(1)
        self.assertEqual(m.value, MAX_VALUE)
        self.assertEqual(r.wraps, 1)

    def test_down_limited_wraps_to_10000(self):
        m = running_model(0, up=False, limit=True)
        r = m.advance(1)
        self.assertEqual(m.value, LIMIT_VALUE)
        self.assertEqual(r.wraps, 1)


class TestControls(unittest.TestCase):
    def test_start_and_pause_keep_value(self):
        m = CounterModel()
        m.start()
        m.advance(500)
        m.pause()
        self.assertEqual(m.state, ExecState.PAUSED)
        frozen = m.value
        m.advance(1000)                      # pausado: nao deve contar
        self.assertEqual(m.value, frozen)
        m.start()
        m.advance(1)
        self.assertEqual(m.value, frozen + 1)

    def test_no_count_when_stopped(self):
        m = CounterModel()
        m.advance(100)
        self.assertEqual(m.value, 0)

    def test_reset_initial_value_per_mode(self):
        m = running_model(1234, up=True)
        m.reset()
        self.assertEqual((m.value, m.state), (0, ExecState.STOPPED))
        m.set_up(False)
        m.reset()
        self.assertEqual(m.value, MAX_VALUE)
        m.set_limit(True)
        m.reset()
        self.assertEqual(m.value, LIMIT_VALUE)
        m.set_up(True)
        m.reset()
        self.assertEqual(m.value, 0)

    def test_enabling_limit_above_10000_goes_to_initial_value(self):
        m = running_model(40000, up=True)
        m.set_limit(True)
        self.assertEqual(m.value, 0)
        m = running_model(40000, up=False)
        m.set_limit(True)
        self.assertEqual(m.value, LIMIT_VALUE)

    def test_toggle_run(self):
        m = CounterModel()
        m.toggle_run()
        self.assertEqual(m.state, ExecState.RUNNING)
        m.toggle_run()
        self.assertEqual(m.state, ExecState.PAUSED)


class TestLimitDetection(unittest.TestCase):
    def test_detect_flag_only_at_10000(self):
        m = CounterModel()
        for v, expected in [(9999, False), (10000, True), (10001, False), (0, False)]:
            m.value = v
            self.assertEqual(m.detect, expected, v)

    def test_bit_pattern_of_10000(self):
        # 10000 = 0010 0111 0001 0000 (Q15..Q0)
        self.assertEqual(bits_of(10000), [0,0,1,0, 0,1,1,1, 0,0,0,1, 0,0,0,0])

    def test_detection_counted_once_per_pass(self):
        m = running_model(9990, up=True)
        r = m.advance(20)
        self.assertEqual(r.detections, 1)
        self.assertEqual(m.detections, 1)


class TestSynchronization(unittest.TestCase):
    def test_decimal_hex_bits_always_consistent(self):
        rnd = random.Random(1)
        for _ in range(500):
            v = rnd.randint(0, MAX_VALUE)
            bits = bits_of(v)
            rebuilt = int("".join(map(str, bits)), 2)
            self.assertEqual(rebuilt, v)
            self.assertEqual(int(f"{v:04X}", 16), v)

    def test_progress_fraction(self):
        self.assertEqual(progress_fraction(0, True, False), 0.0)
        self.assertEqual(progress_fraction(MAX_VALUE, True, False), 1.0)
        self.assertEqual(progress_fraction(MAX_VALUE, False, False), 0.0)
        self.assertEqual(progress_fraction(10000, True, True), 1.0)
        self.assertEqual(progress_fraction(0, False, True), 1.0)


class TestAdvanceMatchesFirmwareStepByStep(unittest.TestCase):
    """advance(n) (aritmetica modular) deve ser igual a n passos unitarios."""

    def test_random_scenarios(self):
        rnd = random.Random(42)
        for _ in range(400):
            limit = rnd.random() < 0.5
            up = rnd.random() < 0.5
            top = LIMIT_VALUE if limit else MAX_VALUE
            start = rnd.randint(0, top)
            n = rnd.choice([1, 2, 7, 100, 5000, 10001, 10002, 65536, 70000, 131075])
            m = running_model(start, up, limit)
            res = m.advance(n)
            v, wraps, dets = start, 0, 0
            for _ in range(n):
                v, w, d = firmware_step(v, up, limit)
                wraps += w
                dets += d
            self.assertEqual((m.value, res.wraps, res.detections), (v, wraps, dets),
                             f"limit={limit} up={up} start={start} n={n}")


if __name__ == "__main__":
    unittest.main()
