PYTHON ?= python3

.PHONY: help setup blink probe program debug debug-check debug-server monitor uf2 shell versions multidrop-build multidrop-probe multidrop-server multidrop-debug multidrop-check gpio-link-build gpio-link-check gpio-connectivity-build gpio-connectivity-check
help:
	@$(PYTHON) tools/pico.py --help

setup:
	$(PYTHON) tools/pico.py setup

blink:
	$(PYTHON) tools/pico.py build

probe:
	$(PYTHON) tools/pico.py probe

program: blink
	$(PYTHON) tools/pico.py flash

debug: program
	$(PYTHON) tools/pico.py debug

debug-check: program
	$(PYTHON) tools/pico.py check

debug-server:
	$(PYTHON) tools/pico.py server

monitor:
	$(PYTHON) tools/pico.py monitor

uf2: blink
	$(PYTHON) tools/pico.py uf2

shell:
	$(PYTHON) tools/pico.py shell

versions:
	$(PYTHON) tools/pico.py versions

multidrop-build:
	$(PYTHON) tools/pico.py multidrop-build

multidrop-probe:
	$(PYTHON) tools/pico.py multidrop-probe

multidrop-server:
	$(PYTHON) tools/pico.py multidrop-server

multidrop-debug:
	$(PYTHON) tools/pico.py multidrop-debug --instance $(or $(INSTANCE),1) --firmware $(or $(FIRMWARE),blink)

multidrop-check:
	$(PYTHON) tools/pico.py multidrop-check

gpio-link-build: multidrop-build

gpio-link-check:
	$(PYTHON) tools/pico.py gpio-link-check

gpio-connectivity-build: multidrop-build

gpio-connectivity-check:
	$(PYTHON) tools/pico.py gpio-connectivity-check

.PHONY: pio-trace-build pio-trace-capture
pio-trace-build: multidrop-build

pio-trace-capture:
	$(PYTHON) tools/pico.py pio-trace-capture

.PHONY: dispatcher-build bus-fixture-check continuous-capture-check
dispatcher-build: multidrop-build

bus-fixture-check:
	$(PYTHON) tools/bus_check.py --generator $(GENERATOR) --receiver $(RECEIVER) --full

continuous-capture-check:
	$(PYTHON) tools/capture_check.py --generator $(GENERATOR) --receiver $(RECEIVER)
