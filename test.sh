#!/bin/sh

set -e
pyflakes aiosonos
mypy aiosonos
pycodestyle aiosonos
