#!/bin/bash

# This i a sample bash script to retrieve ip config 
# from firecracker MMDS and configure the interfaces
# inside the vm

# Set up mmds interface so we can get metadata
ip link set dev eth1 name mmds
ip link set mmds up
ip route add 169.254.169.254 dev mmds

# Add a small delay to ensure the interface is ready
sleep 0.2

# Fetch network config with error checking
IP=$(curl -s --max-time 1 http://169.254.169.254/network_config/ip)
GATEWAY=$(curl -s --max-time 1 http://169.254.169.254/network_config/gateway)

# Debug: log the values (you can check these in system logs)
echo "Retrieved IP: '$IP'" >&2
echo "Retrieved Gateway: '$GATEWAY'" >&2

# Check if values were retrieved successfully
if [ -z "$IP" ] || [ -z "$GATEWAY" ]; then
    echo "Failed to retrieve network configuration" >&2
    exit 1
fi

# Apply network configuration
ip addr add "$IP" dev eth0
ip link set eth0 up
ip route add "$GATEWAY" dev eth0
ip route add default via "$GATEWAY" dev eth0