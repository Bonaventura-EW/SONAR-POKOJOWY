#!/bin/bash
# SessionStart hook (Claude Code on the web).
# Instaluje zależności Pythona z requirements.txt, żeby testy i parser działały
# od razu w świeżym kontenerze. Bez geopy/pytz `from geocoder import to_nominative`
# pada po cichu, krok "mianownik" w address_parser przestaje działać i
# test_address_parser_golden.py pokazuje FAŁSZYWE regresje. Deleguje do
# .claude/setup.sh (jedyne źródło prawdy o krokach setupu).
set -euo pipefail

# Tylko środowisko zdalne — lokalnie nie ruszamy systemowego Pythona użytkownika.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

bash "${CLAUDE_PROJECT_DIR:-.}/.claude/setup.sh"
