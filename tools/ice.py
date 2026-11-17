#!/usr/bin/env python3
"""USB CDC command interface for the Core2350B core-0 dispatcher."""
from __future__ import annotations
import argparse
import glob
import json
import os
from pathlib import Path
import secrets
import select
import struct
import sys
import time
import zlib

MAX_PAYLOAD = 256
APPS = {"generator": 1, "analyzer": 2, "bus-generator": 3, "bus-memory": 4, "state-analyzer": 5, "cpu-emulator": 6, "generic-memory": 4, "abc1600-memory": 7}
SOURCES = {"flash": 0, "psram": 1, "uploaded": 2}
JOB_FIELDS = "bank trigger_gpio trigger_level timeout_ms flags state error start abort hz samples fdebug remaining raw_crc vcd_bytes vcd_crc".split()
POSITIONS = {"early": 10, "middle": 50, "late": 90}
CAPTURE_FIELDS = "magic version committed bank app count stride hz trigger first_sequence flags bytes crc capacity pre_percent edge_config".split()
STATES = {0: "idle", 1: "preparing", 2: "armed", 3: "running", 4: "done", 5: "error", 6: "saving", 7: "raw_done"}


def encode(op, seq, payload=b"", status=0):
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("Payload exceeds 256 bytes")
    raw = struct.pack("<BBHHH", 1, op, seq, len(payload), status) + payload
    raw += struct.pack("<I", zlib.crc32(raw))
    return b"\xff\x00" + raw.replace(b"\xff", b"\xff\xff") + b"\xff\x01"


class DeviceError(RuntimeError):
    def __init__(self, op, status):
        self.status = status
        super().__init__(f"Device command {op} rejected (status {status})")


class Decoder:
    def __init__(self):
        self.active = self.escape = False
        self.raw = bytearray()

    def feed(self, data):
        frames = []
        for b in data:
            if self.escape:
                self.escape = False
                if b == 0:
                    self.active = True
                    self.raw.clear()
                    continue
                if b == 1:
                    if self.active and len(self.raw) >= 12:
                        raw = self.raw
                        version, op, seq, length, status = struct.unpack_from("<BBHHH", raw)
                        if version == 1 and length <= 256 and len(raw) == length + 12 and zlib.crc32(raw[:-4]) == struct.unpack_from("<I", raw, len(raw)-4)[0]:
                            frames.append((op, seq, status, bytes(raw[8:-4])))
                    self.active = False
                    continue
                if b != 255:
                    self.active = False
                    self.raw.clear()
                    continue
            elif b == 255:
                self.escape = True
                continue
            if self.active:
                self.raw.append(b)
                if len(self.raw) > 268:
                    self.active = False
                    self.raw.clear()
        return frames


class SerialPort:
    """No dependencies on macOS/Linux; pyserial backend on Windows."""
    def __init__(self, path):
        self.serial = None
        if os.name == "nt":
            import serial  # pip install pyserial
            self.serial = serial.Serial(path, 115200, timeout=0.1, write_timeout=2)
        else:
            import termios
            self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                attrs = termios.tcgetattr(self.fd)
                attrs[0] = attrs[1] = attrs[3] = 0
                attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
                attrs[4] = attrs[5] = termios.B115200
                attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
                termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            except BaseException:
                os.close(self.fd)
                raise

    def write(self, data):
        if self.serial:
            self.serial.write(data)
            return
        deadline = time.monotonic() + 3
        while data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.fd], [], remaining)[1]:
                raise TimeoutError("CDC write timed out")
            data = data[os.write(self.fd, data):]

    def read(self, timeout):
        if self.serial:
            self.serial.timeout = timeout
            return self.serial.read(1024)
        if select.select([self.fd], [], [], timeout)[0]:
            return os.read(self.fd, 1024)
        return b""

    def close(self):
        if self.serial:
            self.serial.close()
        else:
            os.close(self.fd)


class Device:
    def __init__(self, port):
        self.port = SerialPort(port)
        self.decoder = Decoder()
        self.seq = secrets.randbelow(65535)
        try:
            self.info = json.loads(self.request(1))
        except BaseException:
            self.close()
            raise
        if self.info.get("protocol") != 1:
            self.close()
            raise RuntimeError("Unsupported dispatcher protocol")

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    def close(self): self.port.close()

    def request(self, op, payload=b"", timeout=10):
        self.seq = (self.seq + 1) & 65535
        frame = encode(op, self.seq, payload)
        for attempt in range(2):
            self.port.write(frame)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                for cmd, seq, status, response in self.decoder.feed(self.port.read(max(0, min(.2, deadline-time.monotonic())))):
                    if seq == self.seq and cmd == (op | 0x80):
                        if status:
                            raise DeviceError(op, status)
                        return response
        raise TimeoutError(f"No valid CDC response for command {op}")

    def status(self):
        result = dict(zip(JOB_FIELDS, struct.unpack("<16I", self.request(6))))
        result["state_name"] = STATES.get(result["state"], "unknown")
        return result

    def load(self, app, source):
        self.request(3, struct.pack("<2I", APPS[app], SOURCES[source]))
        self.info["app"] = APPS[app]

    def run(self, bank, gpio, level, timeout_ms, flags=0, config=None):
        payload = struct.pack("<5I", bank, gpio, level, timeout_ms, flags)
        if config is not None:
            payload += struct.pack("<12I", *config)
        self.request(4, payload)
        result = self.wait(states=(2, 4), timeout=5)
        if config and config[2] == 150000000 and self.info.get("app") == 4:
            self.request(5)  # ACK reaches USB before the full-rate sampler starts
            time.sleep(.01)
            result["start"] = 1
        return result

    def wait(self, states=(4,), timeout=35):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.status()
            if status["state"] in states:
                return status
            if status["state"] == 5:
                raise RuntimeError(f"Application failed: {status}")
            time.sleep(.025)
        raise TimeoutError("Application did not reach requested state")

    def cpu_status(self):
        fields = "version state ssp pc sr opcode instructions reads resets fault address fc reset_seen halt_asserted reset_level halt_level".split()
        result = dict(zip(fields, struct.unpack("<16I", self.request(19))))
        result["state_name"] = {0: "wait_reset", 1: "reset_vector", 2: "running", 3: "stopped", 4: "halted", 5: "failed", 6: "paused"}.get(result["state"], "unknown")
        return result

    def cpu_registers(self):
        return decode_cpu_registers(self.request(25))

    def cpu_trace(self):
        version, count, total, dropped = struct.unpack("<4I", self.request(26, struct.pack("<I", 0xffffffff)))
        if version != 1 or count > 128 or total != count + dropped:
            raise ValueError("Invalid CPU trace metadata")
        return dict(version=version, count=count, total=total, dropped=dropped,
                    snapshots=[decode_cpu_registers(self.request(26, struct.pack("<I", i))) for i in range(count)])

    def memory_info(self):
        return dict(zip("version capacity bytes crc used ready".split(), struct.unpack("<6I", self.request(24))))

    def memory_load(self, image):
        if not 8 <= len(image) <= 1048576:
            raise ValueError("ROM must contain 8..1048576 bytes")
        crc = zlib.crc32(image)
        self.request(21, struct.pack("<2I", len(image), crc))
        for offset in range(0, len(image), 252):
            self.request(22, struct.pack("<I", offset) + image[offset:offset+252])
        self.request(23)
        result = self.memory_info()
        if not result["ready"] or result["crc"] != crc or self.read_data(4, 0, len(image)) != image:
            raise ValueError("ROM upload readback mismatch")
        return result

    def abc1600_status(self):
        fields = "version task boote magic cause reset_button partst cause_reads segment_writes page_high_writes page_low_writes task_writes ram_reads ram_writes bus_errors unsupported_io last_address last_physical last_fc last_write last_target".split()
        return dict(zip(fields, struct.unpack("<21I", self.request(28))))

    def boot_status(self):
        fields = "version profile reset_asserted reset_released halt_seen cycles reads writes first_address last_address first_fc last_fc fc_errors reset_low_us reset_high_us halt_low_us".split()
        return dict(zip(fields, struct.unpack("<16I", self.request(20))))

    def read_data(self, kind, bank, length, offset=0):
        result = bytearray()
        while len(result) < length:
            chunk = self.request(9, struct.pack("<4I", kind, bank, offset+len(result), min(256, length-len(result))))
            if not chunk:
                raise RuntimeError("Device returned an empty data chunk")
            result += chunk
        return bytes(result)

    def fetch(self, bank):
        record = struct.unpack("<16I", self.request(8, struct.pack("<I", bank)))
        data = self.read_data(0, bank, record[8])
        if zlib.crc32(data) != record[9]:
            raise RuntimeError("Downloaded VCD CRC differs from flash record")
        return data

    def fetch_capture(self, bank):
        record = dict(zip(CAPTURE_FIELDS, struct.unpack("<16I", self.request(16, struct.pack("<I", bank)))))
        validate_capture(record)
        raw = self.read_data(2, bank, record["bytes"])
        return record, raw, capture_vcd(record, raw)

    def stop(self, discard=False):
        if discard:
            self.request(7)
        else:
            try:
                self.request(17)
            except DeviceError as exc:
                if exc.status not in (2, 5):
                    raise
                self.request(7)
        return self.wait(states=(0, 4, 5))

    def upload(self, image):
        header = validate_image(image)
        self.request(12, struct.pack("<I", len(image)))
        for offset in range(0, len(image), 252):
            self.request(13, struct.pack("<I", offset) + image[offset:offset+252])
        self.request(14)
        return header


def decode_cpu_registers(raw):
    values = struct.unpack("<35I", raw)
    fields = "version state ssp pc sr opcode instructions reads resets fault address fc reset_seen halt_asserted reset_level halt_level".split()
    result = dict(zip(fields, values[:16]))
    result.update(d=list(values[16:24]), a=list(values[24:32]), usp=values[32], writes=values[33], instruction_pc=values[34])
    if result["version"] != 2:
        raise ValueError("Unsupported CPU register report")
    return result


def validate_image(image):
    if len(image) < 30:
        raise ValueError("Truncated application image")
    magic, abi, app, address, entry, length, crc = struct.unpack_from("<7I", image)
    if (magic != 0x41505031 or abi != 2 or app not in range(1, 8) or address != 0x20030000
            or entry != 1 or length != len(image)-28 or not 2 <= length <= 16384
            or zlib.crc32(image[28:]) != crc):
        raise ValueError("Invalid application image header or CRC")
    return app


def validate_capture(r):
    fast = bool(r["flags"] & 16)
    state = r["app"] in (4, 5, 7) and not fast
    if (r["magic"] != 0x43415032 or r["version"] != 1 or r["committed"] != 0
            or r["bank"] not in (0, 1) or r["app"] not in (2, 4, 5, 7)
            or (r["app"] in (4, 5, 7) and r["bank"] != 0) or not 1 <= r["capacity"] <= 65536
            or (fast and (r["app"] != 4 or r["capacity"] > 4096 or r["hz"] != 150000000))
            or not 0 <= r["count"] <= r["capacity"] or r["stride"] != (12 if state else 4)
            or r["bytes"] != r["count"] * r["stride"] or not r["hz"]
            or r["pre_percent"] not in POSITIONS.values() or r["flags"] & ~31
            or r["edge_config"] & ~3
            or bool(r["flags"] & 1) != (r["trigger"] != 0xffffffff)
            or (r["trigger"] != 0xffffffff and r["trigger"] >= r["count"])):
        raise ValueError("Invalid capture metadata")


def capture_vcd(r, raw):
    """Validate raw records and render their actual timestamps and trigger."""
    validate_capture(r)
    if len(raw) != r["bytes"] or zlib.crc32(raw) != r["crc"]:
        raise ValueError("Capture raw length/CRC mismatch")
    state = r["app"] in (4, 5, 7) and not r["flags"] & 16
    signals = ([("a", 20, "A", 0), ("d", 8, "D", 20), ("as", 1, "AS_N", 28),
                ("ds", 1, "DS_N", 29), ("rw", 1, "RW", 30), ("ack", 1, "DTACK_N", 31)]
               if r["app"] in (4, 5, 7) else [(f"g{i}", 1, f"GPIO{i}", i-(32 if r["bank"] else 0))
                              for i in range(32 if r["bank"] else 0, 45 if r["bank"] else 32)])
    lines = ["$version 68008ice dispatcher 0.7 $end", "$timescale 1ps $end",
             f'$comment {r["count"]} samples; trigger index {r["trigger"]}; flags {r["flags"]}; '
             f'nominal clock, sample-relative times; selected {"AS" if r["edge_config"] & 1 else "DS"} '
             f'{"release" if r["edge_config"] & 2 else "assert"} edge; '
             f'{"state records show selected edges only" if state else "uniform timing samples"} $end',
             "$scope module bus $end"]
    lines += [f"$var wire {width} {ident} {name} $end" for ident, width, name, bit in signals]
    lines += ["$var wire 1 t TRIGGER $end", "$upscope $end", "$enddefinitions $end"]
    first_ticks = previous_ticks = None
    previous_value = None
    for index in range(r["count"]):
        if state:
            value, lo, hi = struct.unpack_from("<3I", raw, index*12)
            ticks = lo | hi << 32
        else:
            value, = struct.unpack_from("<I", raw, index*4)
            ticks = index
        if previous_ticks is not None and ticks <= previous_ticks:
            raise ValueError("State timestamps must increase strictly")
        if first_ticks is None:
            first_ticks = ticks
        lines.append(f'#{(ticks-first_ticks)*1000000000000//r["hz"]}')
        if index == 0:
            lines.append(f'{int(r["trigger"] == 0)}t')
        elif index == r["trigger"]:
            lines.append("1t")
        for ident, width, name, bit in signals:
            mask = (1 << width)-1
            v = (value >> bit) & mask
            if previous_value is None or v != (previous_value >> bit) & mask:
                lines.append(f"{v}{ident}" if width == 1 else f"b{v:0{width}b} {ident}")
        previous_value, previous_ticks = value, ticks
    if not r["count"]:
        lines += ["#0", "0t"]
    return ("\n".join(lines)+"\n").encode("ascii")


def capture_config(args):
    return (args.samples, POSITIONS[args.position], 150000000 if getattr(args, "timing150", False) else getattr(args, "sample_hz", 1000000),
            int(getattr(args, "strobe", "ds") == "as"), int(getattr(args, "edge", "assert") == "release"),
            getattr(args, "address", 0), getattr(args, "mask", 0), getattr(args, "base", 0),
            getattr(args, "cycles", 2048), getattr(args, "idle_ms", 100),
            getattr(args, "cycle_timeout_us", 10000),
            getattr(args, "seed", 0 if getattr(args,"command",None)=="abc1600-memory" else 0x5a))


def save_capture(device, bank, path):
    record, raw, vcd = device.fetch_capture(bank)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(vcd)
    path.with_suffix(".bin").write_bytes(raw)
    path.with_suffix(".json").write_text(json.dumps(record, indent=2)+"\n")
    return record


def fixture(args):
    from pio_trace import check_vcd
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    banks = (0, 1) if args.bank == "both" else (int(args.bank),)
    if args.trigger_gpio is not None and any(not ((32 <= args.trigger_gpio <= 44) if bank else (0 <= args.trigger_gpio <= 31)) for bank in banks):
        raise ValueError("Fixture trigger must be among the GPIOs generated in each selected bank")
    results = []
    with Device(args.generator) as source, Device(args.receiver) as receiver:
        if source.info["serial"] == receiver.info["serial"]:
            raise ValueError("Generator and receiver must be different devices")
        for bank in banks:
            gpio = args.trigger_gpio if args.trigger_gpio is not None else (32 if bank else 0)
            source.load("generator", args.source)
            receiver.load("analyzer", args.source)
            try:
                source.run(bank, gpio, args.level, 15000, 1 | (2 if args.level == 0 else 0))
                receiver.run(bank, gpio, args.level, args.timeout_ms)
                source.request(5)
                source.wait()
                status = receiver.wait()
                data = receiver.fetch(bank)
                raw = receiver.read_data(1, bank, 4096)
                mailbox = [0] * 16
                mailbox[8:15] = [status["hz"], 1024, status["fdebug"], status["remaining"],
                                 status["vcd_bytes"], status["vcd_crc"], status["raw_crc"]]
                result = check_vcd(data, raw, bank, mailbox)
                result.update(trigger_gpio=gpio, trigger_level=args.level, source=args.source,
                              generator=source.info["serial"], receiver=receiver.info["serial"])
                name = "HIGH13.VCD" if bank else "LOW32.VCD"
                (output/name).write_bytes(data)
                (output/f"bank{bank}.bin").write_bytes(raw)
                results.append(result)
                print(json.dumps(result, indent=2), flush=True)
            finally:
                try:
                    source.request(7)
                finally:
                    receiver.request(7)
    (output/"report.json").write_text(json.dumps(results, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Target USB CDC port (not the probe UART)")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("info", "list", "status", "go", "bootsel", "ports", "timing-debug", "cpu-status", "boot-status", "cpu-registers", "cpu-trace", "memory-info", "abc1600-status"):
        sub.add_parser(command)
    stop = sub.add_parser("stop")
    stop.add_argument("--discard", action="store_true", help="Abort instead of retaining partial capture")
    load = sub.add_parser("load")
    load.add_argument("app", choices=APPS)
    load.add_argument("--source", choices=SOURCES, default="flash")
    upload = sub.add_parser("upload")
    upload.add_argument("image", type=Path)
    for command in ("capture", "generate"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--bank", type=int, choices=(0, 1), default=0)
        cmd.add_argument("--trigger-gpio", type=int, choices=range(45), default=0)
        cmd.add_argument("--level", type=int, choices=(0, 1), default=1)
        cmd.add_argument("--timeout-ms", type=int, default=5000)
        cmd.add_argument("--source", choices=SOURCES, default="flash")
        if command == "generate":
            cmd.add_argument("--allow-drive", action="store_true", required=True)
            cmd.add_argument("--initial-high", action="store_true")
            cmd.add_argument("--prepare", action="store_true", help="Wait for a separate go command")
        else:
            cmd.add_argument("--wait", action="store_true")
            cmd.add_argument("--samples", type=int, choices=range(1, 65537), metavar="1..65536", default=1024)
            cmd.add_argument("--position", choices=POSITIONS, default="middle")
            cmd.add_argument("--sample-hz", type=int, default=1000000)
            cmd.add_argument("--burst150", action="store_true", help="Original finite 1024-sample 150 MS/s capture")
    cpu = sub.add_parser("emulate", help="Run the 68008 instruction interpreter on the bench PIO bus")
    cpu.add_argument("--allow-drive", action="store_true", required=True)
    cpu.add_argument("--allow-writes", action="store_true", help="Permit emulated CPU memory writes")
    cpu.add_argument("--source", choices=SOURCES, default="flash")
    cpu.add_argument("--timeout-ms", type=int, default=10000)
    cpu.add_argument("--cycle-timeout-us", type=int, default=10000)
    cpu.add_argument("--instructions", type=int, choices=range(1, 2000001), metavar="1..2000000", default=1024)
    cpu.add_argument("--prepare", action="store_true")
    for command in ("bus-generate", "memory", "state-capture", "abc1600-memory"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--source", choices=SOURCES, default="flash")
        cmd.add_argument("--timeout-ms", type=int, default=30000)
        cmd.add_argument("--samples", type=int, choices=range(1, 65537), metavar="1..65536", default=None if command == "memory" else 4096 if command == "abc1600-memory" else 1024)
        cmd.add_argument("--position", choices=POSITIONS, default="middle")
        cmd.add_argument("--base", type=lambda n: int(n, 0), default=0, help="Aligned base address of 1 KiB memory")
        cmd.add_argument("--cycle-timeout-us", type=int, default=10000)
        if command != "state-capture":
            cmd.add_argument("--allow-drive", action="store_true", required=True)
        if command == "bus-generate":
            cmd.add_argument("--cycles", type=int, default=2048)
            cmd.add_argument("--seed", type=lambda n: int(n, 0), default=0x5a)
            cmd.add_argument("--allow-writes", action="store_true", help="Write/read/verify 1 KiB sweeps")
            cmd.add_argument("--prepare", action="store_true")
        else:
            if command == "memory":
                cmd.add_argument("--boot", choices=("stop", "nop-stop", "reset-fault", "image"), help="Load vectors/test program and pulse RESET/HALT; GPIO35/38/40 sidebands")
                cmd.add_argument("--timing150", action="store_true", help="Memory plus 150 MS/s timing capture, up to 4096 samples; USB pauses during acquisition")
            cmd.add_argument("--address", type=lambda n: int(n, 0), default=0)
            cmd.add_argument("--mask", type=lambda n: int(n, 0), default=0, help="Address comparator mask; 0 matches any address")
            cmd.add_argument("--strobe", choices=("as", "ds"), default="ds")
            cmd.add_argument("--edge", choices=("assert", "release"), default="assert")
            cmd.add_argument("--idle-ms", type=int, default=100, help="0 disables idle completion")
            cmd.add_argument("--wait", action="store_true")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--bank", type=int, choices=(0, 1), default=0)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--capture", action="store_true", help="Fetch new continuous/state capture and convert to VCD")
    mem = sub.add_parser("memory-dump")
    mem.add_argument("--output", type=Path, required=True)
    mem.add_argument("--image", action="store_true", help="Read the uploaded-ROM 1 MiB target map")
    mem.add_argument("--address", type=lambda n: int(n, 0), default=0)
    mem.add_argument("--bytes", type=int, default=1024)
    memload = sub.add_parser("memory-load", help="Upload and read back a ROM into the 1 MiB target map")
    memload.add_argument("image", type=Path)
    memload.add_argument("--machine", choices=("generic", "abc1600"), default="generic")
    poke = sub.add_parser("memory-poke", help="Set a non-ROM byte in the uploaded image's RAM")
    poke.add_argument("address", type=lambda n: int(n, 0))
    poke.add_argument("value", type=lambda n: int(n, 0))
    test = sub.add_parser("fixture")
    test.add_argument("--generator", required=True)
    test.add_argument("--receiver", required=True)
    test.add_argument("--bank", choices=("0", "1", "both"), default="both")
    test.add_argument("--trigger-gpio", type=int, choices=range(45))
    test.add_argument("--level", type=int, choices=(0, 1), default=1)
    test.add_argument("--source", choices=SOURCES, default="flash")
    test.add_argument("--timeout-ms", type=int, default=5000)
    test.add_argument("--output", default="build/dispatcher-capture")
    args = parser.parse_args()
    if args.command == "memory" and args.samples is None:
        args.samples = 4096 if args.timing150 else 1024
    if args.command == "memory" and args.timing150 and (args.samples > 4096 or args.address or args.mask):
        parser.error("--timing150 needs 1..4096 samples and zero address/mask")
    if args.command == "memory" and args.boot and (args.timing150 or args.base):
        parser.error("--boot requires base zero and state capture")
    if args.command == "memory-dump" and not (args.address >= 0 and args.bytes >= 1 and
            args.address + args.bytes <= (1048576 if args.image else 1024)):
        parser.error("memory dump exceeds the selected memory map")
    if args.command == "ports":
        print("\n".join(sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*"))))
        return
    if args.command == "fixture":
        fixture(args)
        return
    if not args.port:
        parser.error("--port is required for this command")
    with Device(args.port) as device:
        result = None
        if args.command == "info": result = device.info
        elif args.command == "list":
            raw = device.request(2)
            result = [dict(zip("magic abi app address entry bytes crc".split(), struct.unpack_from("<7I", raw, i))) for i in range(0, len(raw), 28)]
        elif args.command == "status": result = device.status()
        elif args.command == "cpu-status": result = device.cpu_status()
        elif args.command == "cpu-registers": result = device.cpu_registers()
        elif args.command == "cpu-trace": result = device.cpu_trace()
        elif args.command == "memory-info": result = device.memory_info()
        elif args.command == "abc1600-status": result = device.abc1600_status()
        elif args.command == "memory-load":
            device.load("abc1600-memory" if args.machine == "abc1600" else "generic-memory", "flash")
            result = device.memory_load(args.image.read_bytes())
        elif args.command == "memory-poke":
            device.request(27, struct.pack("<2I", args.address, args.value))
        elif args.command == "boot-status": result = device.boot_status()
        elif args.command == "emulate":
            device.load("cpu-emulator", args.source)
            config = (1, 10, 1000000, 0, 0, 0, 0, 0, args.instructions, 0, args.cycle_timeout_us, 0)
            result = device.run(0, 0, 0, args.timeout_ms, 1 | (4 if args.allow_writes else 0), config)
            if not args.prepare:
                device.request(5); result = device.wait(timeout=args.timeout_ms/1000+5)
        elif args.command == "timing-debug":
            fields="phase completed_cycles last_pins trigger_search_index end_index fdebug timer_pc ack_pc pio_ctrl stop_remaining stop_ctrl timer_seed".split()
            result = dict(zip(fields, struct.unpack("<12I", device.request(18))))
        elif args.command == "load": device.load(args.app, args.source)
        elif args.command == "upload": result = {"uploaded_app": device.upload(args.image.read_bytes())}
        elif args.command == "go": device.request(5); result = device.wait()
        elif args.command == "stop": result = device.stop(args.discard)
        elif args.command == "bootsel": device.request(11)
        elif args.command == "fetch":
            if args.capture:
                result = save_capture(device, args.bank, args.output)
            else:
                args.output.write_bytes(device.fetch(args.bank)); result = {"saved": str(args.output)}
        elif args.command == "memory-dump":
            args.output.write_bytes(device.read_data(4 if args.image else 3, 0, args.bytes, args.address)); result = {"saved": str(args.output)}
        elif args.command in ("bus-generate", "memory", "state-capture", "abc1600-memory"):
            app = {"bus-generate": "bus-generator", "memory": "bus-memory", "state-capture": "state-analyzer", "abc1600-memory": "abc1600-memory"}[args.command]
            device.load(app, args.source)
            flags = (1 | (4 if args.allow_writes else 0)) if args.command == "bus-generate" else int(args.command in ("memory", "abc1600-memory"))
            config = capture_config(args)
            if args.command == "memory" and args.boot:
                flags |= 8
                config = (*config[:-1], ("stop", "nop-stop", "reset-fault", "image").index(args.boot))
            result = device.run(0, 0, 0, args.timeout_ms, flags, config)
            if args.command == "bus-generate" and not args.prepare:
                device.request(5); result = device.wait(timeout=args.timeout_ms/1000+30)
            elif args.command != "bus-generate" and args.wait:
                result = device.wait(timeout=args.timeout_ms/1000+30)
        elif args.command in ("capture", "generate"):
            app = "generator" if args.command == "generate" else "analyzer"
            device.load(app, args.source)
            flags = (1 | (2 if args.initial_high else 0)) if app == "generator" else 0
            config = capture_config(args) if app == "analyzer" and not args.burst150 else None
            result = device.run(args.bank, args.trigger_gpio, args.level, args.timeout_ms, flags, config)
            if app == "generator" and not args.prepare:
                device.request(5); result = device.wait()
            elif app == "analyzer" and args.wait:
                result = device.wait()
        if result is not None: print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
