#!/usr/bin/env bash
set -euo pipefail
model_dir="${1:-models}"
revision=bb307c036e8a1ed7b663bbd0c35b41c4c9294cfd
mkdir -p "$model_dir"
download() {
    local name="$1" expected="$2" target="$model_dir/$1"
    if [[ -f "$target" ]] && printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status; then
        echo "Verified existing $name"
        return
    fi
    curl --fail --location --retry 4 --continue-at - \
        "https://huggingface.co/ggml-org/Qwen2-VL-2B-Instruct-GGUF/resolve/$revision/$name" \
        --output "$target.partial"
    printf '%s  %s\n' "$expected" "$target.partial" | sha256sum --check
    mv "$target.partial" "$target"
}
download Qwen2-VL-2B-Instruct-Q4_K_M.gguf 5745685d2e607a82a0696c1118e56a2a1ae0901da450fd9cd4f161c6b62867d7
download mmproj-Qwen2-VL-2B-Instruct-f16.gguf ecb20cabcdd8dbc277de06bd6eb980aeb2adfaaba9f199a434e328d205675d03
