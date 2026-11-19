#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHONPATH="$ROOT/runtime/python:$ROOT/tests" python3 "$ROOT/runtime/python/iilp.py" --self-test
PYTHONPATH="$ROOT/runtime/python:$ROOT/tests" python3 -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
if command -v node >/dev/null 2>&1; then
  node --test "$ROOT/runtime/javascript/iilp.test.mjs"
else
  echo "SKIP: Node.js not installed; JavaScript interoperability tests not run."
fi
