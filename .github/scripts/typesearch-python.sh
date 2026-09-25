#!/usr/bin/env bash
# El SDK de Python (typesearch) para el CI, mientras pyproject.toml lo toma por ruta ([tool.uv.sources] →
# ../typesearch-python, como en el repo de trabajo, hasta que esté en PyPI):
#   - si typesearch ya está en PyPI (el nuestro), el job pasa a esa versión: borra [tool.uv.sources] y
#     rehace uv.lock (el paquete construido ya pide "typesearch>=0.1.0,<1");
#   - si no, clona al lado el repo público hermano (typesearch-ai/typesearch-python).
# Sin [tool.uv.sources], o con la carpeta ya en su lugar (el repo de trabajo), no hace nada.
# Este archivo es el mismo en cada repo que usa el SDK de Python.
set -euo pipefail

sdk_repo='https://github.com/typesearch-ai/typesearch-python'

grep -q '^\[tool\.uv\.sources\]' pyproject.toml || exit 0
dir="$(dirname "$PWD")/typesearch-python"
if [ -f "$dir/pyproject.toml" ]; then
  echo "typesearch: $dir"
  exit 0
fi

published=$(curl -fsSL https://pypi.org/pypi/typesearch/json 2>/dev/null || true)
if [[ "$published" == *github.com/typesearch-ai/typesearch-python* ]]; then
  echo "typesearch: from PyPI"
  awk '/^\[/ { skip = ($0 == "[tool.uv.sources]") } !skip' pyproject.toml > pyproject.toml.new
  mv pyproject.toml.new pyproject.toml
  uv lock
else
  echo "typesearch: not on PyPI yet, using $sdk_repo in $dir"
  git clone --quiet --depth 1 "$sdk_repo.git" "$dir"
fi
