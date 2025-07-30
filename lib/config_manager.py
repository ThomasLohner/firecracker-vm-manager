#!/usr/bin/env python3

import json
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