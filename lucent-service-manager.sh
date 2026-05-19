#!/bin/bash

################################################################################
# LUCENT SERVICE MANAGER
# Complete lifecycle management for all Lucent services
# Handles: voice boxes, Discord bots, email monitors, backup routines
################################################################################

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
LUCENT_DIR="/home/nick/dev/lucent"
UI_DIR="${LUCENT_DIR}/ui"
SCRIPTS_DIR="${LUCENT_DIR}/scripts"
LOG_DIR="${LUCENT_DIR}/memory/logs"
TEMP_LOG_DIR="/tmp"

# Service definitions
declare -A SERVICES=(
    [voice-box]="Voice Box Server (port 8001)"
    [auth-proxy]="Auth Proxy (port 8002)"
    [discord-bot]="Discord Bot"
    [discord-monitor]="Discord Monitor"
    [email-sync]="Email Sync/Score (cron)"
    [memory-backup]="Memory Backup (cron)"
    [service-monitor]="Service Monitor (cron)"
)

# Service details
declare -A SERVICE_PORT=(
    [voice-box]="8001"
    [auth-proxy]="8002"
)

declare -A SERVICE_PROCESS=(
    [voice-box]="server.py|uvicorn"
    [auth-proxy]="auth_proxy.py"
    [discord-bot]="discord_bot.py"
    [discord-monitor]="discord_monitor.py"
)

declare -A SERVICE_SCRIPT=(
    [voice-box]="${UI_DIR}/server.py"
    [auth-proxy]="${UI_DIR}/auth_proxy.py"
    [discord-bot]="${UI_DIR}/discord_bot.py"
    [discord-monitor]="${UI_DIR}/discord_monitor.py"
    [email-sync]="${SCRIPTS_DIR}/sync_and_score.py"
    [memory-backup]="${SCRIPTS_DIR}/backup_memory.py"
    [service-monitor]="${SCRIPTS_DIR}/service_monitor.py"
)

declare -A SERVICE_TYPE=(
    [voice-box]="process"
    [auth-proxy]="process"
    [discord-bot]="process"
    [discord-monitor]="process"
    [email-sync]="cron"
    [memory-backup]="cron"
    [service-monitor]="cron"
)

################################################################################
# UTILITY FUNCTIONS
################################################################################

print_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_section() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Get process IDs for a service
get_pids() {
    local service=$1
    local pids=()

    if [[ "${SERVICE_TYPE[$service]}" == "process" ]]; then
        local pattern="${SERVICE_PROCESS[$service]}"
        # Try to get PIDs by pattern
        while IFS= read -r pid; do
            [[ -n "$pid" ]] && pids+=("$pid")
        done < <(pgrep -f "$pattern" 2>/dev/null || true)
    fi

    echo "${pids[@]}"
}

# Check if port is listening
check_port() {
    local port=$1
    lsof -Pi ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1
    return $?
}

# Get PID listening on port
get_port_pid() {
    local port=$1
    lsof -Pi ":${port}" -sTCP:LISTEN -t 2>/dev/null | head -1
}

# Check if process is running
is_running() {
    local service=$1
    local port="${SERVICE_PORT[$service]}"

    if [[ -n "$port" ]]; then
        check_port "$port"
        return $?
    fi

    # For non-port services, check by process name
    local pids=($(get_pids "$service"))
    [[ ${#pids[@]} -gt 0 ]]
    return $?
}

# Get status with details
get_service_status() {
    local service=$1
    local port="${SERVICE_PORT[$service]}"
    local pids=($(get_pids "$service"))
    local status="STOPPED"
    local details=""

    if is_running "$service"; then
        status="RUNNING"
        if [[ -n "$port" ]]; then
            local port_pid=$(get_port_pid "$port")
            details="PID: $port_pid, Port: $port"
        elif [[ ${#pids[@]} -gt 0 ]]; then
            details="PIDs: ${pids[*]}"
        fi
    else
        details="Not listening"
    fi

    echo "$status|$details"
}

################################################################################
# SERVICE OPERATIONS
################################################################################

start_service() {
    local service=$1

    if is_running "$service"; then
        print_warning "$service is already running"
        return 0
    fi

    case $service in
        voice-box)
            print_info "Starting Voice Box Server (port 8001)..."
            cd "$UI_DIR"
            nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 8001 >"${TEMP_LOG_DIR}/voice_box.log" 2>&1 &
            sleep 2
            if is_running "voice-box"; then
                print_success "Voice Box Server started"
                return 0
            else
                print_error "Failed to start Voice Box Server"
                return 1
            fi
            ;;
        auth-proxy)
            print_info "Starting Auth Proxy (port 8002)..."
            cd "$UI_DIR"
            nohup python3 auth_proxy.py >"${TEMP_LOG_DIR}/auth_proxy.log" 2>&1 &
            sleep 2
            if is_running "auth-proxy"; then
                print_success "Auth Proxy started"
                return 0
            else
                print_error "Failed to start Auth Proxy"
                return 1
            fi
            ;;
        discord-bot)
            print_info "Starting Discord Bot..."
            cd "$UI_DIR"
            nohup python3 discord_bot.py >"${TEMP_LOG_DIR}/discord_bot.log" 2>&1 &
            sleep 2
            if is_running "discord-bot"; then
                print_success "Discord Bot started"
                return 0
            else
                print_error "Failed to start Discord Bot"
                return 1
            fi
            ;;
        discord-monitor)
            print_info "Starting Discord Monitor..."
            cd "$UI_DIR"
            nohup python3 discord_monitor.py >"${TEMP_LOG_DIR}/discord_monitor.log" 2>&1 &
            sleep 2
            if is_running "discord-monitor"; then
                print_success "Discord Monitor started"
                return 0
            else
                print_error "Failed to start Discord Monitor"
                return 1
            fi
            ;;
        email-sync|memory-backup|service-monitor)
            print_info "$service is a cron job - cannot start manually"
            print_info "Cron jobs run on their scheduled intervals"
            return 0
            ;;
        *)
            print_error "Unknown service: $service"
            return 1
            ;;
    esac
}

stop_service() {
    local service=$1

    if ! is_running "$service"; then
        print_warning "$service is not running"
        return 0
    fi

    case $service in
        voice-box)
            print_info "Stopping Voice Box Server..."
            local pid=$(get_port_pid "8001")
            if [[ -n "$pid" ]]; then
                kill -9 "$pid" 2>/dev/null
                sleep 1
                if ! is_running "voice-box"; then
                    print_success "Voice Box Server stopped"
                    return 0
                fi
            fi
            print_error "Failed to stop Voice Box Server"
            return 1
            ;;
        auth-proxy)
            print_info "Stopping Auth Proxy..."
            local pid=$(get_port_pid "8002")
            if [[ -n "$pid" ]]; then
                kill -9 "$pid" 2>/dev/null
                sleep 1
                if ! is_running "auth-proxy"; then
                    print_success "Auth Proxy stopped"
                    return 0
                fi
            fi
            print_error "Failed to stop Auth Proxy"
            return 1
            ;;
        discord-bot)
            print_info "Stopping Discord Bot..."
            pkill -9 -f "discord_bot.py" 2>/dev/null
            sleep 1
            if ! is_running "discord-bot"; then
                print_success "Discord Bot stopped"
                return 0
            fi
            print_error "Failed to stop Discord Bot"
            return 1
            ;;
        discord-monitor)
            print_info "Stopping Discord Monitor..."
            pkill -9 -f "discord_monitor.py" 2>/dev/null
            sleep 1
            if ! is_running "discord-monitor"; then
                print_success "Discord Monitor stopped"
                return 0
            fi
            print_error "Failed to stop Discord Monitor"
            return 1
            ;;
        email-sync|memory-backup|service-monitor)
            print_info "$service is a cron job - cannot stop manually"
            print_info "Cron jobs are managed by the system cron daemon"
            return 0
            ;;
        *)
            print_error "Unknown service: $service"
            return 1
            ;;
    esac
}

restart_service() {
    local service=$1
    print_info "Restarting $service..."
    stop_service "$service"
    sleep 1
    start_service "$service"
}

################################################################################
# STATUS REPORTING
################################################################################

show_status() {
    local target_service=$1

    print_header "LUCENT SERVICE STATUS"

    local all_running=true
    local running_count=0
    local stopped_count=0
    local cron_count=0

    for service in "${!SERVICES[@]}"; do
        # Skip if target is specified and doesn't match
        if [[ -n "$target_service" && "$target_service" != "$service" ]]; then
            continue
        fi

        local status_output=$(get_service_status "$service")
        local status="${status_output%|*}"
        local details="${status_output#*|}"
        local service_desc="${SERVICES[$service]}"
        local type="${SERVICE_TYPE[$service]}"

        if [[ "$type" == "cron" ]]; then
            ((cron_count++))
            echo ""
            echo -e "${CYAN}${service}${NC} — ${service_desc}"
            echo -e "  Type: Cron job"
            echo -e "  Status: ${YELLOW}SCHEDULED${NC}"
        else
            echo ""
            echo -e "${CYAN}${service}${NC} — ${service_desc}"

            if [[ "$status" == "RUNNING" ]]; then
                ((running_count++))
                echo -e "  Status: ${GREEN}✓ RUNNING${NC}"
            else
                ((stopped_count++))
                all_running=false
                echo -e "  Status: ${RED}✗ STOPPED${NC}"
            fi

            echo -e "  ${details}"
        fi
    done

    print_section "Summary"
    echo "  Running processes: $running_count"
    echo "  Stopped processes: $stopped_count"
    echo "  Cron jobs (scheduled): $cron_count"

    if [[ $stopped_count -gt 0 ]]; then
        echo ""
        print_warning "Some services are not running"
    fi

    echo ""
}

show_cron_jobs() {
    print_header "SCHEDULED CRON JOBS"

    echo ""
    print_section "Current cron configuration"
    crontab -l 2>/dev/null | grep -v "^#" | nl

    echo ""
    print_section "Cron job details"
    echo ""
    echo -e "${CYAN}email-sync${NC} — Email Sync/Score (sync_and_score.py)"
    echo "  Schedule: Every 5 minutes (*/5 * * * *)"
    echo "  Script: ${SCRIPTS_DIR}/sync_and_score.py"
    echo ""
    echo -e "${CYAN}email-cleanup${NC} — Email Cleanup & Sync (email_monitor.py)"
    echo "  Schedule: Every 30 minutes (*/30 * * * *)"
    echo "  Script: ${SCRIPTS_DIR}/email_monitor.py"
    echo "  Purpose: Syncs emails and removes deleted messages from database"
    echo ""
    echo -e "${CYAN}memory-backup${NC} — Memory Backup"
    echo "  Schedule: Every hour (0 * * * *)"
    echo "  Script: ${SCRIPTS_DIR}/backup_memory.py"
    echo ""
    echo -e "${CYAN}service-monitor${NC} — Service Monitor"
    echo "  Schedule: Every 15 minutes (*/15 * * * *)"
    echo "  Script: ${SCRIPTS_DIR}/service_monitor.py"
    echo ""
    echo -e "${CYAN}rotate-voice-logs${NC} — Voice Log Rotation"
    echo "  Schedule: Weekly Mondays 2:00 AM (0 2 * * 1)"
    echo "  Script: ${SCRIPTS_DIR}/rotate_voice_logs.py"
    echo ""
}

show_logs() {
    local service=$1

    print_header "SERVICE LOGS"

    case $service in
        voice-box)
            echo ""
            print_section "Voice Box Server Log (${TEMP_LOG_DIR}/voice_box.log)"
            if [[ -f "${TEMP_LOG_DIR}/voice_box.log" ]]; then
                tail -20 "${TEMP_LOG_DIR}/voice_box.log"
            else
                print_warning "Log file not found"
            fi
            ;;
        auth-proxy)
            echo ""
            print_section "Auth Proxy Log (${TEMP_LOG_DIR}/auth_proxy.log)"
            if [[ -f "${TEMP_LOG_DIR}/auth_proxy.log" ]]; then
                tail -20 "${TEMP_LOG_DIR}/auth_proxy.log"
            else
                print_warning "Log file not found"
            fi
            ;;
        discord-bot)
            echo ""
            print_section "Discord Bot Log (${TEMP_LOG_DIR}/discord_bot.log)"
            if [[ -f "${TEMP_LOG_DIR}/discord_bot.log" ]]; then
                tail -20 "${TEMP_LOG_DIR}/discord_bot.log"
            else
                print_warning "Log file not found"
            fi
            ;;
        discord-monitor)
            echo ""
            print_section "Discord Monitor Log (${TEMP_LOG_DIR}/discord_monitor.log)"
            if [[ -f "${TEMP_LOG_DIR}/discord_monitor.log" ]]; then
                tail -20 "${TEMP_LOG_DIR}/discord_monitor.log"
            else
                print_warning "Log file not found"
            fi
            ;;
        cron)
            echo ""
            print_section "Service Monitor Cron Log (${LOG_DIR}/cron.log)"
            if [[ -f "${LOG_DIR}/cron.log" ]]; then
                tail -20 "${LOG_DIR}/cron.log"
            else
                print_warning "Cron log not found"
            fi
            echo ""
            print_section "Email Sync Cron Log (${LOG_DIR}/email_sync.log)"
            if [[ -f "${LOG_DIR}/email_sync.log" ]]; then
                tail -20 "${LOG_DIR}/email_sync.log"
            else
                print_warning "Email sync log not found"
            fi
            ;;
        *)
            echo ""
            print_info "Available logs:"
            ls -lh "${TEMP_LOG_DIR}"/*.log 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
            ls -lh "${LOG_DIR}"/activity_*.log 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
            ;;
    esac
    echo ""
}

################################################################################
# INTERACTIVE MENU SYSTEM
################################################################################

show_main_menu() {
    echo ""
    print_header "LUCENT SERVICE MANAGER"
    echo ""
    echo "What would you like to do?"
    echo ""
    echo -e "  ${CYAN}1${NC}) Check service status"
    echo -e "  ${CYAN}2${NC}) Start service(s)"
    echo -e "  ${CYAN}3${NC}) Stop service(s)"
    echo -e "  ${CYAN}4${NC}) Restart service(s)"
    echo -e "  ${CYAN}5${NC}) View service logs"
    echo -e "  ${CYAN}6${NC}) View cron job configuration"
    echo -e "  ${CYAN}0${NC}) Exit"
    echo ""
}

show_service_menu() {
    echo ""
    print_section "Select service(s)"
    echo ""
    echo -e "  ${CYAN}1${NC}) voice-box         — Voice Box Server (port 8001)"
    echo -e "  ${CYAN}2${NC}) auth-proxy        — Auth Proxy (port 8002)"
    echo -e "  ${CYAN}3${NC}) discord-bot       — Discord Bot"
    echo -e "  ${CYAN}4${NC}) discord-monitor   — Discord Monitor"
    echo -e "  ${CYAN}5${NC}) email-sync        — Email Sync/Score (cron)"
    echo -e "  ${CYAN}6${NC}) memory-backup     — Memory Backup (cron)"
    echo -e "  ${CYAN}7${NC}) service-monitor   — Service Monitor (cron)"
    echo -e "  ${CYAN}8${NC}) all               — All services"
    echo -e "  ${CYAN}0${NC}) Back to main menu"
    echo ""
}

show_logs_menu() {
    echo ""
    print_section "Select service logs to view"
    echo ""
    echo -e "  ${CYAN}1${NC}) voice-box         — Voice Box Server logs"
    echo -e "  ${CYAN}2${NC}) auth-proxy        — Auth Proxy logs"
    echo -e "  ${CYAN}3${NC}) discord-bot       — Discord Bot logs"
    echo -e "  ${CYAN}4${NC}) discord-monitor   — Discord Monitor logs"
    echo -e "  ${CYAN}5${NC}) cron              — Cron job activity logs"
    echo -e "  ${CYAN}6${NC}) all               — View all available logs"
    echo -e "  ${CYAN}0${NC}) Back to main menu"
    echo ""
}

get_user_input() {
    local prompt=$1
    local input
    read -p "$prompt" input
    echo "$input"
}

handle_status() {
    show_status
    read -p "Press Enter to continue..."
}

handle_start() {
    show_service_menu
    local choice=$(get_user_input "Enter selection: ")

    case $choice in
        1)
            show_status
            echo ""
            print_section "Starting voice-box..."
            start_service "voice-box"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        2)
            show_status
            echo ""
            print_section "Starting auth-proxy..."
            start_service "auth-proxy"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        3)
            show_status
            echo ""
            print_section "Starting discord-bot..."
            start_service "discord-bot"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        4)
            show_status
            echo ""
            print_section "Starting discord-monitor..."
            start_service "discord-monitor"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        5|6|7)
            print_info "This is a cron job - it runs on a schedule"
            read -p "Press Enter to continue..."
            ;;
        8)
            show_status
            echo ""
            print_section "Starting all services..."
            for service in voice-box auth-proxy discord-bot discord-monitor; do
                start_service "$service"
            done
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        0)
            return
            ;;
        *)
            print_error "Invalid selection"
            read -p "Press Enter to continue..."
            ;;
    esac
}

handle_stop() {
    show_service_menu
    local choice=$(get_user_input "Enter selection: ")

    case $choice in
        1)
            show_status
            echo ""
            print_section "Stopping voice-box..."
            stop_service "voice-box"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        2)
            show_status
            echo ""
            print_section "Stopping auth-proxy..."
            stop_service "auth-proxy"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        3)
            show_status
            echo ""
            print_section "Stopping discord-bot..."
            stop_service "discord-bot"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        4)
            show_status
            echo ""
            print_section "Stopping discord-monitor..."
            stop_service "discord-monitor"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        5|6|7)
            print_info "This is a cron job - it runs on a schedule"
            read -p "Press Enter to continue..."
            ;;
        8)
            show_status
            echo ""
            print_section "Stopping all services..."
            for service in voice-box auth-proxy discord-bot discord-monitor; do
                stop_service "$service"
            done
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        0)
            return
            ;;
        *)
            print_error "Invalid selection"
            read -p "Press Enter to continue..."
            ;;
    esac
}

handle_restart() {
    show_service_menu
    local choice=$(get_user_input "Enter selection: ")

    case $choice in
        1)
            show_status
            echo ""
            print_section "Restarting voice-box..."
            restart_service "voice-box"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        2)
            show_status
            echo ""
            print_section "Restarting auth-proxy..."
            restart_service "auth-proxy"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        3)
            show_status
            echo ""
            print_section "Restarting discord-bot..."
            restart_service "discord-bot"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        4)
            show_status
            echo ""
            print_section "Restarting discord-monitor..."
            restart_service "discord-monitor"
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        5|6|7)
            print_info "This is a cron job - it runs on a schedule"
            read -p "Press Enter to continue..."
            ;;
        8)
            show_status
            echo ""
            print_section "Restarting all services..."
            for service in voice-box auth-proxy discord-bot discord-monitor; do
                restart_service "$service"
            done
            echo ""
            show_status
            read -p "Press Enter to continue..."
            ;;
        0)
            return
            ;;
        *)
            print_error "Invalid selection"
            read -p "Press Enter to continue..."
            ;;
    esac
}

handle_logs() {
    show_logs_menu
    local choice=$(get_user_input "Enter selection: ")

    case $choice in
        1) show_logs "voice-box"; read -p "Press Enter to continue..." ;;
        2) show_logs "auth-proxy"; read -p "Press Enter to continue..." ;;
        3) show_logs "discord-bot"; read -p "Press Enter to continue..." ;;
        4) show_logs "discord-monitor"; read -p "Press Enter to continue..." ;;
        5) show_logs "cron"; read -p "Press Enter to continue..." ;;
        6) show_logs; read -p "Press Enter to continue..." ;;
        0) return ;;
        *) print_error "Invalid selection"; read -p "Press Enter to continue..." ;;
    esac
}

################################################################################
# MAIN INTERACTIVE LOOP
################################################################################

main() {
    while true; do
        clear
        show_main_menu

        local choice=$(get_user_input "Enter your choice: ")

        case $choice in
            1) handle_status ;;
            2) handle_start ;;
            3) handle_stop ;;
            4) handle_restart ;;
            5) handle_logs ;;
            6) show_cron_jobs; read -p "Press Enter to continue..." ;;
            0)
                echo ""
                print_info "Goodbye!"
                exit 0
                ;;
            *)
                print_error "Invalid selection. Please try again."
                read -p "Press Enter to continue..."
                ;;
        esac
    done
}

main "$@"
