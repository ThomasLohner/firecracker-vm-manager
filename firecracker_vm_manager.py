#!/usr/bin/env python3

import argparse
import json
import requests
import requests_unixsocket
import subprocess
import sys
import time
from pathlib import Path

def load_env_config():
    """Load configuration from .env file"""
    config = {}
    env_file = Path(".env")
    
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Could not read .env file: {e}", file=sys.stderr)
    
    return config


def parse_metadata(metadata_arg, tap_ip, vm_ip, hostname=None):
    """Parse metadata from command line argument and add network config"""
    metadata = {}
    
    # Parse user-provided metadata
    if metadata_arg:
        if metadata_arg.startswith('@'):
            # Read from file
            file_path = metadata_arg[1:]
            try:
                with open(file_path, 'r') as f:
                    user_metadata = json.load(f)
                metadata.update(user_metadata)
            except FileNotFoundError:
                print(f"Error: Metadata file not found: {file_path}", file=sys.stderr)
                return None
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in metadata file {file_path}: {e}", file=sys.stderr)
                return None
        else:
            # Parse JSON string directly
            try:
                user_metadata = json.loads(metadata_arg)
                metadata.update(user_metadata)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in metadata argument: {e}", file=sys.stderr)
                return None
    
    # Always add network_config object
    metadata['network_config'] = {
            'ip': vm_ip,
            'gateway': tap_ip,
            'hostname': hostname
        }
    
    return metadata


class FirecrackerVMManager:
    def __init__(self, socket_path, socket_path_prefix='/tmp'):
        self.socket_path = socket_path
        self.socket_path_prefix = socket_path_prefix
        self.session = requests_unixsocket.Session()
        self.base_url = f"http+unix://{self.socket_path.replace('/', '%2F')}"
        self.allocated_tap_devices = set()  # Track devices allocated in this session
        self.cache_dir = Path("cache")  # Cache directory for VM configurations
        
        # Ensure cache directory exists
        self._ensure_cache_directory()
    
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
    
    def _setup_device_common(self, device_name, device_type="TAP"):
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
    
    def _validate_file_exists(self, file_path, file_type="file"):
        """Validate that a file exists and return Path object"""
        path = Path(file_path)
        if not path.exists():
            print(f"Error: {file_type} {file_path} does not exist", file=sys.stderr)
            return None
        return path
    
    def _configure_network_interface(self, iface_id, host_dev_name):
        """Helper to configure network interface via API"""
        data = {
            "iface_id": iface_id,
            "host_dev_name": host_dev_name
        }
        return self._make_request("PUT", f"/network-interfaces/{iface_id}", data)

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

    def get_vm_config(self):
        """Get VM configuration from Firecracker API"""
        try:
            response = self.session.get(f"{self.base_url}/vm/config")
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception:
            return None

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
            
            # Create a temporary VM manager for this socket
            temp_manager = FirecrackerVMManager(socket_path, self.socket_path_prefix)
            
            # Try to get VM config
            if temp_manager.check_socket_in_use():
                vm_config = temp_manager.get_vm_config()
                if vm_config:
                    running_vms.append({
                        'name': vm_name,
                        'socket_path': socket_path,
                        'config': vm_config
                    })
        
        return running_vms

    def format_vm_table(self, running_vms):
        """Format running VM information as a table"""
        if not running_vms:
            print("No running VMs found.")
            return
        
        # Extract information for table
        table_data = []
        for vm in running_vms:
            config = vm['config']
            
            # Extract basic info
            vm_name = vm['name']
            
            # Extract machine config
            machine_config = config.get('machine-config', {})
            cpus = machine_config.get('vcpu_count', 'N/A')
            memory = machine_config.get('mem_size_mib', 'N/A')
            
            # Extract boot source info
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
            tap_info = 'N/A'
            mmds_tap_info = 'N/A'
            internal_ip = 'N/A'
            
            # Look for interfaces by iface_id and get their IP addresses
            tap_device = 'N/A'
            mmds_tap_device = 'N/A'
            
            for interface in network_interfaces:
                iface_id = interface.get('iface_id')
                host_dev_name = interface.get('host_dev_name', 'N/A')
                
                if iface_id == 'eth0':
                    tap_device = host_dev_name
                elif iface_id == 'mmds0':
                    mmds_tap_device = host_dev_name
            
            # Get IP address for main TAP device only (MMDS is always 169.254.169.254)
            tap_ip = self.get_tap_device_ip(tap_device)
            
            # Format TAP interface info with IP
            tap_info = f"{tap_device}"
            if tap_ip != 'N/A':
                tap_info += f" ({tap_ip})"
            
            # MMDS TAP doesn't need IP since it's always 169.254.169.254
            mmds_tap_info = mmds_tap_device
            
            # Try to get MMDS data for internal IP
            mmds_data = self._get_mmds_data_for_vm(vm['socket_path'])
            if mmds_data and 'network_config' in mmds_data:
                internal_ip = mmds_data['network_config'].get('ip', 'N/A')
            
            table_data.append([
                vm_name,
                internal_ip,
                str(cpus),
                f"{memory} MiB" if memory != 'N/A' else 'N/A',
                rootfs_filename,
                kernel_name,
                tap_info,
                mmds_tap_info
            ])
        
        # Print table header
        headers = ['VM Name', 'Internal IP', 'CPUs', 'Memory', 'Rootfs', 'Kernel', 'TAP Interface (IP)', 'MMDS TAP']
        
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

    def list_available_kernels(self, kernel_path_env):
        """List available kernel files from KERNEL_PATH directory"""
        if not kernel_path_env:
            print("Error: KERNEL_PATH not set in .env file", file=sys.stderr)
            return False
        
        kernel_dir = Path(kernel_path_env)
        if not kernel_dir.is_dir():
            print(f"Error: KERNEL_PATH '{kernel_path_env}' is not a valid directory", file=sys.stderr)
            return False
            
        try:
            # Look for common kernel file patterns
            kernel_patterns = ['vmlinux*', 'bzImage*', 'kernel*', 'Image*']
            kernel_files = []
            
            for pattern in kernel_patterns:
                kernel_files.extend(kernel_dir.glob(pattern))
            
            # Remove duplicates and sort
            kernel_files = sorted(set(kernel_files), key=lambda x: x.name)
            
            if not kernel_files:
                print(f"No kernel files found in {kernel_dir}")
                print("Looking for files matching: vmlinux*, bzImage*, kernel*, Image*")
                return True
            
            print(f"Available kernels in {kernel_dir}:")
            print()
            
            # Print table header
            print(f"{'Filename':<30} {'Size':<10} {'Modified'}")
            print('-' * 55)
            
            for kernel_file in kernel_files:
                try:
                    stat = kernel_file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    modified = Path(kernel_file).stat().st_mtime
                    from datetime import datetime
                    modified_str = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M')
                    
                    print(f"{kernel_file.name:<30} {size_mb:>6.1f} MB {modified_str}")
                except Exception as e:
                    print(f"{kernel_file.name:<30} {'N/A':<10} {'N/A'}")
            
            print()
            print(f"Usage: ./fcm create --kernel <filename> ...")
            print(f"Example: ./fcm create --kernel {kernel_files[0].name} ...")
            
            return True
            
        except Exception as e:
            print(f"Error accessing kernel directory {kernel_dir}: {e}", file=sys.stderr)
            return False

    def list_available_images(self, images_path_env):
        """List available image files from IMAGES_PATH directory"""
        if not images_path_env:
            print("Error: IMAGES_PATH not set in .env file", file=sys.stderr)
            return False
        
        images_dir = Path(images_path_env)
        if not images_dir.is_dir():
            print(f"Error: IMAGES_PATH '{images_path_env}' is not a valid directory", file=sys.stderr)
            return False
            
        try:
            # Look for common filesystem image patterns
            image_patterns = ['*.ext4', '*.ext3', '*.ext2', '*.img', '*.qcow2', '*.raw']
            image_files = []
            
            for pattern in image_patterns:
                image_files.extend(images_dir.glob(pattern))
            
            # Remove duplicates and sort
            image_files = sorted(set(image_files), key=lambda x: x.name)
            
            if not image_files:
                print(f"No image files found in {images_dir}")
                print("Looking for files matching: *.ext4, *.ext3, *.ext2, *.img, *.qcow2, *.raw")
                return True
            
            print(f"Available images in {images_dir}:")
            print()
            
            # Print table header
            print(f"{'Filename':<30} {'Size':<10} {'Modified'}")
            print('-' * 55)
            
            for image_file in image_files:
                try:
                    stat = image_file.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    modified = Path(image_file).stat().st_mtime
                    from datetime import datetime
                    modified_str = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M')
                    
                    print(f"{image_file.name:<30} {size_mb:>6.1f} MB {modified_str}")
                except Exception as e:
                    print(f"{image_file.name:<30} {'N/A':<10} {'N/A'}")
            
            print()
            print(f"Usage: ./fcm create --image <filename> ...")
            print(f"Example: ./fcm create --image {image_files[0].name} ...")
            
            return True
            
        except Exception as e:
            print(f"Error accessing images directory {images_dir}: {e}", file=sys.stderr)
            return False

    def resolve_kernel_path(self, kernel_filename, kernel_path_env):
        """Resolve kernel filename to full path using KERNEL_PATH directory"""
        if not kernel_filename:
            return None
        
        if not kernel_path_env:
            print("Error: KERNEL_PATH not set in .env file", file=sys.stderr)
            return None
        
        kernel_dir = Path(kernel_path_env)
        
        if not kernel_dir.is_dir():
            print(f"Error: KERNEL_PATH '{kernel_path_env}' is not a valid directory", file=sys.stderr)
            return None
        
        kernel_file = kernel_dir / kernel_filename
        if kernel_file.exists():
            return str(kernel_file)
        else:
            print(f"Error: Kernel file '{kernel_filename}' not found in {kernel_dir}", file=sys.stderr)
            print(f"Use './fcm kernels' to see available kernels")
            return None

    def build_rootfs(self, vm_name, image_filename, images_path_env, rootfs_path_env, rootfs_size, force_overwrite=False):
        """Build rootfs by copying image file and resizing it"""
        print(f"Building rootfs for VM: {vm_name}...")
        
        # Validate IMAGES_PATH
        if not images_path_env:
            print("Error: IMAGES_PATH not set in .env file", file=sys.stderr)
            return None
            
        images_dir = Path(images_path_env)
        if not images_dir.is_dir():
            print(f"Error: IMAGES_PATH '{images_path_env}' is not a valid directory", file=sys.stderr)
            return None
        
        # Validate ROOTFS_PATH
        if not rootfs_path_env:
            print("Error: ROOTFS_PATH not set in .env file", file=sys.stderr)
            return None
            
        rootfs_dir = Path(rootfs_path_env)
        
        # Create rootfs directory if it doesn't exist
        try:
            rootfs_dir.mkdir(parents=True, exist_ok=True)
            print(f"✓ Rootfs directory ready: {rootfs_dir}")
        except Exception as e:
            print(f"Error creating rootfs directory {rootfs_dir}: {e}", file=sys.stderr)
            return None
        
        # Check if image file exists
        image_file = images_dir / image_filename
        if not image_file.exists():
            print(f"Error: Image file '{image_filename}' not found in {images_dir}", file=sys.stderr)
            print(f"Use './fcm images' to see available images")
            return None
        
        # Define destination rootfs file
        rootfs_file = rootfs_dir / f"{vm_name}.ext4"
        
        # Check if rootfs file already exists
        if rootfs_file.exists():
            if not force_overwrite:
                print(f"Error: Rootfs file already exists: {rootfs_file}", file=sys.stderr)
                print(f"A VM with name '{vm_name}' may already have a rootfs file.", file=sys.stderr)
                print(f"Please choose a different VM name, remove the existing file, or use --force-rootfs to overwrite.", file=sys.stderr)
                return None
            else:
                print(f"Warning: Overwriting existing rootfs file: {rootfs_file}")
                print(f"✓ Force overwrite enabled")
        
        try:
            # Copy image file to rootfs location
            print(f"Copying {image_file} -> {rootfs_file}")
            import shutil
            shutil.copy2(image_file, rootfs_file)
            print(f"✓ Image copied to rootfs location")
            
            # Resize the rootfs file
            print(f"Resizing rootfs to {rootfs_size}")
            self._run_command(["resize2fs", str(rootfs_file), rootfs_size])
            print(f"✓ Rootfs resized to {rootfs_size}")
            
            print(f"✓ Rootfs built successfully: {rootfs_file}")
            return str(rootfs_file)
            
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error building rootfs: {e}", file=sys.stderr)
            # Clean up partially created file
            if rootfs_file.exists():
                try:
                    rootfs_file.unlink()
                    print(f"✓ Cleaned up partial rootfs file: {rootfs_file}")
                except Exception:
                    pass
            return None

    def _get_mmds_data_for_vm(self, socket_path):
        """Get MMDS data for a specific VM"""
        try:
            temp_manager = FirecrackerVMManager(socket_path, self.socket_path_prefix)
            response = temp_manager.session.get(f"http+unix://{socket_path.replace('/', '%2F')}/mmds")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None

    def _ensure_cache_directory(self):
        """Create cache directory if it doesn't exist"""
        try:
            self.cache_dir.mkdir(exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating cache directory: {e}", file=sys.stderr)
            return False

    def _get_cache_file_path(self, vm_name):
        """Get the cache file path for a VM"""
        return self.cache_dir / f"{vm_name}.json"

    def save_vm_config(self, vm_name, kernel_path, rootfs_path, tap_device, mmds_tap, vm_ip, tap_ip, cpus, memory, hostname):
        """Save VM configuration to cache file"""
        if not self._ensure_cache_directory():
            return False
        
        cache_data = {
            "kernel": kernel_path,
            "rootfs": rootfs_path,
            "tap_device": tap_device,
            "mmds_tap": mmds_tap,
            "vm_ip": vm_ip,
            "tap_ip": tap_ip,
            "cpus": cpus,
            "memory": memory,
            "hostname": hostname,
            "created_at": time.time()
        }
        
        cache_file = self._get_cache_file_path(vm_name)
        try:
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"✓ VM configuration cached: {cache_file}")
            return True
        except Exception as e:
            print(f"Error saving VM config to cache: {e}", file=sys.stderr)
            return False

    def load_vm_config(self, vm_name):
        """Load VM configuration from cache file"""
        cache_file = self._get_cache_file_path(vm_name)
        
        if not cache_file.exists():
            print(f"Error: No cached configuration found for VM '{vm_name}'", file=sys.stderr)
            print(f"Cache file expected at: {cache_file}", file=sys.stderr)
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            print(f"✓ VM configuration loaded from cache: {cache_file}")
            return cache_data
        except Exception as e:
            print(f"Error loading VM config from cache: {e}", file=sys.stderr)
            return None

    def remove_vm_config_cache(self, vm_name):
        """Remove VM configuration from cache"""
        cache_file = self._get_cache_file_path(vm_name)
        
        try:
            if cache_file.exists():
                cache_file.unlink()
                print(f"✓ VM configuration cache removed: {cache_file}")
            else:
                print(f"✓ VM configuration cache doesn't exist: {cache_file}")
            return True
        except Exception as e:
            print(f"Error removing VM config cache: {e}", file=sys.stderr)
            return False

    def _make_request(self, method, endpoint, data=None):
        """Make HTTP request to Firecracker API"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method == "PUT":
                response = self.session.put(url, json=data)
            elif method == "GET":
                response = self.session.get(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code not in [200, 204]:
                print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
                return False
            return True
        except Exception as e:
            print(f"Request failed: {e}", file=sys.stderr)
            return False

    def check_socket_in_use(self):
        """Check if Firecracker process is listening on socket"""
        try:
            response = self.session.get(f"{self.base_url}/")
            return True  # Socket is in use
        except:
            return False  # Socket is not in use or doesn't exist

    def set_boot_source(self, kernel_path, boot_args="console=ttyS0 reboot=k panic=1 pci=off"):
        """Set the boot source for the VM"""
        kernel_file = self._validate_file_exists(kernel_path, "Kernel file")
        if not kernel_file:
            return False
        
        data = {
            "kernel_image_path": str(kernel_file.absolute()),
            "boot_args": boot_args
        }
        return self._make_request("PUT", "/boot-source", data)

    def set_rootfs(self, rootfs_path):
        """Set the root filesystem drive"""
        rootfs_file = self._validate_file_exists(rootfs_path, "Rootfs file")
        if not rootfs_file:
            return False
        
        data = {
            "drive_id": "rootfs",
            "path_on_host": str(rootfs_file.absolute()),
            "is_root_device": True,
            "is_read_only": False
        }
        return self._make_request("PUT", "/drives/rootfs", data)

    def set_network_interface(self, tap_device):
        """Set network interface configuration"""
        return self._configure_network_interface("eth0", tap_device)

    def set_mmds_network_interface(self, mmds_tap):
        """Set dedicated MMDS network interface configuration"""
        return self._configure_network_interface("mmds0", mmds_tap)

    def set_machine_config(self, vcpu_count, mem_size_mib):
        """Set machine configuration (CPU and memory)"""
        data = {
            "vcpu_count": vcpu_count,
            "mem_size_mib": mem_size_mib
        }
        return self._make_request("PUT", "/machine-config", data)

    def configure_mmds_interface(self, interface_id="mmds0", ipv4_address="169.254.169.254"):
        """Configure MMDS to allow requests from specified network interface"""
        data = {
            "network_interfaces": [interface_id],
            "ipv4_address": ipv4_address
        }
        return self._make_request("PUT", "/mmds/config", data)

    def set_mmds_metadata(self, metadata):
        """Set metadata for the Metadata Service (MMDS)"""
        if not metadata:
            return True  # Skip if no metadata provided
        
        return self._make_request("PUT", "/mmds", metadata)

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

    def create_supervisor_config(self, vm_name, socket_path):
        """Create supervisord configuration for VM"""
        config_content = f"""[program:{vm_name}]
command=/usr/sbin/firecracker --id {vm_name} --api-sock {socket_path}
stdout_logfile=/var/log/{vm_name}.log
stderr_logfile=/var/log/{vm_name}.error.log
autostart=true
"""
        
        config_path = Path(f"/etc/supervisor/conf.d/{vm_name}.conf")
        
        try:
            config_path.write_text(config_content)
            print(f"✓ Supervisor config created: {config_path}")
            return True
        except Exception as e:
            print(f"Error creating supervisor config: {e}", file=sys.stderr)
            return False

    def remove_supervisor_config(self, vm_name):
        """Remove supervisord configuration for VM"""
        config_path = Path(f"/etc/supervisor/conf.d/{vm_name}.conf")
        
        try:
            if config_path.exists():
                config_path.unlink()
                print(f"✓ Supervisor config removed: {config_path}")
            else:
                print(f"✓ Supervisor config doesn't exist: {config_path}")
            return True
        except Exception as e:
            print(f"Error removing supervisor config: {e}", file=sys.stderr)
            return False

    def supervisor_reload(self):
        """Reload supervisor configuration"""
        try:
            self._run_command(["sudo", "supervisorctl", "update"])
            print("✓ Supervisor configuration reloaded")
            return True
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error reloading supervisor: {e}", file=sys.stderr)
            return False

    def start_microvm(self):
        """Start the microVM"""
        data = {
            "action_type": "InstanceStart"
        }
        return self._make_request("PUT", "/actions", data)

    def create_vm(self, vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata=None, mmds_tap=None, foreground=False, hostname=None):
        """Create and start a new VM"""
        print(f"Creating VM: {vm_name}...")
        
        # Check if socket is in use
        if self.check_socket_in_use():
            print(f"Error: Socket {self.socket_path} is already in use", file=sys.stderr)
            return False
        
        # If socket file exists but nothing is listening, delete it
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            print(f"Removing stale socket file: {self.socket_path}")
            socket_file.unlink()
        
        success = False
        if foreground:
            success = self.create_vm_foreground(vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
        else:
            success = self.create_vm_supervisor(vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
        
        # Save VM configuration to cache if creation was successful
        if success:
            if not self.save_vm_config(vm_name, kernel_path, rootfs_path, tap_device, mmds_tap, vm_ip, tap_ip, cpus, memory, hostname or vm_name):
                print("Warning: Failed to save VM configuration to cache", file=sys.stderr)
        
        return success
    
    def create_vm_supervisor(self, vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap):
        """Create VM using supervisor"""
        # Create supervisor config
        if not self.create_supervisor_config(vm_name, self.socket_path):
            return False
        
        # Reload supervisor to start Firecracker
        if not self.supervisor_reload():
            return False
        
        # Wait for Firecracker to be ready with retries
        max_retries = 10
        retry_delay = 1
        
        print("Waiting for Firecracker to start...")
        for attempt in range(max_retries):
            time.sleep(retry_delay)
            
            # Check if socket file exists
            socket_file = Path(self.socket_path)
            if not socket_file.exists():
                print(f"Attempt {attempt + 1}/{max_retries}: Socket file not yet created")
                continue
            
            # Check if Firecracker is listening
            if self.check_socket_in_use():
                print(f"✓ Firecracker is ready (attempt {attempt + 1})")
                break
            else:
                print(f"Attempt {attempt + 1}/{max_retries}: Firecracker not yet listening")
        else:
            print("Error: Firecracker failed to start within timeout period", file=sys.stderr)
            
            # Check supervisor status for debugging
            try:
                result = self._run_command(["sudo", "supervisorctl", "status", vm_name], check=False)
                print(f"Supervisor status: {result.stdout.strip()}", file=sys.stderr)
                if result.stderr.strip():
                    print(f"Supervisor stderr: {result.stderr.strip()}", file=sys.stderr)
            except Exception as e:
                print(f"Could not check supervisor status: {e}", file=sys.stderr)
            
            # Check Firecracker logs for debugging
            log_files = [f"/var/log/{vm_name}.log", f"/var/log/{vm_name}.error.log"]
            for log_file in log_files:
                try:
                    result = self._run_command(["sudo", "tail", "-20", log_file], check=False)
                    if result.returncode == 0 and result.stdout.strip():
                        print(f"\n--- Last 20 lines of {log_file} ---", file=sys.stderr)
                        print(result.stdout, file=sys.stderr)
                    elif result.returncode != 0:
                        print(f"Could not read {log_file}: {result.stderr.strip()}", file=sys.stderr)
                except Exception as e:
                    print(f"Error reading {log_file}: {e}", file=sys.stderr)
            
            # Check if socket directory exists and has proper permissions
            socket_dir = Path(self.socket_path).parent
            print(f"\nSocket debugging:", file=sys.stderr)
            print(f"Expected socket path: {self.socket_path}", file=sys.stderr)
            print(f"Socket directory: {socket_dir}", file=sys.stderr)
            print(f"Socket directory exists: {socket_dir.exists()}", file=sys.stderr)
            
            if socket_dir.exists():
                try:
                    stat_result = self._run_command(["ls", "-la", str(socket_dir)], check=False)
                    print(f"Socket directory contents:\n{stat_result.stdout}", file=sys.stderr)
                except Exception as e:
                    print(f"Could not list socket directory: {e}", file=sys.stderr)
            
            # Check if Firecracker binary exists and is executable
            try:
                firecracker_result = self._run_command(["which", "firecracker"], check=False)
                if firecracker_result.returncode == 0:
                    firecracker_path = firecracker_result.stdout.strip()
                    print(f"Firecracker binary found at: {firecracker_path}", file=sys.stderr)
                    
                    # Check if it's executable
                    exec_result = self._run_command(["test", "-x", firecracker_path], check=False)
                    print(f"Firecracker executable: {exec_result.returncode == 0}", file=sys.stderr)
                else:
                    print("Firecracker binary not found in PATH", file=sys.stderr)
                    
                # Also check the specific path we're using
                specific_path_result = self._run_command(["test", "-x", "/usr/sbin/firecracker"], check=False)
                print(f"/usr/sbin/firecracker exists and is executable: {specific_path_result.returncode == 0}", file=sys.stderr)
                
            except Exception as e:
                print(f"Error checking Firecracker binary: {e}", file=sys.stderr)
            
            return False
        
        # Now configure the VM
        return self.configure_and_start(kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
    
    def create_vm_foreground(self, vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap):
        """Create VM in foreground mode for debugging"""
        import signal
        
        print(f"Starting Firecracker in foreground mode...")
        print(f"Command: /usr/sbin/firecracker --id {vm_name} --api-sock {self.socket_path}")
        
        # Cleanup function for when process terminates
        def cleanup():
            print("\nCleaning up...")
            # Remove TAP device
            self.remove_tap_device(tap_device)
            # Remove MMDS TAP device if it was used
            if mmds_tap:
                self.remove_tap_device(mmds_tap)
            # Remove socket file
            socket_file = Path(self.socket_path)
            if socket_file.exists():
                socket_file.unlink()
                print(f"✓ Socket file removed: {self.socket_path}")
        
        # Setup signal handlers for cleanup
        def signal_handler(signum, frame):
            cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Start Firecracker process
            firecracker_process = subprocess.Popen([
                "/usr/sbin/firecracker",
                "--id", vm_name,
                "--api-sock", self.socket_path
            ])
            
            # Wait a moment for Firecracker to start
            import time
            time.sleep(1)
            
            # Configure the VM
            config_success = self.configure_and_start(kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
            
            if not config_success:
                print("VM configuration failed, terminating Firecracker", file=sys.stderr)
                firecracker_process.terminate()
                cleanup()
                return False
            
            print("\n✓ VM running in foreground mode. Press Ctrl+C to stop and cleanup.")
            
            # Wait for Firecracker process to complete
            firecracker_process.wait()
            
        except KeyboardInterrupt:
            print("\nReceived interrupt signal")
        except Exception as e:
            print(f"Error running Firecracker: {e}", file=sys.stderr)
        finally:
            cleanup()
        
        return True
    
    def destroy_vm(self, vm_name, force_destroy=False):
        """Destroy a VM and clean up all resources including rootfs"""
        print(f"Destroying VM: {vm_name}...")
        
        # 1. Check if VM is running and throw error if so
        if self.check_socket_in_use():
            print(f"Error: VM '{vm_name}' is currently running. Please stop the VM first using:", file=sys.stderr)
            print(f"  ./fcm stop --name {vm_name}", file=sys.stderr)
            return False
        
        # 2. Load VM config from cache to get TAP devices and rootfs path
        cache_data = self.load_vm_config(vm_name)
        if not cache_data:
            print(f"Error: Cannot destroy VM '{vm_name}' - no cached configuration found", file=sys.stderr)
            print("This VM may have been created with an older version or the cache was deleted", file=sys.stderr)
            return False
        
        # Extract configuration from cache
        tap_device = cache_data.get('tap_device')
        mmds_tap = cache_data.get('mmds_tap')
        rootfs_path = cache_data.get('rootfs')
        
        # 3. Ask for confirmation unless force_destroy is specified
        if not force_destroy:
            print(f"\n⚠️  WARNING: This will permanently delete:")
            if rootfs_path:
                print(f"   - VM rootfs file: {rootfs_path}")
            if tap_device:
                print(f"   - TAP device: {tap_device}")
            if mmds_tap:
                print(f"   - MMDS TAP device: {mmds_tap}")
            print(f"   - Supervisor configuration for '{vm_name}'")
            print(f"   - VM configuration cache")
            
            while True:
                response = input(f"\nAre you sure you want to destroy VM '{vm_name}'? (yes/no): ").strip().lower()
                if response in ['yes', 'y']:
                    break
                elif response in ['no', 'n']:
                    print("VM destruction cancelled.")
                    return False
                else:
                    print("Please enter 'yes' or 'no'")
        
        # 4. Remove socket file if it exists
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            socket_file.unlink()
            print(f"✓ Socket file removed: {self.socket_path}")
        
        # 5. Remove TAP devices using cached config
        if tap_device:
            if not self.remove_tap_device(tap_device):
                print(f"Warning: Failed to remove TAP device {tap_device}", file=sys.stderr)
        else:
            print("✓ No main TAP device found in cache")
        
        if mmds_tap:
            if not self.remove_tap_device(mmds_tap):
                print(f"Warning: Failed to remove MMDS TAP device {mmds_tap}", file=sys.stderr)
        else:
            print("✓ No MMDS TAP device found in cache")
        
        # 6. Delete rootfs file using cached config
        if rootfs_path:
            rootfs_file = Path(rootfs_path)
            if rootfs_file.exists():
                try:
                    rootfs_file.unlink()
                    print(f"✓ Rootfs file deleted: {rootfs_path}")
                except Exception as e:
                    print(f"Error: Failed to delete rootfs file {rootfs_path}: {e}", file=sys.stderr)
                    return False
            else:
                print(f"✓ Rootfs file doesn't exist: {rootfs_path}")
        else:
            print("✓ No rootfs path found in cache")
        
        # 7. Delete supervisor config
        if not self.remove_supervisor_config(vm_name):
            return False
        
        # Reload supervisor
        if not self.supervisor_reload():
            return False
        
        # 8. Remove VM configuration cache
        if not self.remove_vm_config_cache(vm_name):
            print(f"Warning: Failed to remove configuration cache for VM {vm_name}", file=sys.stderr)
        
        print(f"✓ VM '{vm_name}' destroyed successfully!")
        return True

    def stop_vm(self, vm_name):
        """Stop a VM without removing TAP devices"""
        print(f"Stopping VM: {vm_name}...")
        
        try:
            # Stop the VM via supervisor
            result = self._run_command(["sudo", "supervisorctl", "stop", vm_name], check=False)
            
            if result.returncode == 0:
                print(f"✓ VM {vm_name} stopped successfully")
                
                # Remove socket file to allow clean restart
                socket_file = Path(self.socket_path)
                if socket_file.exists():
                    socket_file.unlink()
                    print(f"✓ Socket file removed: {self.socket_path}")
                else:
                    print(f"✓ Socket file doesn't exist: {self.socket_path}")
                
                return True
            else:
                print(f"Error: Failed to stop VM {vm_name}", file=sys.stderr)
                print(f"supervisorctl output: {result.stderr}", file=sys.stderr)
                return False
                
        except Exception as e:
            print(f"Error stopping VM: {e}", file=sys.stderr)
            return False

    def start_vm(self, vm_name):
        """Start a VM from cached configuration"""
        print(f"Starting VM: {vm_name}...")
        
        # Load VM configuration from cache
        cache_data = self.load_vm_config(vm_name)
        if not cache_data:
            return False
        
        # Extract configuration values
        kernel_path = cache_data.get('kernel')
        rootfs_path = cache_data.get('rootfs')
        tap_device = cache_data.get('tap_device')
        mmds_tap = cache_data.get('mmds_tap')
        vm_ip = cache_data.get('vm_ip')
        tap_ip = cache_data.get('tap_ip')
        cpus = cache_data.get('cpus')
        memory = cache_data.get('memory')
        hostname = cache_data.get('hostname', vm_name)
        
        # Validate that all required values are present
        required_fields = ['kernel', 'rootfs', 'tap_device', 'mmds_tap', 'vm_ip', 'tap_ip', 'cpus', 'memory']
        missing_fields = [field for field in required_fields if not cache_data.get(field)]
        
        if missing_fields:
            print(f"Error: Missing required fields in cached config: {', '.join(missing_fields)}", file=sys.stderr)
            return False
        
        # Check if socket is in use
        if self.check_socket_in_use():
            print(f"Error: Socket {self.socket_path} is already in use", file=sys.stderr)
            return False
        
        # If socket file exists but nothing is listening, delete it
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            print(f"Removing stale socket file: {self.socket_path}")
            socket_file.unlink()
        
        # Start Firecracker process via supervisor
        try:
            result = self._run_command(["sudo", "supervisorctl", "start", vm_name], check=False)
            
            if result.returncode != 0:
                print(f"Error: Failed to start Firecracker process for VM {vm_name}", file=sys.stderr)
                print(f"supervisorctl output: {result.stderr}", file=sys.stderr)
                return False
            
            print(f"✓ Firecracker process started for VM {vm_name}")
            
        except Exception as e:
            print(f"Error starting Firecracker process: {e}", file=sys.stderr)
            return False
        
        # Wait a moment for Firecracker to start
        time.sleep(1)
        
        # Create metadata for MMDS
        metadata = parse_metadata(None, tap_ip, vm_ip, hostname)
        if metadata is None:
            print("Error: Failed to create metadata for MMDS", file=sys.stderr)
            return False
        
        # Configure the VM using cached settings
        success = self.configure_and_start(kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
        
        if success:
            print(f"✓ VM {vm_name} started successfully from cached configuration!")
        else:
            print(f"Error: Failed to configure and start VM {vm_name}", file=sys.stderr)
        
        return success

    def restart_vm(self, vm_name):
        """Restart a VM by stopping and then starting it"""
        print(f"Restarting VM: {vm_name}...")
        
        # First stop the VM
        print("Step 1: Stopping VM...")
        if not self.stop_vm(vm_name):
            print(f"Error: Failed to stop VM {vm_name}", file=sys.stderr)
            return False
        
        # Wait a moment between stop and start
        time.sleep(1)
        
        # Then start the VM
        print("Step 2: Starting VM...")
        if not self.start_vm(vm_name):
            print(f"Error: Failed to start VM {vm_name}", file=sys.stderr)
            return False
        
        print(f"✓ VM {vm_name} restarted successfully!")
        return True

    def configure_and_start(self, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap):
        """Configure all VM settings and start the microVM"""
        print("Configuring Firecracker VM...")
        
        # Set machine configuration
        if not self.set_machine_config(cpus, memory):
            print("Failed to set machine configuration", file=sys.stderr)
            return False
        print(f"✓ Machine config set: {cpus} vCPUs, {memory} MiB RAM")

        # Set boot source
        if not self.set_boot_source(kernel_path):
            print("Failed to set boot source", file=sys.stderr)
            return False
        print(f"✓ Boot source set: {kernel_path}")

        # Set rootfs
        if not self.set_rootfs(rootfs_path):
            print("Failed to set rootfs", file=sys.stderr)
            return False
        print(f"✓ Rootfs set: {rootfs_path}")

        # Setup TAP device and networking
        if not self.setup_tap_device(tap_device, tap_ip, vm_ip):
            print("Failed to setup TAP device", file=sys.stderr)
            return False

        # Set primary network interface (eth0)
        if not self.set_network_interface(tap_device):
            print("Failed to set network interface", file=sys.stderr)
            return False
        print(f"✓ Primary network interface set: eth0 -> {tap_device}")

        # Configure MMDS if metadata provided
        if metadata and mmds_tap:
            # Setup dedicated MMDS TAP device
            if not self.setup_mmds_tap_device(mmds_tap):
                print("Failed to setup MMDS TAP device", file=sys.stderr)
                return False
            
            # Set dedicated MMDS network interface (mmds0)
            if not self.set_mmds_network_interface(mmds_tap):
                print("Failed to set MMDS network interface", file=sys.stderr)
                return False
            print(f"✓ MMDS network interface set: mmds0 -> {mmds_tap}")
            
            # Configure which interface can access MMDS
            if not self.configure_mmds_interface("mmds0"):
                print("Failed to configure MMDS interface", file=sys.stderr)
                return False
            print("✓ MMDS interface configured")
            # Set the metadata
            if not self.set_mmds_metadata(metadata):
                print("Failed to set MMDS metadata", file=sys.stderr)
                return False
            print("✓ MMDS metadata configured")

        # Start the VM
        if not self.start_microvm():
            print("Failed to start microVM", file=sys.stderr)
            return False
        print("✓ MicroVM started successfully!")
        
        return True


def show_help_and_exit():
    """Show help message with examples and exit"""
    help_text = """
Firecracker VM Manager - Create and destroy Firecracker VMs

USAGE:
    firecracker_vm_manager.py ACTION --name VM_NAME [OPTIONS]

ACTIONS:
    create          Create and start a new VM (builds rootfs from image)
    destroy         Destroy an existing VM and clean up resources
    stop            Stop a VM without removing TAP devices
    start           Start a previously created VM from cached configuration
    restart         Restart a VM by stopping and then starting it
    list            List all running VMs with their configuration
    kernels         List available kernel files from KERNEL_PATH directory
    images          List available image files from IMAGES_PATH directory

REQUIRED PARAMETERS:
    --name          Name of the VM (not required for list, kernels, and images actions)

OPTIONAL PARAMETERS:
    --socket        Path to Firecracker API socket file (default: /tmp/<vm_name>.sock)

REQUIRED FOR CREATE ACTION:
    --kernel        Kernel filename (must exist in KERNEL_PATH directory)
    --image         Image filename (must exist in IMAGES_PATH directory)
    --rootfs-size   Size to resize rootfs to (e.g., 1G, 512M, 2048M)
    --tap-ip        IP address for TAP device on host
    --vm-ip         IP address for VM (guest)

OPTIONAL FOR CREATE ACTION:
    --tap-device    TAP device name on host (auto-generated if not specified)
    --mmds-tap      MMDS TAP device name (auto-generated if not specified)

OPTIONAL FOR DESTROY ACTION:
    --tap-device    TAP device name to remove (required if not using auto-discovery)
    --mmds-tap      MMDS TAP device name to remove (required if VM was created with metadata)

OPTIONAL PARAMETERS (CREATE ONLY):
    --cpus          Number of vCPUs (can be set in .env as CPUS)
    --memory        Memory in MiB (can be set in .env as MEMORY)
    --hostname      Hostname for the VM (defaults to VM name if not specified)
    --foreground    Run Firecracker in foreground for debugging (skips supervisor)
    --force-rootfs  Force overwrite existing rootfs file if it exists
    --help, -h      Show this help message

EXAMPLE USAGE:
    # List available images and kernels
    ./firecracker_vm_manager.py images
    ./firecracker_vm_manager.py kernels

    # Create a VM with auto-generated TAP device (simplest form)
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with specific TAP device
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-device tap5 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with metadata (MMDS TAP auto-generated)
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --metadata '{"app":"web"}'

    # Create a VM with custom resources and specific devices
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 2G --tap-device tap0 --mmds-tap tap1 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --cpus 2 --memory 512

    # Create a VM in foreground mode for debugging
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --foreground

    # Force overwrite existing rootfs file
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --force-rootfs

    # Destroy a VM (with auto-cleanup warning)
    ./firecracker_vm_manager.py destroy --name myvm
    
    # Destroy a VM with specific device cleanup
    ./firecracker_vm_manager.py destroy --name myvm --tap-device tap0 --mmds-tap tap1

    # Stop a VM without removing TAP devices
    ./firecracker_vm_manager.py stop --name myvm

    # Start a previously created VM from cached configuration
    ./firecracker_vm_manager.py start --name myvm

    # Restart a VM (stop then start)
    ./firecracker_vm_manager.py restart --name myvm

    # List all running VMs
    ./firecracker_vm_manager.py list

PREREQUISITES:
    - Root/sudo access for network configuration and supervisor management
    - Supervisor daemon running
    - resize2fs utility for rootfs resizing
    - Python dependencies: pip install requests requests-unixsocket
"""
    print(help_text)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Manage Firecracker VMs", add_help=False)
    parser.add_argument("action", nargs="?", choices=["create", "destroy", "stop", "start", "restart", "list", "kernels", "images"], help="Action to perform")
    parser.add_argument("--name", help="Name of the VM")
    parser.add_argument("--socket", help="Path to Firecracker API socket (default: /tmp/<vm_name>.sock)")
    parser.add_argument("--kernel", help="Kernel filename (must exist in KERNEL_PATH directory)")
    parser.add_argument("--image", help="Image filename (must exist in IMAGES_PATH directory, can be set in .env as IMAGE)")
    parser.add_argument("--rootfs-size", help="Size to resize rootfs to (can be set in .env as ROOTFS_SIZE)")
    parser.add_argument("--cpus", type=int, help="Number of vCPUs (can be set in .env as CPUS)")
    parser.add_argument("--memory", type=int, help="Memory in MiB (can be set in .env as MEMORY)")
    parser.add_argument("--tap-device", help="TAP device name on host")
    parser.add_argument("--tap-ip", help="IP address for TAP device on host")
    parser.add_argument("--vm-ip", help="IP address for VM (guest)")
    parser.add_argument("--metadata", help="JSON metadata for MMDS (provide JSON string or file path starting with @)")
    parser.add_argument("--mmds-tap", help="TAP device name for MMDS interface (enables MMDS with network config)")
    parser.add_argument("--hostname", help="Hostname for the VM (defaults to VM name if not specified)")
    parser.add_argument("--foreground", action="store_true", help="Run Firecracker in foreground for debugging")
    parser.add_argument("--force-rootfs", action="store_true", help="Force overwrite existing rootfs file if it exists")
    parser.add_argument("--force-destroy", action="store_true", help="Force destroy without confirmation prompt")
    parser.add_argument("--help", "-h", action="store_true", help="Show help message")

    args = parser.parse_args()

    # Show help if requested or no action specified
    if args.help or not args.action:
        show_help_and_exit()

    # Load configuration from .env file
    env_config = load_env_config()

    # Check for basic required parameters (except for list, kernels, and images actions)
    if not args.name and args.action not in ["list", "kernels", "images"]:
        print("Error: --name is required for create, destroy, stop, start, and restart actions", file=sys.stderr)
        show_help_and_exit()
    
    # Set socket path prefix from .env if available, default to /tmp
    socket_path_prefix = env_config.get('SOCKET_PATH_PREFIX', '/tmp')
    
    # Create socket directory if it doesn't exist
    socket_dir = Path(socket_path_prefix)
    if not socket_dir.exists():
        try:
            socket_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created socket directory: {socket_path_prefix}")
        except Exception as e:
            print(f"Warning: Could not create socket directory {socket_path_prefix}: {e}", file=sys.stderr)
    
    # Set default socket path if not provided (not needed for list, kernels, or images actions)
    if not args.socket and args.action not in ["list", "kernels", "images"]:
        args.socket = str(Path(socket_path_prefix) / f"{args.name}.sock")
    
    # Set kernel path from .env if not provided via command line
    if not args.kernel and 'KERNEL_PATH' in env_config:
        args.kernel = env_config['KERNEL_PATH']
    
    # Set image from .env if not provided via command line
    if not args.image and 'IMAGE' in env_config and env_config['IMAGE']:
        args.image = env_config['IMAGE']
    
    # Set rootfs size from .env if not provided via command line
    if not args.rootfs_size and 'ROOTFS_SIZE' in env_config:
        args.rootfs_size = env_config['ROOTFS_SIZE']
    
    # Set CPU count from .env if available
    if not args.cpus and 'CPUS' in env_config:
        try:
            args.cpus = int(env_config['CPUS'])
        except ValueError:
            print(f"Warning: Invalid CPUS value in .env file: {env_config['CPUS']}", file=sys.stderr)
    
    # Set memory from .env if available
    if not args.memory and 'MEMORY' in env_config:
        try:
            args.memory = int(env_config['MEMORY'])
        except ValueError:
            print(f"Warning: Invalid MEMORY value in .env file: {env_config['MEMORY']}", file=sys.stderr)
    
    # Create VM manager (use dummy socket path for list, kernels, and images actions)
    socket_path = args.socket if args.socket else str(Path(socket_path_prefix) / "dummy.sock")
    vm_manager = FirecrackerVMManager(socket_path, socket_path_prefix)

    if args.action == "kernels":
        # List available kernels
        success = vm_manager.list_available_kernels(env_config.get('KERNEL_PATH'))
        if not success:
            sys.exit(1)
        return

    elif args.action == "images":
        # List available images
        success = vm_manager.list_available_images(env_config.get('IMAGES_PATH'))
        if not success:
            sys.exit(1)
        return

    elif args.action == "create":
        # Check for create-specific required parameters
        create_required = {
            "kernel": args.kernel,
            "image": args.image,
            "rootfs-size": args.rootfs_size,
            "tap-ip": args.tap_ip,
            "vm-ip": args.vm_ip,
            "cpus": args.cpus,
            "memory": args.memory
        }
        
        missing_params = [param for param, value in create_required.items() if not value]
        
        if missing_params:
            error_msg = f"Error: Missing required parameter(s) for create action: {', '.join(['--' + p for p in missing_params])}"
            env_hints = []
            if 'kernel' in missing_params:
                env_hints.append("KERNEL_PATH=<path>")
            if 'image' in missing_params:
                env_hints.append("IMAGE=<filename>")
            if 'rootfs-size' in missing_params:
                env_hints.append("ROOTFS_SIZE=<size>")
            if 'cpus' in missing_params:
                env_hints.append("CPUS=<number>")
            if 'memory' in missing_params:
                env_hints.append("MEMORY=<mb>")
            
            if env_hints:
                error_msg += f"\nNote: These can be set in .env file: {', '.join(env_hints)}"
            
            print(error_msg, file=sys.stderr)
            show_help_and_exit()

        # Resolve kernel path (support both filenames and full paths)
        resolved_kernel_path = vm_manager.resolve_kernel_path(args.kernel, env_config.get('KERNEL_PATH'))
        if not resolved_kernel_path:
            sys.exit(1)  # Error message already printed by resolve_kernel_path

        # Build rootfs from image
        rootfs_path = vm_manager.build_rootfs(
            vm_name=args.name,
            image_filename=args.image,
            images_path_env=env_config.get('IMAGES_PATH'),
            rootfs_path_env=env_config.get('ROOTFS_PATH'),
            rootfs_size=args.rootfs_size,
            force_overwrite=args.force_rootfs
        )
        if not rootfs_path:
            sys.exit(1)  # Error message already printed by build_rootfs

        # Auto-generate TAP device name if not specified
        if not args.tap_device:
            args.tap_device = vm_manager.find_next_available_tap_device()
            print(f"Auto-generated TAP device: {args.tap_device}")
        else:
            # Validate explicitly provided TAP device
            if not vm_manager.validate_tap_device_available(args.tap_device):
                print(f"Error: TAP device '{args.tap_device}' already exists on the system", file=sys.stderr)
                sys.exit(1)
            # Mark explicitly provided device as allocated to prevent conflicts
            vm_manager.allocated_tap_devices.add(args.tap_device)

        # Auto-generate MMDS TAP device name if not specified (always needed for network_config)
        if not args.mmds_tap:
            args.mmds_tap = vm_manager.find_next_available_tap_device()
            print(f"Auto-generated MMDS TAP device: {args.mmds_tap}")
        else:
            # Validate explicitly provided MMDS TAP device
            if not vm_manager.validate_tap_device_available(args.mmds_tap):
                print(f"Error: MMDS TAP device '{args.mmds_tap}' already exists on the system", file=sys.stderr)
                sys.exit(1)
            # Mark explicitly provided device as allocated to prevent conflicts
            vm_manager.allocated_tap_devices.add(args.mmds_tap)

        # Set hostname to VM name if not specified
        hostname = args.hostname if args.hostname else args.name
        
        # Parse metadata (always include network_config since we always have MMDS TAP)
        # When MMDS TAP is available, always create metadata (at minimum with network_config)
        metadata = parse_metadata(args.metadata, args.tap_ip, args.vm_ip, hostname)
        if metadata is None:
            sys.exit(1)  # Error message already printed by parse_metadata

        success = vm_manager.create_vm(
            vm_name=args.name,
            kernel_path=resolved_kernel_path,
            rootfs_path=rootfs_path,
            tap_device=args.tap_device,
            tap_ip=args.tap_ip,
            vm_ip=args.vm_ip,
            cpus=args.cpus,
            memory=args.memory,
            metadata=metadata,
            mmds_tap=args.mmds_tap,
            foreground=args.foreground,
            hostname=hostname
        )

    elif args.action == "destroy":
        # Destroy action will load TAP devices and rootfs path from cache
        success = vm_manager.destroy_vm(
            vm_name=args.name,
            force_destroy=args.force_destroy
        )

    elif args.action == "stop":
        # Stop a VM without removing TAP devices
        success = vm_manager.stop_vm(vm_name=args.name)

    elif args.action == "start":
        # Start a VM from cached configuration
        success = vm_manager.start_vm(vm_name=args.name)

    elif args.action == "restart":
        # Restart a VM (stop then start)
        success = vm_manager.restart_vm(vm_name=args.name)

    elif args.action == "list":
        # List running VMs
        running_vms = vm_manager.discover_running_vms()
        vm_manager.format_vm_table(running_vms)
        return  # No need to check success for list action

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()