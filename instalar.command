#!/bin/bash
# Dois cliques no Finder para instalar (macOS). Se pedir permissão, autorize.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 instalar.py
else
  echo "Python 3 não encontrado. Instale o Python 3 e rode de novo."
fi
echo ""
read -r -p "Pressione Enter para fechar..."
