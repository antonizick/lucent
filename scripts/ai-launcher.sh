#!/usr/bin/env bash
# ai-launcher.sh — Multi-platform AI launcher with model selection
# Usage: bash scripts/ai-launcher.sh [platform] [model]
# Examples:
#   bash scripts/ai-launcher.sh                 # Interactive menu
#   bash scripts/ai-launcher.sh claude opus     # Quick-launch: Claude + Opus
#   bash scripts/ai-launcher.sh opencode big-pickle

set -euo pipefail

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Get available Ollama models ───
get_ollama_models() {
    if ! ollama list &>/dev/null; then
        return 1
    fi
    ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' 2>/dev/null || true
}

# ─── Get Anthropic models (for Claude) ───
get_anthropic_models() {
    echo -e "opus\nsonnet\nhaiku"
}

# ─── Get OpenCode free models ───
get_opencode_free_models() {
    echo -e "big-pickle\ndeepseek-v4-flash-free\nminimax-m2.5-free\nnemotron-3-super-free\nring-2.6-1t-free"
}

# ─── Launch Claude with model ───
launch_claude() {
    local model="$1"
    local model_type="$2"

    echo ""
    echo -e "${GREEN}${BOLD}[*] Launching Claude with model: ${CYAN}${model}${NC}"
    echo -e "${YELLOW}    Press Ctrl+C to cancel${NC}"
    echo ""

    cd /home/nick/dev/lucent

    if [[ "$model_type" == "anthropic" ]]; then
        exec claude --model "$model"
    elif [[ "$model_type" == "ollama" ]]; then
        exec ollama launch claude --model "$model"
    fi
}

# ─── Launch OpenCode with model ───
launch_opencode() {
    local model="$1"
    local model_type="$2"

    echo ""
    echo -e "${GREEN}${BOLD}[*] Launching OpenCode with model: ${CYAN}${model}${NC}"
    echo -e "${YELLOW}    Press Ctrl+C to cancel${NC}"
    echo ""

    cd /home/nick/dev/lucent

    if [[ "$model_type" == "free" ]]; then
        exec opencode /home/nick/dev/lucent --model "opencode/${model}"
    elif [[ "$model_type" == "ollama" ]]; then
        exec ollama launch opencode --model "$model"
    fi
}

# ─── Show Claude model selection menu ───
select_claude_model() {
    local ollama_models
    ollama_models="$(get_ollama_models)" || ollama_models=""

    local anthropic_models
    anthropic_models="$(get_anthropic_models)"

    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}       Claude — Select Model${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    local index=1
    declare -A model_map

    # Anthropic models (color: magenta)
    if [[ -n "$anthropic_models" ]]; then
        echo -e "${MAGENTA}${BOLD}Anthropic Models:${NC}"
        while IFS= read -r model; do
            [[ -z "$model" ]] && continue
            printf "  ${CYAN}%2d)${NC} ${BOLD}%-30s${NC} ${MAGENTA}(anthropic)${NC}\n" "$index" "$model"
            model_map["$index"]="$model|anthropic"
            ((index++))
        done <<< "$anthropic_models"
        echo ""
    fi

    # Ollama models (color: blue)
    if [[ -n "$ollama_models" ]]; then
        echo -e "${BLUE}${BOLD}Local Ollama Models:${NC}"
        while IFS= read -r model; do
            [[ -z "$model" ]] && continue
            printf "  ${CYAN}%2d)${NC} ${BOLD}%-30s${NC} ${BLUE}(ollama)${NC}\n" "$index" "$model"
            model_map["$index"]="$model|ollama"
            ((index++))
        done <<< "$ollama_models"
        echo ""
    fi

    echo -e "  ${CYAN}b)${NC} ${DIM}Go back${NC}"
    echo ""

    read -rp "  Select: " choice

    if [[ "$choice" == "b" || "$choice" == "B" ]]; then
        return 2  # Signal to go back
    fi

    if [[ -n "${model_map[$choice]:-}" ]]; then
        IFS='|' read -r model model_type <<< "${model_map[$choice]}"
        launch_claude "$model" "$model_type"
    else
        echo -e "${RED}Invalid selection.${NC}"
        sleep 1
        select_claude_model
    fi
}

# ─── Show OpenCode model selection menu ───
select_opencode_model() {
    local ollama_models
    ollama_models="$(get_ollama_models)" || ollama_models=""

    local opencode_free_models
    opencode_free_models="$(get_opencode_free_models)"

    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}       OpenCode — Select Model${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    local index=1
    declare -A model_map

    # OpenCode free models (color: green)
    if [[ -n "$opencode_free_models" ]]; then
        echo -e "${GREEN}${BOLD}OpenCode Free Models:${NC}"
        while IFS= read -r model; do
            [[ -z "$model" ]] && continue
            printf "  ${CYAN}%2d)${NC} ${BOLD}%-30s${NC} ${GREEN}(free)${NC}\n" "$index" "$model"
            model_map["$index"]="$model|free"
            ((index++))
        done <<< "$opencode_free_models"
        echo ""
    fi

    # Ollama models (color: blue)
    if [[ -n "$ollama_models" ]]; then
        echo -e "${BLUE}${BOLD}Local Ollama Models:${NC}"
        while IFS= read -r model; do
            [[ -z "$model" ]] && continue
            printf "  ${CYAN}%2d)${NC} ${BOLD}%-30s${NC} ${BLUE}(ollama)${NC}\n" "$index" "$model"
            model_map["$index"]="$model|ollama"
            ((index++))
        done <<< "$ollama_models"
        echo ""
    fi

    echo -e "  ${CYAN}b)${NC} ${DIM}Go back${NC}"
    echo ""

    read -rp "  Select: " choice

    if [[ "$choice" == "b" || "$choice" == "B" ]]; then
        return 2  # Signal to go back
    fi

    if [[ -n "${model_map[$choice]:-}" ]]; then
        IFS='|' read -r model model_type <<< "${model_map[$choice]}"
        launch_opencode "$model" "$model_type"
    else
        echo -e "${RED}Invalid selection.${NC}"
        sleep 1
        select_opencode_model
    fi
}

# ─── Platform selection menu ───
select_platform() {
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}       Multi-AI Launcher${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  ${CYAN}1)${NC} ${BOLD}Claude${NC}     (Anthropic + Local Models)"
    echo -e "  ${CYAN}2)${NC} ${BOLD}OpenCode${NC}   (Free Models + Local Models)"
    echo ""

    read -rp "  Select: " choice

    case "$choice" in
        1)
            select_claude_model
            ;;
        2)
            select_opencode_model
            ;;
        *)
            echo -e "${RED}Invalid selection.${NC}"
            sleep 1
            clear
            select_platform
            ;;
    esac
}

# ─── Quick-launch mode (CLI args) ───
quick_launch() {
    local platform="$1"
    local model="$2"

    case "$platform" in
        claude)
            # Determine model type (anthropic or ollama)
            if echo "opus sonnet haiku" | grep -qw "$model"; then
                launch_claude "$model" "anthropic"
            else
                # Assume ollama model
                launch_claude "$model" "ollama"
            fi
            ;;
        opencode)
            # Determine model type (free or ollama)
            if echo "big-pickle deepseek-v4-flash-free minimax-m2.5-free nemotron-3-super-free ring-2.6-1t-free" | grep -qw "$model"; then
                launch_opencode "$model" "free"
            else
                # Assume ollama model
                launch_opencode "$model" "ollama"
            fi
            ;;
        *)
            echo -e "${RED}Unknown platform: $platform${NC}"
            echo "Supported: claude, opencode"
            exit 1
            ;;
    esac
}

# ─── Main entry point ───
main() {
    if [[ $# -eq 2 ]]; then
        # Quick-launch mode
        quick_launch "$1" "$2"
    elif [[ $# -eq 0 ]]; then
        # Interactive mode
        clear
        select_platform
    else
        echo "Usage: $0 [platform] [model]"
        echo "  Interactive:  $0"
        echo "  Quick-launch: $0 claude opus"
        echo "  Quick-launch: $0 opencode big-pickle"
        exit 1
    fi
}

main "$@"
