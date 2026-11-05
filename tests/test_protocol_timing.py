"""Testes do protocolo serial e da temporizacao de 20 s."""
import unittest

from contador.comm import protocol as P
from contador.core import timing as T
from contador.core.counter_model import ExecState


class TestProtocol(unittest.TestCase):
    def test_parse_state_frame(self):
        f = P.parse_line("S,10000,1,1,1,1,3\n")
        self.assertEqual(f, P.StateFrame(10000, True, ExecState.RUNNING, True, True, 3))

    def test_parse_other_frames(self):
        self.assertEqual(P.parse_line("B,DIR"), P.ButtonFrame("DIR"))
        self.assertEqual(P.parse_line("C,20000770"), P.CycleFrame(20000770))
        self.assertEqual(P.parse_line("H,CONTADOR16,1"), P.HelloFrame("CONTADOR16", "1"))
        self.assertEqual(P.parse_line("PONG"), P.PongFrame())
        self.assertIsNone(P.parse_line("   \r\n"))

    def test_invalid_lines_raise(self):
        bad = ["S,1,2,3", "S,70000,1,1,0,0,0", "S,5,1,3,0,0,0", "S,a,1,1,0,0,0",
               "B,XYZ", "C", "X,1,2", "lixo"]
        for line in bad:
            with self.assertRaises(P.ProtocolError, msg=line):
                P.parse_line(line)

    def test_encode_commands(self):
        for cmd in P.ALL_COMMANDS:
            self.assertEqual(P.encode_command(cmd), (cmd + "\n").encode("ascii"))
        with self.assertRaises(P.ProtocolError):
            P.encode_command("FOO")


class TestTiming(unittest.TestCase):
    def test_nominal_frequencies_match_pdf(self):
        self.assertAlmostEqual(T.nominal_frequency(False), 3276.8, places=6)
        self.assertAlmostEqual(T.nominal_frequency(True), 500.05, places=6)

    def test_timer_values_used_by_firmware(self):
        self.assertEqual(T.timer_cycles(False), 4883)
        self.assertEqual(T.ocr1a(False), 4882)
        self.assertEqual(T.timer_cycles(True), 31997)
        self.assertEqual(T.ocr1a(True), 31996)

    def test_cycle_period_within_0_01_percent_of_20s(self):
        for limit in (False, True):
            err = abs(T.relative_error_pct(T.real_cycle_period(limit)))
            self.assertLess(err, 0.01, f"limit={limit} erro={err}%")


if __name__ == "__main__":
    unittest.main()
