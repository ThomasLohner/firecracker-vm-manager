#!/usr/bin/env python3

from pathlib import Path
from .firecracker_api import FirecrackerAPI
from .config_manager import ConfigManager
from .network_manager import NetworkManager


class VMDiscovery:
    """Manages VM discovery, state detection, and table formatting"""
    
    def __init__(self, socket_path_prefix='/tmp', config_manager=None):
        self.socket_path_prefix = socket_path_prefix
        self.config_manager = config_manager or ConfigManager()
        self.network_manager = NetworkManager()
    
    def discover_all_vms(self):
        """Discover all VMs (both running and stopped) by scanning cache and socket directories"""
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
                
                all_vms.append({
                    'name': vm_name,
                    'socket_path': socket_path,
                    'config': vm_config,
                    'cached_config': cached_config,
                    'state': 'running' if is_running else 'stopped'
                })
        
        return all_vms
    
    def discover_running_vms(self):
        """Discover running VMs by scanning socket files in socket directory"""
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
        """Get MMDS data for a specific VM"""
        try:
            temp_api = FirecrackerAPI(socket_path)
            return temp_api.get_mmds_data()
        except Exception:
            pass
        return None
    
    def format_vm_table(self, all_vms):
        """Format VM information as a table (both running and stopped)"""
        if not all_vms:
            print("No VMs found.")
            return
        
        # Extract information for table
        table_data = []
        for vm in all_vms:
            vm_name = vm['name']
            state = vm['state']
            config = vm['config']  # May be None for stopped VMs
            cached_config = vm.get('cached_config', {})
            
            # For running VMs, prefer API config; for stopped VMs, use cached config
            if state == 'running' and config:
                # Extract from API configuration
                machine_config = config.get('machine-config', {})
                cpus = machine_config.get('vcpu_count', 'N/A')
                memory = machine_config.get('mem_size_mib', 'N/A')
                
                boot_source = config.get('boot-source', {})
                kernel_path = boot_source.get('kernel_image_path', 'N/A')
                kernel_name = Path(kernel_path).name if kernel_path != 'N/A' else 'N/A'
                
                # Extract drives info (rootfs) - drives is an array
                drives = config.get('drives', [])
                rootfs_filename = 'N/A'
                for drive in drives:
                    if drive.get('drive_id') == 'rootfs' and drive.get('is_root_device', False):
                        rootfs_path = drive.get('path_on_host', 'N/A')
                        rootfs_filename = Path(rootfs_path).name if rootfs_path != 'N/A' else 'N/A'
                        break
                
                # Extract network interfaces - network-interfaces is an array
                network_interfaces = config.get('network-interfaces', [])
                tap_device = 'N/A'
                mmds_tap_device = 'N/A'
                
                for interface in network_interfaces:
                    iface_id = interface.get('iface_id')
                    host_dev_name = interface.get('host_dev_name', 'N/A')
                    
                    if iface_id == 'eth0':
                        tap_device = host_dev_name
                    elif iface_id == 'mmds0':
                        mmds_tap_device = host_dev_name
                
                # Get IP address for main TAP device
                tap_ip = self.network_manager.get_tap_device_ip(tap_device)
                
                # Try to get MMDS data for internal IP
                mmds_data = self._get_mmds_data_for_vm(vm['socket_path'])
                if mmds_data and 'network_config' in mmds_data:
                    internal_ip = mmds_data['network_config'].get('ip', 'N/A')
                else:
                    internal_ip = 'N/A'
                    
            else:
                # Extract from cached configuration for stopped VMs
                cpus = cached_config.get('cpus', 'N/A')
                memory = cached_config.get('memory', 'N/A')
                
                kernel_path = cached_config.get('kernel', 'N/A')
                kernel_name = Path(kernel_path).name if kernel_path != 'N/A' else 'N/A'
                
                rootfs_path = cached_config.get('rootfs', 'N/A')
                rootfs_filename = Path(rootfs_path).name if rootfs_path != 'N/A' else 'N/A'
                
                tap_device = cached_config.get('tap_device', 'N/A')
                mmds_tap_device = cached_config.get('mmds_tap', 'N/A')
                
                # For stopped VMs, we can't get real-time IP info
                tap_ip = 'N/A'
                internal_ip = cached_config.get('vm_ip', 'N/A')
            
            # Get base image from cached configuration (available for both running and stopped)
            base_image = cached_config.get('base_image', 'N/A')
            
            # Format TAP interface info with IP
            tap_info = f"{tap_device}"
            if tap_ip != 'N/A':
                tap_info += f" ({tap_ip})"
            
            # MMDS TAP doesn't need IP since it's always 169.254.169.254
            mmds_tap_info = mmds_tap_device
            
            table_data.append([
                vm_name,
                state,
                internal_ip,
                str(cpus),
                f"{memory} MiB" if memory != 'N/A' else 'N/A',
                rootfs_filename,
                base_image,
                kernel_name,
                tap_info,
                mmds_tap_info
            ])
        
        # Print table header
        headers = ['VM Name', 'State', 'Internal IP', 'CPUs', 'Memory', 'Rootfs', 'Base Image', 'Kernel', 'TAP Interface (IP)', 'MMDS TAP']
        
        # Calculate column widths
        col_widths = [len(header) for header in headers]
        for row in table_data:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Print formatted table
        def print_row(row):
            formatted_cells = []
            for i, cell in enumerate(row):
                formatted_cells.append(str(cell).ljust(col_widths[i]))
            print(' | '.join(formatted_cells))
        
        def print_separator():
            sep_parts = ['-' * width for width in col_widths]
            print('-+-'.join(sep_parts))
        
        print_row(headers)
        print_separator()
        for row in table_data:
            print_row(row)