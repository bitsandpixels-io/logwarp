# ---------------------------------------------------------------------------
# logwarp — release management
#
# VERSION STRATEGY
#   The single source of truth for the version is the **git tag**.
#   Tags must follow the format:  v<MAJOR>.<MINOR>.<PATCH>
#   hatch-vcs reads the latest tag at build/install time and writes
#   src/logwarp/_version.py automatically — never edit that file by hand.
#
# TYPICAL WORKFLOW
#   1.  make release-patch   → bumps patch  (0.1.0 → 0.1.1)
#   2.  make release-minor   → bumps minor  (0.1.0 → 0.2.0)
#   3.  make release-major   → bumps major  (0.1.0 → 1.0.0)
#   4.  make build           → produces dist/ wheel + sdist
#   5.  make publish         → uploads to PyPI (requires TWINE_* env vars)
# ---------------------------------------------------------------------------

PYTHON  ?= .venv/bin/python
PIP     ?= .venv/bin/pip
BUILD   ?= .venv/bin/python -m build
TWINE   ?= .venv/bin/twine

.PHONY: help version release-patch release-minor release-major build publish install dev-install

help:
	@echo ""
	@echo "  make version         — show current version"
	@echo "  make release-patch   — tag & push a patch release (x.y.Z+1)"
	@echo "  make release-minor   — tag & push a minor release (x.Y+1.0)"
	@echo "  make release-major   — tag & push a major release (X+1.0.0)"
	@echo "  make build           — build wheel + sdist into dist/"
	@echo "  make publish         — upload dist/ to PyPI via twine"
	@echo "  make dev-install     — pip install -e .[dev] in .venv"
	@echo ""

# Show current version as reported by hatch-vcs / setuptools-scm
version:
	@$(PYTHON) -c "from logwarp import __version__; print(__version__)"

# ---------------------------------------------------------------------------
# Helpers — compute the next semver tag from the latest git tag
# ---------------------------------------------------------------------------
_LATEST_TAG := $(shell git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
_VERSION    := $(patsubst v%,%,$(_LATEST_TAG))
_MAJOR      := $(word 1,$(subst ., ,$(_VERSION)))
_MINOR      := $(word 2,$(subst ., ,$(_VERSION)))
_PATCH      := $(word 3,$(subst ., ,$(_VERSION)))

release-patch: _NEXT = v$(_MAJOR).$(_MINOR).$(shell echo $$(( $(_PATCH) + 1 )))
release-minor: _NEXT = v$(_MAJOR).$(shell echo $$(( $(_MINOR) + 1 ))).0
release-major: _NEXT = v$(shell echo $$(( $(_MAJOR) + 1 ))).0.0

release-patch release-minor release-major: _guard-clean
	@echo "Tagging $(_NEXT) …"
	git tag -a "$(_NEXT)" -m "Release $(_NEXT)"
	git push origin "$(_NEXT)"
	@echo "✓  Tagged and pushed $(_NEXT)"

# Abort if the working tree is dirty
_guard-clean:
	@git diff --quiet && git diff --cached --quiet || \
		(echo "ERROR: working tree is dirty — commit or stash changes first." && exit 1)

# ---------------------------------------------------------------------------
# Build & publish
# ---------------------------------------------------------------------------
build:
	rm -rf dist/
	$(BUILD)

publish: build
	$(TWINE) upload dist/*

# ---------------------------------------------------------------------------
# Dev environment
# ---------------------------------------------------------------------------
dev-install:
	$(PIP) install -e ".[dev]"
