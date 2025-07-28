"""
Firecracker VM Manager Library

This package contains the core modules for managing Firecracker VMs:
- firecracker_api: Core API client for Firecracker HTTP requests
- network_manager: TAP device management and networking
- filesystem_manager: Rootfs building and file management
- config_manager: Environment configuration and VM caching
- vm_discovery: VM discovery and state monitoring
- vm_lifecycle: VM lifecycle operations (create, destroy, start, stop)
"""

__version__ = "1.0.0"
__author__ = "Firecracker VM Manager"

# Import main classes for convenience
from .firecracker_api import FirecrackerAPI
from .network_manager import NetworkManager
from .filesystem_manager import FilesystemManager
from .config_manager import ConfigManager
from .vm_discovery import VMDiscovery
from .vm_lifecycle import VMLifecycle

__all__ = [
    'FirecrackerAPI',
    'NetworkManager', 
    'FilesystemManager',
    'ConfigManager',
    'VMDiscovery',
    'VMLifecycle'
]