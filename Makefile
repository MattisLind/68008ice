PYTHON ?= python3

.PHONY: help setup blink probe program debug debug-check debug-server monitor uf2 shell versions
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
