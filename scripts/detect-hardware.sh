#!/bin/bash
# Holma - Hardware Detection Script
# Detects architecture, platform, RAM and USB capabilities
# Runs at container start, outputs environment variables

set -e

# --- Architecture Detection ---
detect_arch() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)       echo "amd64" ;;
        aarch64)      echo "arm64" ;;
        armv7l|armhf) echo "arm" ;;
        *)            echo "unknown" ;;
    esac
}

# --- Platform Detection ---
detect_platform() {
    # Raspberry Pi: check device-tree model or cpuinfo
    if [ -f /proc/device-tree/model ] 2>/dev/null; then
        local model
        model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || true)
        if echo "$model" | grep -qi "raspberry"; then
            echo "raspberrypi"
            return
        fi
    fi

    if [ -f /proc/cpuinfo ]; then
        if grep -qi "raspberry" /proc/cpuinfo 2>/dev/null; then
            echo "raspberrypi"
            return
        fi
    fi

    # Synology DSM: check for syno markers
    if [ -f /etc/synoinfo.conf ] || { [ -d /var/packages ] && [ -f /etc/VERSION ]; }; then
        echo "synology"
        return
    fi

    # Check from host environment variable
    if [ -n "$SYNOLOGY_DSM" ] || [ -n "$SYNO_PLATFORM" ]; then
        echo "synology"
        return
    fi

    echo "generic"
}

# --- RAM Detection (in MB) ---
detect_ram_mb() {
    if [ -f /proc/meminfo ]; then
        local kb
        kb=$(grep -i "^MemTotal:" /proc/meminfo | awk '{print $2}')
        echo $(( kb / 1024 ))
    else
        echo "0"
    fi
}

# --- USB Detection ---
detect_usb() {
    if [ -d /run/udev ] && [ -d /dev/bus/usb ] 2>/dev/null; then
        echo "true"
    else
        echo "false"
    fi
}

# --- Recommended parallel tasks based on RAM ---
recommend_parallel_tasks() {
    local ram_mb=$1
    if [ "$ram_mb" -le 512 ]; then
        echo "1"
    elif [ "$ram_mb" -le 1024 ]; then
        echo "1"
    elif [ "$ram_mb" -le 2048 ]; then
        echo "2"
    elif [ "$ram_mb" -le 4096 ]; then
        echo "3"
    else
        echo "4"
    fi
}

# --- Main ---
main() {
    HARDWARE_ARCH=$(detect_arch)
    HARDWARE_PLATFORM=$(detect_platform)
    HARDWARE_RAM_MB=$(detect_ram_mb)
    USB_DETECTION_ENABLED=$(detect_usb)
    RECOMMENDED_PARALLEL_TASKS=$(recommend_parallel_tasks "$HARDWARE_RAM_MB")

    # Allow PLATFORM_PROFILE override
    if [ "${PLATFORM_PROFILE:-auto}" != "auto" ]; then
        HARDWARE_PLATFORM="$PLATFORM_PROFILE"
    fi

    # Export as environment variables
    export HARDWARE_ARCH
    export HARDWARE_PLATFORM
    export HARDWARE_RAM_MB
    export USB_DETECTION_ENABLED
    export RECOMMENDED_PARALLEL_TASKS

    # Print detection results for logging
    echo "=== Holma Hardware Detection ==="
    echo "  Architecture:     $HARDWARE_ARCH"
    echo "  Platform:         $HARDWARE_PLATFORM"
    echo "  RAM:              ${HARDWARE_RAM_MB} MB"
    echo "  USB Detection:    $USB_DETECTION_ENABLED"
    echo "  Recommended Tasks: $RECOMMENDED_PARALLEL_TASKS"
    echo "======================================="
}

main
