#!/usr/bin/env python3
"""Docker Pico SDK build and SWD development for the standalone Core2350B."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import glob
import hashlib
import os
from pathlib import Path
import platform
import select
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
IMAGE = os.environ.get("PICO_IMAGE", "68008ice-pico:2.3.1")
DOCKER = os.environ.get("DOCKER", "docker")
DEBUG = ROOT / "build/debug"
ELF = "/work/build/firmware/blink.elf"
MAC = platform.system() == "Darwin"
LINUX = platform.system() == "Linux"


def run(args, *, log=None):
    print("+ " + shlex.join(map(str, args)), flush=True)
    if log is None:
        subprocess.run(args, cwd=ROOT, check=True)
        return
    DEBUG.mkdir(parents=True, exist_ok=True)
    with open(log, "w") as out:
        with subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True) as proc:
            for line in proc.stdout:
                print(line, end="", flush=True)
                out.write(line)
            if proc.wait():
                raise subprocess.CalledProcessError(proc.returncode, args)


def container(args, *, interactive=False, debug=False):
    cmd = [DOCKER, "run", "--rm", "--init"]
    if interactive:
        cmd.append("-it")
    if debug and LINUX:
        cmd += ["--network", "host"]
    # Keep files editable for Linux users as well as Docker Desktop users.
    if LINUX:
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    cmd += ["--mount", f"type=bind,source={ROOT},target=/work", IMAGE]
    return cmd + list(args)


def host_tools():
    if not MAC:
        return
    dest = ROOT / "build/tools"
    binary = dest / "openocd"
    if binary.exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    url = ("https://github.com/raspberrypi/pico-sdk-tools/releases/download/"
           "v2.3.1-0/openocd-0.12.0%2Bdev-mac.zip")
    archive = ROOT / "build/tool-downloads/openocd-mac.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print("Downloading Raspberry Pi OpenOCD v2.3.1-0 for macOS", flush=True)
        urllib.request.urlretrieve(url, archive)
    expected = "412caeab08a4613d3fd425fc1fa3fa84aa95ff05bca008f13eacee118e05035d"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"OpenOCD checksum mismatch: {archive}")
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(dest)
    binary.chmod(0o755)


def ocd_args(*, oneshot=False):
    if MAC:
        binary = Path(os.environ.get("OPENOCD", ROOT / "build/tools/openocd"))
        if not binary.is_file():
            raise RuntimeError("Host OpenOCD missing; run make setup first")
        args = [str(binary), "-s", str(binary.parent / "scripts"),
                "-f", str(ROOT / "tools/debug/openocd.cfg")]
    elif LINUX:
        args = [DOCKER, "run", "--rm", "--init", "--network", "host",
                "--mount", "type=bind,source=/dev/bus/usb,target=/dev/bus/usb",
                "--device-cgroup-rule", "c 189:* rmw",
                "--mount", f"type=bind,source={ROOT},target=/work",
                "-e", f"DEBUG_PROBE_SERIAL={os.environ.get('DEBUG_PROBE_SERIAL', '')}",
                IMAGE, "openocd", "-f", "/work/tools/debug/openocd.cfg"]
    else:
        raise RuntimeError("Use macOS or Linux; Windows can use WSL2 with USB forwarding")
    if oneshot:
        args += ["-c", "gdb port disabled", "-c", "init", "-c", "targets", "-c", "shutdown"]
    return args


@contextmanager
def debug_server():
    if os.environ.get("OPENOCD_EXTERNAL") == "1":
        yield
        return
    DEBUG.mkdir(parents=True, exist_ok=True)
    log = DEBUG / "openocd.log"
    args = ocd_args()
    print("+ " + shlex.join(args) + f" (log: {log.relative_to(ROOT)})", flush=True)
    with open(log, "w") as stream:
        proc = subprocess.Popen(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(log.read_text())
                if "Listening on port 3333 for gdb connections" in log.read_text():
                    yield
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("OpenOCD startup timed out:\n" + log.read_text())
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def gdb(command):
    if not (ROOT / "build/firmware/blink.elf").exists():
        raise RuntimeError("Firmware missing; run make blink first")
    host = "host.docker.internal" if MAC else "127.0.0.1"
    endpoint = os.environ.get("GDB_ENDPOINT", f"{host}:3333")
    args = ["gdb-multiarch", "-q", "-nx", ELF,
            "-ex", "set pagination off", "-ex", "set remotetimeout 15",
            "-ex", f"target extended-remote {endpoint}"]
    if command == "debug":
        args += ["-ex", "monitor reset halt", "-ex", "tbreak main", "-ex", "continue",
                 "-ex", "info registers pc sp",
                 "-ex", "display blink_count", "-ex", "display led_state"]
    else:
        script = "flash.gdb" if command == "flash" else "check.gdb"
        args += ["-batch", "-x", f"/work/tools/debug/{script}"]
    with debug_server():
        run(container(args, interactive=command == "debug", debug=True),
            log=None if command == "debug" else DEBUG / f"{command}.log")


def usb_monitor(port, seconds):
    # USB stdio belongs to the target, not the probe's unconnected UART bridge.
    import termios
    if port is None:
        candidates = sorted(glob.glob("/dev/cu.usbmodem*") if MAC
                            else glob.glob("/dev/ttyACM*"))
        raise RuntimeError("Choose the target CDC port: make monitor PORT=/dev/...\n"
                           + "\n".join(candidates))
    fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    try:
        config = termios.tcgetattr(fd)
        config[0] = 0
        config[1] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[3] = 0
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = 0
        config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        deadline = time.monotonic() + seconds if seconds else float("inf")
        print(f"Monitoring target USB stdio on {port}; Ctrl-C to exit", flush=True)
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.2)[0]:
                data = os.read(fd, 4096)
                if data:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "build", "probe", "flash", "check",
                                            "debug", "server", "shell", "versions", "uf2", "monitor"])
    parser.add_argument("--port", default=os.environ.get("PORT"))
    parser.add_argument("--seconds", type=float, default=0)
    args = parser.parse_args()
    if args.command == "setup":
        run([DOCKER, "build", "-t", IMAGE, "-f", "docker/Dockerfile", "."])
        host_tools()
    elif args.command == "build":
        run(container(["cmake", "-S", "firmware", "-B", "build/firmware", "-G", "Ninja",
                       "-DCMAKE_BUILD_TYPE=Debug", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]))
        run(container(["cmake", "--build", "build/firmware", "--parallel", "4"]))
    elif args.command == "probe":
        run(ocd_args(oneshot=True), log=DEBUG / "probe.log")
    elif args.command in ("flash", "check", "debug"):
        gdb(args.command)
    elif args.command == "server":
        run(ocd_args())
    elif args.command == "shell":
        run(container(["bash"], interactive=True))
    elif args.command == "versions":
        for command in (["arm-none-eabi-gcc", "--version"], ["cmake", "--version"],
                        ["gdb-multiarch", "--version"], ["picotool", "version"], ["openocd", "--version"]):
            run(container(command))
    elif args.command == "monitor":
        usb_monitor(args.port, args.seconds)
    elif args.command == "uf2":
        volume = Path(os.environ.get("BOOT_VOLUME", "/Volumes/RP2350"))
        if not (volume / "INFO_UF2.TXT").is_file():
            raise RuntimeError(f"No ROM boot volume at {volume}; hold BOOT then reset, or set BOOT_VOLUME")
        info = (volume / "INFO_UF2.TXT").read_text()
        if "RP2350" not in info:
            raise RuntimeError("Refusing to copy to a volume without RP2350 identification")
        shutil.copyfile(ROOT / "build/firmware/blink.uf2", volume / "blink.uf2")
        print("Copied blink.uf2; the board should reboot automatically")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
