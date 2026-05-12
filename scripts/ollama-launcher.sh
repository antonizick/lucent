#!/usr/bin/env bash
# ollama-launcher.sh — Select an Ollama model and launch OpenCode
# Usage: bash scripts/ollama-launcher.sh

set -euo pipefail

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Ollama health check ───
check_ollama() {
    if ! ollama list &>/dev/null; then
        echo -e "${RED}Error: Ollama is not running or not accessible.${NC}"
        echo "Start Ollama with:  ollama serve"
        exit 1
    fi
}

# ─── Query available models with size info ───
get_models() {
    ollama list 2>/dev/null | tail -n +2 | awk '{
        name=$1
        size=$2 " " $3
        printf "%s\t%s\n", name, size
    }'
}

# ─── Launch OpenCode with selected model ───
launch() {
    local model="$1"
    echo ""
    echo -e "${GREEN}${BOLD}[*] Launching opencode with model: ${CYAN}${model}${NC}"
    echo -e "${YELLOW}    Press Ctrl+C to cancel${NC}"
    echo ""
    exec opencode --model "${model}"
}

# ─── Pull a new model ───
pull_model() {
    echo ""
    read -rp "Model name to pull (e.g., qwen3.6:27b): " model_name
    if [[ -z "$model_name" ]]; then
        echo -e "${RED}Empty name. Pull cancelled.${NC}"
        exit 0
    fi
    echo -e "${CYAN}Pulling ${BOLD}${model_name}${NC} ..."
    ollama pull "$model_name"
    echo -e "${GREEN}Pull complete.${NC}"
    echo ""
    read -rp "Launch OpenCode with ${model_name}? [Y/n] " confirm
    if [[ "${confirm:-Y}" =~ ^[Yy]$ ]]; then
        launch "$model_name"
    fi
}

# ─── Main menu ───
main() {
    check_ollama

    local models
    models="$(get_models)"

    if [[ -z "$models" ]]; then
        echo -e "${YELLOW}No models found. Pull one first.${NC}"
        pull_model
        exit $?
    fi

    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}       Ollama Model Selector${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    local index=1
    while IFS=$'\t' read -r name size; do
        printf "  ${CYAN}%2d)${NC} ${BOLD}%-28s${NC} %s\n" "$index" "$name" "$size"
        ((index++))
    done <<< "$models"

    echo ""
    printf "  ${CYAN}%2d)${NC} ${BOLD}Pull new model${NC}\n" "$index"
    echo ""
    echo -e "  Or type a model name directly to launch"
    echo ""

    read -rp "  Select: " choice

    if [[ -z "$choice" ]]; then
        echo -e "${YELLOW}No selection. Exiting.${NC}"
        exit 0
    fi

    # Direct number selection
    if [[ "$choice" =~ ^[0-9]+$ ]]; then
    local model_count
    model_count="$(echo "$models" | wc -l)"
    local max=$((model_count + 1))

    if [[ "$choice" -eq "$max" ]]; then
            pull_model
        elif [[ "$choice" -ge 1 && "$choice" -lt "$max" ]]; then
            local selected
            selected="$(echo "$models" | sed -n "${choice}p" | cut -f1)"
            launch "$selected"
        else
            echo -e "${RED}Invalid number.${NC}"
            exit 1
        fi
    else
        # Direct name input — verify it exists locally
        if echo "$models" | cut -f1 | grep -qx "$choice"; then
            launch "$choice"
        else
            echo -e "${YELLOW}Model '${choice}' not found locally. Pull it instead?${NC}"
            read -rp "[Y/n] " pull_confirm
            if [[ "${pull_confirm:-Y}" =~ ^[Yy]$ ]]; then
                pull_model
            fi
        fi
    fi
}

main
