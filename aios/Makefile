# luminOS / aios — top-level build
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
export AIOS_HEADLESS ?= 1
export AIOS_RUNTIME_DIR ?= /tmp/aios-runtime
export AIOS_STATE_DIR ?= /tmp/aios-state
export AIOS_RCP_LOOPBACK ?= 1
export AIOS_OFFLINE ?= 1
export PATH := $(CURDIR)/.venv/bin:$(PATH)

.PHONY: venv install test unit integration smoke run stop daily-build deb img-skeleton iso apt-repo clean lint

venv:
	python3 -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

install: venv

unit:
	$(PYTHON) -m pytest tests/unit -q --tb=short

integration: stop
	$(PYTHON) -m pytest tests/integration -q --tb=short

test: unit integration

smoke: stop
	bash scripts/smoke.sh

run:
	bash scripts/run-stack.sh

stop:
	bash scripts/stop-stack.sh || true

daily-build:
	bash scripts/daily-build.sh

deb:
	bash packaging/build-deb.sh

img-skeleton:
	bash scripts/mkimg/build-skeleton.sh

apt-repo:
	bash scripts/make-apt-repo.sh

# Requires root + live-build on the builder machine
iso:
	sudo bash scripts/build-iso.sh

clean: stop
	rm -rf build dist *.egg-info /tmp/aios-runtime /tmp/aios-state /tmp/aios-daily
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true

lint:
	$(PYTHON) -m compileall -q libs services cli sdk/python apps 2>/dev/null || $(PYTHON) -m compileall -q libs services cli sdk/python
