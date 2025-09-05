#!/usr/bin/env python3

from pathlib import Path
from .firecracker_api import FirecrackerAPI
from .config_manager import ConfigManager
from .network_manager import NetworkManager


class VMDiscovery:
    """Manages VM discovery and state detection"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager or ConfigManager()
        self.socket_path_prefix = self.config_manager.get_socket_path_prefix()
        self.network_manager = NetworkManager()
    
    def discover_all_vms(self):
        """Discover all VMs (both running and stopped) by scanning cache and socket directories
        
        Returns:
            list: List of VM dictionaries containing:
                - name: VM name
                - state: 'running' or 'stopped'
                - socket_path: Path to socket file
                - config: Live API configuration (for running VMs)
                - cached_config: Cached configuration from file
                - vm_ip: VM internal IP address
                - tap_ip: TAP device IP address
                - base_image: Base image used to create VM
                - networkdriver: Network driver mode (internal/external)
        """
        all_vms = []
        
        # First, get all cached VMs
        if self.config_manager.cache_dir.exists():
            for cache_file in self.config_manager.cache_dir.glob("*.json"):
                vm_name = cache_file.stem  # filename without .json extension
                
                # Check if VM is running by looking for socket and testing connection
                socket_path = str(Path(self.socket_path_prefix) / f"{vm_name}.sock")
                is_running = False
                vm_config = None
                
                if Path(socket_path).exists():
                    # Create a temporary API client for this socket
                    temp_api = FirecrackerAPI(socket_path)
                    if temp_api.check_socket_in_use():
                        vm_config = temp_api.get_vm_config()
                        if vm_config:
                            is_running = True
                
                # Load cached configuration
                try:
                    cached_config = self.config_manager.load_vm_config(vm_name)
                    if not cached_config:  # Skip VMs with corrupted cache files
                        continue
                except Exception:
                    continue
                
                # Extract key information for easier access
                vm_ip = cached_config.get('vm_ip', 'N/A')
                tap_ip = cached_config.get('tap_ip', 'N/A')
                base_image = cached_config.get('base_image', 'N/A')
                networkdriver = cached_config.get('networkdriver', 'internal')
                
                # For running VMs, try to get current TAP IP from device
                if is_running:
                    tap_device = cached_config.get('tap_device', 'N/A')
                    if tap_device != 'N/A':
                        current_tap_ip = self.network_manager.get_tap_device_ip(tap_device)
                        if current_tap_ip and current_tap_ip != 'N/A':
                            tap_ip = current_tap_ip
                    
                    # Try to get internal IP from MMDS
                    mmds_data = self._get_mmds_data_for_vm(socket_path)
                    if mmds_data and 'network_config' in mmds_data:
                        mmds_vm_ip = mmds_data['network_config'].get('ip', 'N/A')
                        if mmds_vm_ip != 'N/A':
                            vm_ip = mmds_vm_ip
                
                all_vms.append({
                    'name': vm_name,
                    'socket_path': socket_path,
                    'config': vm_config,
                    'cached_config': cached_config,
                    'state': 'running' if is_running else 'stopped',
                    'vm_ip': vm_ip,
                    'tap_ip': tap_ip,
                    'base_image': base_image,
                    'networkdriver': networkdriver
                })
        
        return all_vms
    
    def discover_running_vms(self):
        """Discover running VMs by scanning socket files in socket directory
        
        Returns:
            list: List of running VM dictionaries with name, socket_path, and config
        """
        socket_dir = Path(self.socket_path_prefix)
        running_vms = []
        
        if not socket_dir.exists():
            return running_vms
        
        # Find all .sock files in the directory
        for socket_file in socket_dir.glob("*.sock"):
            vm_name = socket_file.stem  # filename without .sock extension
            socket_path = str(socket_file)
            
            # Create a temporary API client for this socket
            temp_api = FirecrackerAPI(socket_path)
            
            # Try to get VM config
            if temp_api.check_socket_in_use():
                vm_config = temp_api.get_vm_config()
                if vm_config:
                    running_vms.append({
                        'name': vm_name,
                        'socket_path': socket_path,
                        'config': vm_config
                    })
        
        return running_vms
    
    def _get_mmds_data_for_vm(self, socket_path):
        """Get MMDS data for a specific VM
        
        Args:
            socket_path: Path to VM socket file
            
        Returns:
            dict: MMDS metadata or None if not available
        """
        try:
            temp_api = FirecrackerAPI(socket_path)
            return temp_api.get_mmds_data()
        except Exception:
            pass
        return None