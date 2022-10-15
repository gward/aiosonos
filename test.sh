#!/bin/sh

set -e
pyflakes aiosonos examples
mypy aiosonos examples tests
pytest -q tests
pycodestyle aiosonos examples
