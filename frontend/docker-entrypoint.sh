#!/bin/sh
set -eu

cd /app

echo "Installing / syncing npm dependencies..."
npm install --no-audit --no-fund

if ! test -f node_modules/react-router-dom/package.json; then
  echo "ERROR: react-router-dom did not appear under /app/node_modules after npm install." >&2
  echo 'If you use Docker, remove the stale volume: docker compose down && docker volume rm tfk_mentors_frontend_nm' >&2
  ls -la node_modules 2>/dev/null | head -n 25 || echo "(node_modules missing or empty)" >&2
  exit 1
fi

exec "$@"
