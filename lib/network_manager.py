#!/usr/bin/env python3

import subprocess
import sys


class NetworkManager:
    """Manages TAP devices, networking, and device allocation"""
    
    def __init__(self):
        self.allocated_tap_devices = set()  # Track devices allocated in this session
    
    def _run_command(self, cmd, check=True, capture_output=True, text=True):
        """Helper method to run subprocess commands with consistent error handling"""
        try:
            return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)
        except subprocess.CalledProcessError as e:
            if capture_output:
                print(f"Command failed: {' '.join(cmd)}\nError: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Unexpected error running command: {' '.join(cmd)}\nError: {e}", file=sys.stderr)
            raise
    
    def _setup_device_common(self, device_name):
        """Common device setup logic - check if device exists"""
        result = self._run_command(["ip", "link", "show", device_name], check=False)
        return result.returncode == 0  # True if device exists
    
    def _create_tap_device(self, device_name):
        """Create a TAP device"""
        print(f"Creating {device_name}")
        self._run_command(["sudo", "ip", "tuntap", "add", device_name, "mode", "tap"])
        print(f"✓ {device_name} created")
    
    def _bring_device_up(self, device_name):
        """Bring a network device up"""
        print(f"Bringing up {device_name}")
        self._run_command(["sudo", "ip", "link", "set", device_name, "up"])
        print(f"✓ {device_name} is up")
    
    def discover_existing_tap_devices(self):
        """Discover existing TAP devices on the system"""
        try:
            result = self._run_command(["ip", "link", "show"])
            
            # Parse output to find tap devices (format: "1: tap0: <BROADCAST,MULTICAST> ...")
            tap_devices = []
            for line in result.stdout.split('\n'):
                if 'tap' in line and ':' in line:
                    # Extract device name between first and second colon
                    parts = line.split(':')
                    if len(parts) >= 2:
                        device_name = parts[1].strip()
                        if device_name.startswith('tap') and device_name not in tap_devices:
                            tap_devices.append(device_name)
            
            return tap_devices
            
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Warning: Could not discover TAP devices: {e}", file=sys.stderr)
            return []
    
    def find_next_available_tap_device(self, prefix="tap"):
        """Find next available tap device name (tap0, tap1, etc.)"""
        existing_devices = self.discover_existing_tap_devices()
        
        # Extract indices from existing tap devices (system + session allocated)
        used_indices = set()
        
        # Add system devices
        for device in existing_devices:
            if device.startswith(prefix):
                try:
                    # Extract number after prefix (e.g., "tap0" -> 0)
                    index_str = device[len(prefix):]
                    if index_str.isdigit():
                        used_indices.add(int(index_str))
                except ValueError:
                    continue
        
        # Add session-allocated devices
        for device in self.allocated_tap_devices:
            if device.startswith(prefix):
                try:
                    index_str = device[len(prefix):]
                    if index_str.isdigit():
                        used_indices.add(int(index_str))
                except ValueError:
                    continue
        
        # Find first available index starting from 0
        index = 0
        while index in used_indices:
            index += 1
        
        device_name = f"{prefix}{index}"
        # Track this device as allocated
        self.allocated_tap_devices.add(device_name)
        return device_name
    
    def validate_tap_device_available(self, device_name):
        """Check if a TAP device name is available (doesn't exist on system)"""
        if not device_name:
            return True  # None/empty is valid (will be auto-generated)
        
        existing_devices = self.discover_existing_tap_devices()
        
        if device_name in existing_devices:
            return False  # Device already exists
        
        # Also check if it's been allocated in this session
        if device_name in self.allocated_tap_devices:
            return False  # Device already allocated in this session
        
        return True  # Device is available
    
    def get_tap_device_ip(self, device_name):
        """Get IP address of a TAP device from the system"""
        if not device_name or device_name == 'N/A':
            return 'N/A'
        
        try:
            result = self._run_command(["ip", "addr", "show", device_name])
            
            # Parse output to find IPv4 address
            for line in result.stdout.split('\n'):
                line = line.strip()
                if 'inet ' in line and not line.startswith('inet 127.'):
                    # Extract IP address (format: "inet 192.168.1.1/32 scope global tap0")
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'inet' and i + 1 < len(parts):
                            ip_with_mask = parts[i + 1]
                            # Remove subnet mask if present
                            ip_addr = ip_with_mask.split('/')[0]
                            return ip_addr
            
            return 'N/A'
            
        except (subprocess.CalledProcessError, Exception):
            return 'N/A'
    
    def setup_mmds_tap_device(self, mmds_tap):
        """Create MMDS TAP device on host (no IP configuration needed)"""
        try:
            # Check if MMDS TAP device already exists
            if not self._setup_device_common(mmds_tap):
                # MMDS TAP device doesn't exist, create it
                self._create_tap_device(mmds_tap)
            else:
                print(f"✓ MMDS TAP device {mmds_tap} already exists")
            
            # Bring MMDS TAP device up
            self._bring_device_up(mmds_tap)
            
            return True
            
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error setting up MMDS TAP device: {e}", file=sys.stderr)
            return False
    
    def setup_tap_device(self, tap_device, tap_ip, vm_ip):
        """Create and configure TAP device on host"""
        try:
            # Check if TAP device already exists
            if not self._setup_device_common(tap_device):
                # TAP device doesn't exist, create it
                self._create_tap_device(tap_device)
            else:
                print(f"✓ TAP device {tap_device} already exists")
            
            # Check if IP address is already configured
            addr_result = self._run_command(["ip", "addr", "show", tap_device])
            
            if f"{tap_ip}/32" not in addr_result.stdout:
                # Configure IP address on TAP device
                print(f"Configuring IP {tap_ip}/32 on {tap_device}")
                self._run_command(["sudo", "ip", "addr", "add", f"{tap_ip}/32", "dev", tap_device])
                print(f"✓ IP {tap_ip}/32 configured on {tap_device}")
            else:
                print(f"✓ IP {tap_ip}/32 already configured on {tap_device}")
            
            # Bring TAP device up
            self._bring_device_up(tap_device)
            
            # Check if route already exists
            route_result = self._run_command(["ip", "route", "show", f"{vm_ip}/32"])
            
            if not route_result.stdout.strip():
                # Add route for VM IP via TAP device
                print(f"Adding route for VM IP {vm_ip} via {tap_device}")
                self._run_command(["sudo", "ip", "route", "add", f"{vm_ip}/32", "dev", tap_device])
                print(f"✓ Route for {vm_ip} via {tap_device} added")
            else:
                print(f"✓ Route for {vm_ip} already exists")
            
            return True
            
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error setting up TAP device: {e}", file=sys.stderr)
            return False
    
    def remove_tap_device(self, tap_device):
        """Remove TAP device (routes are automatically removed)"""
        try:
            # Check if TAP device exists
            if self._setup_device_common(tap_device):
                print(f"Removing TAP device: {tap_device}")
                self._run_command(["sudo", "ip", "link", "del", tap_device])
                print(f"✓ TAP device {tap_device} removed (routes automatically removed)")
            else:
                print(f"✓ TAP device {tap_device} doesn't exist")
            
            return True
            
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error removing TAP device: {e}", file=sys.stderr)
            return False