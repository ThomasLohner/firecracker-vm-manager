#!/usr/bin/env python3

import json
import subprocess
import sys
import time
from pathlib import Path


class ConfigManager:
    """Manages environment configuration, VM caching, and metadata parsing"""
    
    def __init__(self, cache_dir=None, config_file=None):
        # Use provided cache_dir or default to /var/lib/firecracker/cache
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path("/var/lib/firecracker/cache")
        
        # Use provided config_file or default to /etc/firecracker.env
        if config_file:
            self.config_file = Path(config_file)
        else:
            self.config_file = Path("/etc/firecracker.env")
        
        # Store base path for standard directory structure
        self.base_path = "/var/lib/firecracker"
        
        # Initialize environment config
        self.env_config = {}
        
        # Track if we've already checked Firecracker binary
        self.firecracker_checked = False
        
        self._ensure_cache_directory()
    
    def load_env_config(self):
        """Load configuration from config file"""
        config = {}
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                # Strip inline comments (everything after #)
                                if '#' in value:
                                    value = value.split('#')[0]
                                config[key.strip()] = value.strip()
            except Exception as e:
                print(f"Warning: Could not read config file {self.config_file}: {e}", file=sys.stderr)
        
        return config
    
    def parse_metadata(self, metadata_arg, tap_ip, vm_ip, hostname=None):
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
    
    def _ensure_cache_directory(self):
        """Create cache directory if it doesn't exist"""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating cache directory: {e}", file=sys.stderr)
            return False
    
    def _get_cache_file_path(self, vm_name):
        """Get the cache file path for a VM"""
        return self.cache_dir / f"{vm_name}.json"
    
    def save_vm_config(self, vm_name, kernel_path, rootfs_path, tap_device, mmds_tap, vm_ip, tap_ip, cpus, memory, hostname, base_image=None, networkdriver="internal"):
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
            "base_image": base_image,
            "networkdriver": networkdriver,
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
    
    def get_all_cached_vms(self):
        """Get list of all cached VM names"""
        if not self.cache_dir.exists():
            return []
        
        cached_vms = []
        for cache_file in self.cache_dir.glob("*.json"):
            vm_name = cache_file.stem  # filename without .json extension
            cached_vms.append(vm_name)
        
        return cached_vms
    
    def setup_environment(self, args):
        """Perform all preflight checks and environment setup
        
        Args:
            args: Command line arguments from argparse
        
        Returns:
            bool: True if setup successful, False otherwise
        """
        # Check Firecracker binary first
        if not self._check_firecracker_binary():
            return False
        
        # Load configuration from config file
        self.env_config = self.load_env_config()
        
        # Set default paths under /var/lib/firecracker if not configured
        if 'KERNEL_PATH' not in self.env_config or not self.env_config['KERNEL_PATH']:
            self.env_config['KERNEL_PATH'] = f"{self.base_path}/kernels"
        if 'IMAGES_PATH' not in self.env_config or not self.env_config['IMAGES_PATH']:
            self.env_config['IMAGES_PATH'] = f"{self.base_path}/images"
        if 'ROOTFS_PATH' not in self.env_config or not self.env_config['ROOTFS_PATH']:
            self.env_config['ROOTFS_PATH'] = f"{self.base_path}/rootfs"
        
        # Set socket path prefix from config if available, default to /var/run/firecracker
        if 'SOCKET_PATH_PREFIX' not in self.env_config or not self.env_config['SOCKET_PATH_PREFIX']:
            self.env_config['SOCKET_PATH_PREFIX'] = '/var/run/firecracker'
        
        # Create all required directories
        if not self._ensure_all_directories():
            return False
        
        # Apply environment config to args (only if not already set)
        self._apply_env_config_to_args(args)
        
        # Set default socket path if not provided (not needed for list, kernels, or images actions)
        if not args.socket and hasattr(args, 'action') and args.action not in ["list", "kernels", "images"]:
            if args.name:
                socket_path_prefix = self.env_config.get('SOCKET_PATH_PREFIX', '/var/run/firecracker')
                args.socket = str(Path(socket_path_prefix) / f"{args.name}.sock")
        
        return True
    
    def _check_firecracker_binary(self):
        """Check if Firecracker binary exists and get its version
        
        Returns:
            bool: True if Firecracker binary exists and is executable, False otherwise
        """
        # Only check once per session
        if self.firecracker_checked:
            return True
            
        firecracker_path = "/usr/sbin/firecracker"
        
        # Check if the binary exists
        if not Path(firecracker_path).exists():
            print(f"Error: Firecracker binary not found at {firecracker_path}", file=sys.stderr)
            print("Please install Firecracker before using this tool.", file=sys.stderr)
            print("Visit: https://github.com/firecracker-microvm/firecracker/releases", file=sys.stderr)
            return False
        
        # Check if it's executable
        if not Path(firecracker_path).is_file():
            print(f"Error: {firecracker_path} is not a regular file", file=sys.stderr)
            return False
        
        # Try to get the version
        try:
            result = subprocess.run(
                [firecracker_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Extract just the version line (first line typically)
                version_lines = result.stdout.strip().split('\n')
                version_output = version_lines[0] if version_lines else ""
                if version_output:
                    print(f"✓ Firecracker binary found: {version_output}")
                else:
                    print(f"✓ Firecracker binary found at {firecracker_path}")
            else:
                # Some versions might not support --version, check with --help
                result = subprocess.run(
                    [firecracker_path, "--help"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print(f"✓ Firecracker binary found at {firecracker_path} (version info not available)")
                else:
                    print(f"Warning: Firecracker binary found but could not verify it's working properly", file=sys.stderr)
                    print(f"Error output: {result.stderr}", file=sys.stderr)
                    # Don't fail here, as the binary might still work
            
            self.firecracker_checked = True
            return True
            
        except subprocess.TimeoutExpired:
            print(f"Warning: Firecracker binary check timed out", file=sys.stderr)
            self.firecracker_checked = True
            return True  # Don't fail on timeout, binary might still work
        except Exception as e:
            print(f"Warning: Could not check Firecracker version: {e}", file=sys.stderr)
            self.firecracker_checked = True
            return True  # Don't fail on version check error
    
    def _ensure_all_directories(self):
        """Create all required directories
        
        Returns:
            bool: True if all directories created successfully, False otherwise
        """
        # Ensure all required directories exist
        required_dirs = [
            self.env_config['KERNEL_PATH'],
            self.env_config['IMAGES_PATH'],
            self.env_config['ROOTFS_PATH'],
            self.env_config.get('SOCKET_PATH_PREFIX', '/var/run/firecracker')
        ]
        
        for dir_path in required_dirs:
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
                # Only print message for socket directory (others are data directories)
                if dir_path == self.env_config.get('SOCKET_PATH_PREFIX'):
                    if not Path(dir_path).exists():
                        print(f"Created socket directory: {dir_path}")
            except Exception as e:
                print(f"Warning: Could not create directory {dir_path}: {e}", file=sys.stderr)
                # Continue anyway, as some operations might still work
        
        return True
    
    def _apply_env_config_to_args(self, args):
        """Apply environment configuration to command line arguments
        
        Args:
            args: Command line arguments from argparse
        """
        # Set kernel from config if not provided via command line
        if not args.kernel and 'KERNEL' in self.env_config and self.env_config['KERNEL']:
            args.kernel = self.env_config['KERNEL']
        
        # Set image from config if not provided via command line  
        if not args.image and 'IMAGE' in self.env_config and self.env_config['IMAGE']:
            args.image = self.env_config['IMAGE']
        
        # Set rootfs size from config if not provided via command line
        if not args.rootfs_size and 'ROOTFS_SIZE' in self.env_config:
            args.rootfs_size = self.env_config['ROOTFS_SIZE']
        
        # Set CPU count from config if available
        if not args.cpus and 'CPUS' in self.env_config:
            try:
                args.cpus = int(self.env_config['CPUS'])
            except ValueError:
                print(f"Warning: Invalid CPUS value in config file: {self.env_config['CPUS']}", file=sys.stderr)
        
        # Set memory from config if available
        if not args.memory and 'MEMORY' in self.env_config:
            try:
                args.memory = int(self.env_config['MEMORY'])
            except ValueError:
                print(f"Warning: Invalid MEMORY value in config file: {self.env_config['MEMORY']}", file=sys.stderr)
    
    def get_env_config(self):
        """Get the loaded environment configuration
        
        Returns:
            dict: Environment configuration dictionary
        """
        return self.env_config
    
    def get_socket_path_prefix(self):
        """Get the socket path prefix from configuration
        
        Returns:
            str: Socket path prefix (default: /var/run/firecracker)
        """
        return self.env_config.get('SOCKET_PATH_PREFIX', '/var/run/firecracker')
    
    def validate_action_parameters(self, action, args):
        """Validate that required parameters are present for the given action
        
        Args:
            action: The action being performed
            args: Command line arguments from argparse
            
        Returns:
            tuple: (bool success, str error_message or None)
        """
        # Check for basic required parameters (except for list, kernels, and images actions)
        if not args.name and action not in ["list", "kernels", "images"]:
            return False, "Error: --name is required for create, destroy, stop, start, and restart actions"
        
        return True, None
    
    def validate_create_parameters(self, args):
        """Validate parameters required for create action
        
        Args:
            args: Command line arguments from argparse
            
        Returns:
            tuple: (bool success, str error_message or None)
        """
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
                env_hints.append("KERNEL=<filename>")
            if 'image' in missing_params:
                env_hints.append("IMAGE=<filename>")
            if 'rootfs-size' in missing_params:
                env_hints.append("ROOTFS_SIZE=<size>")
            if 'cpus' in missing_params:
                env_hints.append("CPUS=<number>")
            if 'memory' in missing_params:
                env_hints.append("MEMORY=<mb>")
            
            if env_hints:
                error_msg += f"\nNote: These can be set in config file: {', '.join(env_hints)}"
            
            return False, error_msg
        
        return True, None
    
    def validate_external_network_parameters(self, args):
        """Validate parameters required for external network driver mode
        
        Args:
            args: Command line arguments from argparse
            
        Returns:
            tuple: (bool success, str error_message or None)
        """
        if args.networkdriver != "external":
            return True, None
            
        external_required = {
            "tap-device": args.tap_device,
            "tap-ip": args.tap_ip,
            "mmds-tap": args.mmds_tap,
            "vm-ip": args.vm_ip
        }
        
        missing_external_params = [param for param, value in external_required.items() if not value]
        
        if missing_external_params:
            error_msg = f"Error: External network mode requires these parameters: {', '.join(['--' + p for p in missing_external_params])}"
            return False, error_msg
        
        return True, None