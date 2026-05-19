#!/usr/bin/env python3
"""
Service Health Monitor - Checks and restarts Lucent services every 15 minutes
Monitors ports 8001 (server.py) and 8002 (auth_proxy.py)
Logs to activity log for troubleshooting and trend analysis
"""

import subprocess
import requests
import os
import sys
from datetime import datetime
import time

# Configuration
SERVICES = {
    8001: {
        'name': 'server.py',
        'script': 'server.py',
        'health_endpoint': 'http://localhost:8001/services/health',
        'fallback_endpoint': 'http://localhost:8001/'
    },
    8002: {
        'name': 'auth_proxy.py',
        'script': 'auth_proxy.py',
        'health_endpoint': 'http://localhost:8002/',
    }
}

UI_DIR = '/home/nick/dev/lucent/ui'
LOGS_DIR = '/home/nick/dev/lucent/memory/logs'
ACTIVITY_LOG = os.path.join(LOGS_DIR, f"activity_{datetime.now().strftime('%Y-%m-%d')}.log")


def log_activity(component, level, message):
    """Log to activity log file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] [{component}] {level}: {message}\n"

    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(ACTIVITY_LOG, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Failed to write to activity log: {e}", file=sys.stderr)

    print(log_entry.strip())


def is_port_listening(port):
    """Check if a port is listening"""
    try:
        result = subprocess.run(
            ['lsof', '-i', f':{port}', '-t'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        log_activity('service-monitor', 'ERROR', f"Failed to check port {port}: {e}")
        return False


def check_service_health(port, config):
    """Check if a service is healthy via HTTP endpoint"""
    endpoints = [config.get('health_endpoint'), config.get('fallback_endpoint')]

    for endpoint in endpoints:
        if not endpoint:
            continue
        try:
            response = requests.get(endpoint, timeout=2)
            return response.status_code < 500
        except Exception:
            pass

    return False


def get_process_id(port):
    """Get the PID of the process listening on a port"""
    try:
        result = subprocess.run(
            ['lsof', '-i', f':{port}', '-t'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            return int(result.stdout.strip().split('\n')[0])
    except Exception:
        pass
    return None


def restart_services():
    """Restart both services"""
    log_activity('service-monitor', 'NOTICE', 'Restarting services...')

    try:
        # Kill existing processes
        for port in SERVICES.keys():
            pid = get_process_id(port)
            if pid:
                try:
                    os.kill(pid, 9)
                    log_activity('service-monitor', 'NOTICE', f'Killed process on port {port} (PID: {pid})')
                except Exception as e:
                    log_activity('service-monitor', 'WARN', f'Failed to kill process on port {port}: {e}')

        time.sleep(1)

        # Start services
        os.chdir(UI_DIR)

        # Start server.py
        subprocess.Popen(
            ['python3', 'server.py'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log_activity('service-monitor', 'NOTICE', 'Started server.py on port 8001')
        time.sleep(2)

        # Start auth_proxy.py
        subprocess.Popen(
            ['python3', 'auth_proxy.py'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log_activity('service-monitor', 'NOTICE', 'Started auth_proxy.py on port 8002')
        time.sleep(2)

        return True
    except Exception as e:
        log_activity('service-monitor', 'ERROR', f'Failed to restart services: {e}')
        return False


def monitor_services():
    """Check service health and restart if needed"""
    all_healthy = True
    issues = []

    for port, config in SERVICES.items():
        service_name = config['name']

        # Check if port is listening
        if not is_port_listening(port):
            all_healthy = False
            msg = f'{service_name} not listening on port {port}'
            issues.append(msg)
            log_activity('service-monitor', 'ERROR', msg)
            continue

        # Check health endpoint
        if not check_service_health(port, config):
            all_healthy = False
            msg = f'{service_name} on port {port} is not responding to health checks'
            issues.append(msg)
            log_activity('service-monitor', 'WARN', msg)

    # Only log if there are issues
    if not all_healthy:
        log_activity('service-monitor', 'ALERT', f'Service issues detected: {", ".join(issues)}')

        if restart_services():
            log_activity('service-monitor', 'NOTICE', 'Services restarted successfully')
        else:
            log_activity('service-monitor', 'ERROR', 'Failed to restart services')

    return all_healthy


if __name__ == '__main__':
    try:
        success = monitor_services()
        sys.exit(0 if success else 1)
    except Exception as e:
        log_activity('service-monitor', 'FATAL', f'Unexpected error: {e}')
        sys.exit(1)
