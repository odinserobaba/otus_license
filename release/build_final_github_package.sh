#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/release/final_project_full"

echo "[1/3] Prepare output directory"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

echo "[2/3] Copy project files"
rsync -a \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".pytest_cache/" \
  --exclude ".mypy_cache/" \
  --exclude ".ruff_cache/" \
  --exclude ".DS_Store" \
  --exclude "processed/answer_cache.sqlite" \
  --exclude "processed/embedding_cache.json" \
  --exclude "processed/*tmp*" \
  --exclude "release/final_project_full/" \
  "$ROOT_DIR/" "$OUT_DIR/"

echo "[3/3] Write package marker"
cat > "$OUT_DIR/FINAL_PACKAGE_NOTE.md" << 'EOF'
# Final GitHub Package

Эта папка содержит финальную копию проекта для публикации на GitHub.

Сборка выполнена скриптом:
- `release/build_final_github_package.sh`

Содержимое включает:
- исходный код,
- скрипты сборки/eval/deploy,
- документацию,
- тесты,
- текущие артефакты проекта (кроме локальных кэшей и виртуального окружения).
EOF

echo "Done: $OUT_DIR"
