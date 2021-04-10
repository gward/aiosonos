#!/bin/sh

set -e
pyflakes aiosonos examples
mypy aiosonos examples
pycodestyle aiosonos examples
