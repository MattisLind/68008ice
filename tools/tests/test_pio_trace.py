"""Check exported trace integrity independently of the device VCD writer."""
import copy
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pio_trace import check_vcd


def fixture(bank):
    base, width = (32, 13) if bank else (0, 32)
    # Include simultaneous changes and repeated samples: an analyzer must
    # preserve actual observations rather than replace them with its test pattern.
    values = [(i ^ (i >> 1)) & ((1 << width) - 1) for i in range(1024)]
    values[13] = values[12]
    values[14] ^= 0x555
    raw = struct.pack("<1024I", *values)
    lines = ["$timescale 1ps $end"]
    lines += [f"$var wire 1 p{bit} GPIO{base + bit} $end" for bit in range(width)]
    lines += ["$enddefinitions $end"]
    for i, value in enumerate(values):
        lines.append(f"#{i * 10**12 // 150000000}")
        lines += [f"{(value >> bit) & 1}p{bit}" for bit in range(width)]
    data = ("\n".join(lines) + "\n").encode()
    mailbox = [0] * 16
    mailbox[8:10] = [150000000, 1024]
    mailbox[12:15] = [len(data), zlib.crc32(data), zlib.crc32(raw)]
    return data, raw, mailbox


class TraceIntegrity(unittest.TestCase):
    def test_both_banks_preserve_observations(self):
        for bank in (0, 1):
            data, raw, mailbox = fixture(bank)
            result = check_vcd(data, raw, bank, mailbox)
            self.assertEqual(result["samples"], 1024)
            self.assertGreater(result["repeated_samples"], 0)
            self.assertGreater(result["multi_bit_transitions"], 0)

    def test_corrupt_payload_rejected(self):
        data, raw, mailbox = fixture(0)
        with self.assertRaisesRegex(RuntimeError, "CRC"):
            check_vcd(data + b"\n", raw, 0, mailbox)

    def test_raw_disagreement_rejected(self):
        data, raw, mailbox = fixture(1)
        raw = bytes([raw[0] ^ 1]) + raw[1:]
        with self.assertRaisesRegex(RuntimeError, "raw SRAM"):
            check_vcd(data, raw, 1, mailbox)

    def test_wrong_bank_rejected(self):
        data, raw, mailbox = fixture(0)
        with self.assertRaisesRegex(RuntimeError, "pin set"):
            check_vcd(data, raw, 1, mailbox)

    def test_wrong_timebase_rejected(self):
        data, raw, mailbox = fixture(0)
        mailbox[8] = 125000000
        with self.assertRaisesRegex(RuntimeError, "timebase"):
            check_vcd(data, raw, 0, mailbox)

    def test_incomplete_and_stalled_transfers_rejected(self):
        data, raw, mailbox = fixture(0)
        for field, value in ((7, 2), (9, 1023), (10, 1), (11, 1)):
            bad = copy.copy(mailbox)
            bad[field] = value
            with self.assertRaises(RuntimeError):
                check_vcd(data, raw, 0, bad)


if __name__ == "__main__":
    unittest.main()
