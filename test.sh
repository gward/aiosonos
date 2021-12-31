#!/bin/sh

set -e
pyflakes aiosonos examples
mypy aiosonos examples
pytest -q tests
pycodestyle aiosonos examples
