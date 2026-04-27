#!/usr/bin/env bash
# Запуск Ollama с экспериментальным Vulkan для встроенной Intel Graphics (Arc / Arrow Lake и т.п.).
# Требуется: mesa-vulkan-drivers, ICD Intel (/usr/share/vulkan/icd.d/intel_icd.x86_64.json).
#
# Если после запуска в логе всё ещё только CPU и GPULayers пустой:
#   1) Добавить пользователя в группы и перелогиниться:
#        sudo usermod -aG render,video "$USER"
#   2) Выдать ollama capability perfmon (часто нужно для VkPhysicalDeviceMemoryBudget):
#        sudo setcap cap_perfmon+ep "$(command -v ollama)"
#   3) Перезапустить этот скрипт.
#
# Проверка Vulkan (должен быть виден GPU Intel):
#   vulkaninfo --summary
#
set -euo pipefail

OLLAMA_BIN="${OLLAMA_BIN:-$(command -v ollama)}"
if [[ ! -x "$OLLAMA_BIN" ]]; then
  echo "ollama not found; set OLLAMA_BIN=/path/to/ollama" >&2
  exit 1
fi

# Системный loader и драйвер Intel — до библиотек из поставки ollama
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu:${OLLAMA_BIN%/*}/lib/ollama:${LD_LIBRARY_PATH:-}"

# Явно указать ICD Mesa Intel (при нескольких GPU/ICD можно оставить только Intel)
export VK_ICD_FILENAMES="${VK_ICD_FILENAMES:-/usr/share/vulkan/icd.d/intel_icd.x86_64.json}"

# Не задавать GGML_VK_VISIBLE_DEVICES=0 — это отключает видимые Vulkan-GPU.

export OLLAMA_VULKAN="${OLLAMA_VULKAN:-1}"

echo "Using: $OLLAMA_BIN"
echo "OLLAMA_VULKAN=$OLLAMA_VULKAN VK_ICD_FILENAMES=$VK_ICD_FILENAMES"
exec "$OLLAMA_BIN" serve "$@"
