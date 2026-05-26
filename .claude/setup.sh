#!/bin/bash
# Setup script dla Claude Code on the web
# Uruchamiany automatycznie przy starcie sesji w środowisku VM

set -e

echo "🔧 SONAR-POKOJOWY — setup środowiska..."

# Python dependencies
echo "📦 Instaluję zależności Pythona..."
pip install -r requirements.txt --break-system-packages 2>&1 | tail -5 || \
  pip install -r requirements.txt 2>&1 | tail -5

# Konfiguracja git (na wypadek gdyby commitował Claude)
git config --global user.email "claude-code@anthropic.com" 2>/dev/null || true
git config --global user.name "Claude Code" 2>/dev/null || true

# Sanity check - czy importy działają
echo "🧪 Weryfikacja importów..."
python3 -c "
import requests, bs4, lxml, Levenshtein, pytz, geopy
print('✓ Wszystkie zależności OK')
" || echo "⚠️  Niektóre importy się nie powiodły — sprawdź requirements.txt"

# Pokaż gdzie jesteśmy
echo ""
echo "✅ Setup zakończony. Repo gotowe do pracy."
echo "   Struktura: src/ (backend), data/ (źródło prawdy), docs/ (GitHub Pages)"
echo "   Workflow ID: 238181145"
echo ""
