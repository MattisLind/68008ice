"""Fault cases for the GPIO0..44 report, including GPIO39's LED load."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gpio_connectivity import MASK, PIN_COUNT, decode


def trace(links, stuck_low=0, led_load=0):
    # Model connected wire components. Pulling one vertex LOW affects every
    # vertex in its component, including same-board pins reached via bridges.
    neighbours = {vertex: set() for vertex in range(2 * PIN_COUNT)}
    for source, sink in links:
        a, b = source, PIN_COUNT + sink
        neighbours[a].add(b)
        neighbours[b].add(a)
    idle = MASK & ~stuck_low & ~led_load
    lines = ["BOARD 1 F3217B63D8F6A7A5", "BOARD 2 AC740FAC748891BF",
             f"FORMAT 2 {PIN_COUNT}", "BASELINE 0 0 0", f"BASELINE 1 {idle} {idle}"]
    for high in (0, 1):
        baseline = 0 if high else idle
        for board in (1, 2):
            for pin in range(PIN_COUNT):
                pending = [(board - 1) * PIN_COUNT + pin]
                connected = set()
                while pending:
                    node = pending.pop()
                    if node not in connected:
                        connected.add(node)
                        pending.extend(neighbours[node] - connected)
                active = [sum(1 << (n % PIN_COUNT) for n in connected if n // PIN_COUNT == index)
                          for index in (0, 1)]
                values = [(baseline | bits) & ~stuck_low if high else baseline & ~bits for bits in active]
                source, receive = values[board - 1], values[2 - board]
                lines.append(f"SCAN {high} {board} {pin} {baseline} {baseline} {source} {receive} {source} {receive}")
                lines.append(f"RELEASE {high} {board} {pin} {baseline} {baseline}")
    lines.append("GPIO CONNECTIVITY SCAN COMPLETE")
    return "\n".join(lines)


class WiringReportTests(unittest.TestCase):
    def test_all_same_number_including_high_bank(self):
        report = decode(trace([(pin, pin) for pin in range(PIN_COUNT)]))
        self.assertEqual(report["passed"], 45)

    def test_open_gpio44(self):
        report = decode(trace([(pin, pin) for pin in range(44)]))
        self.assertEqual(report["passed"], 44)
        self.assertEqual(report["rows"][44]["status"], "NO_CONNECTION_DETECTED")

    def test_swap_across_banks(self):
        links = [(pin, 44 if pin == 0 else 0 if pin == 44 else pin) for pin in range(PIN_COUNT)]
        report = decode(trace(links))
        self.assertEqual(report["passed"], 43)
        for pin, target in ((0, 44), (44, 0)):
            self.assertEqual(report["rows"][pin]["status"], "WRONG_PIN")
            self.assertEqual(report["rows"][pin]["board1_to_board2"], [target])

    def test_bridge_reports_every_observed_pin(self):
        report = decode(trace([(pin, pin) for pin in range(PIN_COUNT)] + [(0, 1)]))
        self.assertEqual(report["passed"], 43)
        for pin in (0, 1):
            self.assertEqual(report["rows"][pin]["board1_to_board2"], [0, 1])
            self.assertNotEqual(report["rows"][pin]["status"], "PASS")

    def test_held_low_is_not_called_an_open_wire(self):
        report = decode(trace([(pin, pin) for pin in range(PIN_COUNT)], stuck_low=1 << 12))
        self.assertEqual(report["rows"][12]["status"], "ELECTRICAL_OR_UNSTABLE")
        self.assertIn(12, report["bias"]["1"]["low_despite_pull_up"])

    def test_unstable_observation_is_not_reported_as_good(self):
        lines = trace([(pin, pin) for pin in range(PIN_COUNT)]).splitlines()
        for index, line in enumerate(lines):
            if line.startswith("SCAN 1 1 5 "):
                fields = line.split()
                fields[-1] = str(int(fields[-1]) ^ (1 << 5))
                lines[index] = " ".join(fields)
        report = decode("\n".join(lines))
        self.assertNotEqual(report["rows"][5]["status"], "PASS")

    def test_incomplete_scan_is_rejected(self):
        data = trace([(pin, pin) for pin in range(PIN_COUNT)])
        data = "\n".join(line for line in data.splitlines() if not line.startswith("RELEASE 1 2 44 "))
        with self.assertRaises(RuntimeError):
            decode(data)

    def test_led_bias_load_does_not_invent_an_open(self):
        report = decode(trace([(pin, pin) for pin in range(PIN_COUNT)], led_load=1 << 39))
        self.assertEqual(report["passed"], 45)
        self.assertIn(39, report["bias"]["1"]["low_despite_pull_up"])

    def test_unloaded_led_pin_also_requires_low_response(self):
        report = decode(trace([(pin, pin) for pin in range(PIN_COUNT)]))
        self.assertEqual(report["rows"][39]["low_board1_to_board2"], [39])
        self.assertEqual(report["rows"][39]["low_board2_to_board1"], [39])

    def test_led_load_does_not_hide_real_open(self):
        report = decode(trace([(pin, pin) for pin in range(PIN_COUNT) if pin != 39], led_load=1 << 39))
        self.assertEqual(report["rows"][39]["status"], "NO_CONNECTION_DETECTED")

    def test_led_pin_cross_wiring(self):
        links = [(pin, 39 if pin == 44 else 44 if pin == 39 else pin) for pin in range(PIN_COUNT)]
        report = decode(trace(links, led_load=1 << 39))
        self.assertEqual(report["rows"][39]["status"], "WRONG_PIN")
        self.assertEqual(report["rows"][44]["status"], "WRONG_PIN")

    def test_old_range_is_rejected(self):
        data = trace([(pin, pin) for pin in range(PIN_COUNT)]).replace("FORMAT 2 45", "FORMAT 2 39")
        with self.assertRaises(RuntimeError):
            decode(data)


if __name__ == "__main__":
    unittest.main()
