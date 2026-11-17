#!/usr/bin/env python3
"""Docker Pico SDK build and SWD development for the standalone Core2350B."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import errno
import glob
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
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


def ocd_args(*, oneshot=False, multidrop=False):
    config = "multidrop.cfg" if multidrop else "openocd.cfg"
    if MAC:
        binary = Path(os.environ.get("OPENOCD", ROOT / "build/tools/openocd"))
        if not binary.is_file():
            raise RuntimeError("Host OpenOCD missing; run make setup first")
        args = [str(binary), "-s", str(binary.parent / "scripts"),
                "-f", str(ROOT / "tools/debug" / config)]
    elif LINUX:
        args = [DOCKER, "run", "--rm", "--init", "--network", "host",
                "--mount", "type=bind,source=/dev/bus/usb,target=/dev/bus/usb",
                "--device-cgroup-rule", "c 189:* rmw",
                "--mount", f"type=bind,source={ROOT},target=/work",
                "-e", f"DEBUG_PROBE_SERIAL={os.environ.get('DEBUG_PROBE_SERIAL', '')}",
                IMAGE, "openocd", "-f", f"/work/tools/debug/{config}"]
    else:
        raise RuntimeError("Use macOS or Linux; Windows can use WSL2 with USB forwarding")
    if oneshot:
        args += ["-c", "gdb port disabled"]
        if multidrop:
            for instance in (1, 2):
                args += ["-c", f"board{instance}.cm0 configure -gdb-port disabled"]
        args += ["-c", "init", "-c", "targets", "-c", "shutdown"]
    return args


@contextmanager
def debug_server(*, multidrop=False):
    if os.environ.get("OPENOCD_EXTERNAL") == "1":
        yield
        return
    DEBUG.mkdir(parents=True, exist_ok=True)
    log = DEBUG / ("multidrop-openocd.log" if multidrop else "openocd.log")
    args = ocd_args(multidrop=multidrop)
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


def gdb(command, *, instance=None, firmware="blink"):
    elf = ELF if instance is None else f"/work/build/multidrop/{instance}/{firmware}.elf"
    if not (ROOT / elf.removeprefix("/work/")).exists():
        raise RuntimeError("Firmware missing; run make blink first")
    host = "host.docker.internal" if MAC else "127.0.0.1"
    endpoint = os.environ.get("GDB_ENDPOINT", f"{host}:{3333 if instance is None else 3332 + instance}")
    args = ["gdb-multiarch", "-q", "-nx", elf,
            "-ex", "set pagination off", "-ex", "set remotetimeout 15",
            "-ex", f"target extended-remote {endpoint}"]
    if command == "debug":
        if instance is None:
            args += ["-ex", "monitor reset halt", "-ex", "tbreak main", "-ex", "continue"]
        else:
            # Attach to the running application; boot ROM uses instance zero.
            args += ["-ex", "monitor halt", "-ex", "print board_id",
                     "-ex", "print/x *(unsigned int *)0x401000ac"]
        args += ["-ex", "info registers pc sp"]
        if firmware == "dispatcher":
            args += ["-ex", "display dispatcher_job"]
        elif firmware == "pio_trace":
            args += ["-ex", "display trace_control"]
        elif firmware == "gpio_connectivity":
            args += ["-ex", "display connectivity"]
        else:
            args += ["-ex", "display blink_count", "-ex", "display led_state"]
    else:
        script = "flash.gdb" if command == "flash" else "check.gdb"
        args += ["-batch", "-x", f"/work/tools/debug/{script}"]
    with debug_server(multidrop=instance is not None):
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


def multidrop_check():
    # Two live GDB clients share one OpenOCD/probe. The GDB scripts coordinate
    # through a fresh artifact directory; no prior test can satisfy a barrier.
    DEBUG.mkdir(parents=True, exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix="multidrop-check-", dir=DEBUG))
    mounted = "/work/" + str(artifacts.relative_to(ROOT))
    host = "host.docker.internal" if MAC else "127.0.0.1"

    def check(instance):
        elf = f"/work/build/multidrop/{instance}/blink.elf"
        args = container(["env", f"ICE_MULTIDROP_INSTANCE={instance}",
                          f"ICE_MULTIDROP_TEST_DIR={mounted}", "gdb-multiarch", "-q", "-nx",
                          "-batch", elf, "-ex", f"target extended-remote {host}:{3332 + instance}",
                          "-x", "/work/tools/debug/multidrop-check.gdb"], debug=True)
        with (artifacts / f"board{instance}.log").open("w") as log:
            result = subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=50)
        return result.returncode

    with debug_server(multidrop=True), ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(check, instance) for instance in (1, 2)]
        results = [future.result() for future in futures]
    for instance in (1, 2):
        print((artifacts / f"board{instance}.log").read_text(), flush=True)
    if any(results):
        raise RuntimeError(f"Multidrop debug check failed; see {artifacts}")
    identities = [json.loads((artifacts / f"board{instance}.json").read_text())["board_id"]
                  for instance in (1, 2)]
    if len(set(identities)) != 2:
        raise RuntimeError("Both debug connections reached the same physical board")
    print(f"MULTIDROP DEBUG CHECK PASSED: {identities}; logs: {artifacts}")


def usb_boot(port):
    # Pico SDK USB stdio's documented 1200-baud reset, not a power cycle.
    # The caller identifies the target CDC port; never use the probe UART.
    import termios
    if port is None:
        raise RuntimeError("usb-boot requires --port for the target's USB CDC device")
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        config = termios.tcgetattr(fd)
        config[4] = config[5] = termios.B1200
        try:
            termios.tcsetattr(fd, termios.TCSANOW, config)
        except termios.error as exc:
            # macOS can report ENXIO/EIO when the board obeys the request and
            # disconnects before the USB line-coding transaction returns.
            if exc.args[0] not in (errno.ENXIO, errno.EIO):
                raise
    finally:
        os.close(fd)
    print(f"Requested USB BOOTSEL on {port}; wait for the RP2350 ROM disk")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "build", "probe", "flash", "check",
                                            "debug", "server", "shell", "versions", "uf2", "monitor",
                                            "multidrop-build", "multidrop-probe", "multidrop-server",
                                            "multidrop-debug", "multidrop-check", "usb-boot",
                                            "gpio-link-check", "gpio-connectivity-check", "pio-trace-capture"])
    parser.add_argument("--instance", type=int, choices=[1, 2], default=1)
    parser.add_argument("--firmware", choices=["blink", "gpio_link", "gpio_connectivity", "pio_trace", "dispatcher"], default="blink")
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
    elif args.command == "multidrop-build":
        for instance in (1, 2):
            dest = f"build/multidrop/{instance}"
            run(container(["cmake", "-S", "firmware", "-B", dest, "-G", "Ninja",
                           "-DCMAKE_BUILD_TYPE=Debug", f"-DICE_SWD_INSTANCE_ID={instance}"]))
            run(container(["cmake", "--build", dest, "--parallel", "4"]))
    elif args.command == "multidrop-probe":
        run(ocd_args(oneshot=True, multidrop=True), log=DEBUG / "multidrop-probe.log")
    elif args.command == "multidrop-server":
        run(ocd_args(multidrop=True))
    elif args.command == "multidrop-debug":
        gdb("debug", instance=args.instance, firmware=args.firmware)
    elif args.command == "multidrop-check":
        multidrop_check()
    elif args.command == "gpio-link-check":
        commands = ocd_args(multidrop=True)
        for instance in (1, 2):
            commands += ["-c", f"board{instance}.cm0 configure -gdb-port disabled"]
        script = str(ROOT / "tools/debug/gpio-link-check.tcl") if MAC else "/work/tools/debug/gpio-link-check.tcl"
        commands += ["-c", "init", "-f", script, "-c", "shutdown"]
        run(commands, log=DEBUG / "gpio-link-check.log")
    elif args.command == "usb-boot":
        usb_boot(args.port)
    elif args.command == "gpio-connectivity-check":
        from gpio_connectivity import check
        check(root=ROOT, container=container, ocd_args=ocd_args, run=run, mac=MAC)
    elif args.command == "pio-trace-capture":
        from pio_trace import capture
        capture(root=ROOT, container=container, ocd_args=ocd_args, run=run, mac=MAC)
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
