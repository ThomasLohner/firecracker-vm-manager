# Firecracker VM Manager (fcm) - Development Context

## Executive Summary

**Project**: Firecracker VM Manager - Python script with bash wrapper (`fcm`) for complete microVM lifecycle management  
**Status**: Production-ready with image-based rootfs building, TAP auto-generation, VM caching, and comprehensive monitoring  
**Current Version**: Full lifecycle support (create, stop, start, restart, destroy, list) with zero-configuration setup

### Current Capabilities
- **Zero-Setup**: `fcm` wrapper auto-manages Python environment and dependencies
- **Image-Based VMs**: Build VM-specific rootfs from base images with customizable sizes  
- **Complete Lifecycle**: Create, stop, start, restart, destroy, and list VMs
- **Auto-Configuration**: TAP device auto-generation, VM caching, supervisor integration
- **Production Ready**: Configurable paths, comprehensive error handling, safety features

### Recent Major Features
- Image-based rootfs building from base images with `resize2fs`
- VM configuration caching system enabling stop/start without losing settings
- TAP device auto-generation with conflict prevention
- Comprehensive VM discovery (running + stopped) with state monitoring
- Enhanced destroy action with confirmation prompts and cache-based cleanup
- Base image tracking for VM provenance
- External network driver support for using existing TAP devices

## Essential Documentation Links

**CRITICAL**: Access these Firecracker sources for API changes:
- **Getting Started**: https://raw.githubusercontent.com/firecracker-microvm/firecracker/refs/heads/main/docs/getting-started.md
- **API Swagger**: https://raw.githubusercontent.com/firecracker-microvm/firecracker/refs/heads/main/src/firecracker/swagger/firecracker.yaml
- **Network Setup**: https://raw.githubusercontent.com/firecracker-microvm/firecracker/refs/heads/main/docs/network-setup.md
- **Main Repository**: https://github.com/firecracker-microvm/firecracker

**Documentation Updates**: Update `firecracker_vm_manager.md` for user docs, `CLAUDE.md` for development context.

## Project Architecture

### Key Files
| File | Purpose |
|------|---------|
| `fcm.sh` | Development bash wrapper with auto Python environment setup |
| `firecracker_vm_manager.py` | Main CLI interface and module integration |
| `lib/` | Modular implementation directory |
| `lib/__init__.py` | Package interface with exported classes |
| `lib/firecracker_api.py` | Core Firecracker API client |
| `lib/network_manager.py` | TAP device management and networking |
| `lib/filesystem_manager.py` | Rootfs building and file operations |
| `lib/config_manager.py` | Environment config and VM caching |
| `lib/vm_discovery.py` | VM discovery and state monitoring |
| `lib/vm_lifecycle.py` | VM lifecycle operations |
| `.env` | Configuration file with directory paths and defaults |
| `firecracker_vm_manager.md` | User documentation |

### Modular Architecture Overview
The system follows a strict separation between business logic (modules) and presentation (main script):

**Business Logic Modules (lib/):**
- **API Layer**: `FirecrackerAPI` handles all HTTP communication with Firecracker
- **Network Layer**: `NetworkManager` manages TAP devices, IP configuration, routing, device allocation
- **Storage Layer**: `FilesystemManager` handles rootfs building, image/kernel management, returns raw data
- **Configuration Layer**: `ConfigManager` manages environment config, VM caching, metadata, preflight checks, parameter validation, socket paths
- **Discovery Layer**: `VMDiscovery` handles VM state detection and monitoring, returns raw VM data
- **Lifecycle Layer**: `VMLifecycle` orchestrates VM create/destroy/start/stop operations, contains ALL creation logic

**Presentation Layer (main script):**
- **Pure Orchestrator**: No business logic, only dispatches to modules
- **Formatting Functions**: `format_kernels_table()`, `format_images_table()`, `format_vms_table()` for CLI display
- **Action Routing**: Each action has dedicated elif block for clarity
- **Minimal Logic**: Only parses args and delegates to appropriate modules

### Core Operations
| Action | Module | Function | Description |
|--------|--------|----------|-------------|
| `create` | `VMLifecycle` | `create_vm()` | Build rootfs from image, configure, start VM |
| `destroy` | `VMLifecycle` | `destroy_vm()` | Stop VM, confirm, cleanup all resources |
| `stop` | `VMLifecycle` | `stop_vm()` | Stop VM, preserve TAP devices and cache |
| `start` | `VMLifecycle` | `start_vm()` | Restart VM from cached configuration |
| `restart` | `VMLifecycle` | `restart_vm()` | Stop + start sequence |
| `list` | `VMDiscovery` | `discover_all_vms()` | Returns raw VM data (main formats with `format_vms_table()`) |
| `images` | `FilesystemManager` | `get_available_images()` | Returns image list (main formats with `format_images_table()`) |
| `kernels` | `FilesystemManager` | `get_available_kernels()` | Returns kernel list (main formats with `format_kernels_table()`) |

### Module Dependencies and Integration
```
firecracker_vm_manager.py (CLI - Pure Orchestrator)
├── Creates ConfigManager for all operations
├── For kernels/images: Creates FilesystemManager, gets data, formats output
├── For list: Creates VMDiscovery, gets data, formats output  
└── For VM operations: Creates VMLifecycle(vm_name, config_manager)
    └── VMLifecycle internally creates:
        ├── FirecrackerAPI(socket_path)
        ├── NetworkManager()
        └── FilesystemManager(config_manager)

Module Ownership:
- ConfigManager: Shared, created by main and passed where needed
- VMLifecycle: Self-contained, creates all managers it needs
- VMDiscovery: Uses ConfigManager for paths and cache
- FilesystemManager: Uses ConfigManager for all paths
- NetworkManager: Standalone, maintains session state
```

### Modular Design Benefits
- **Single Responsibility**: Each module has one focused purpose
- **Testability**: Individual components can be unit tested independently
- **Maintainability**: Changes to networking don't affect filesystem operations
- **Reusability**: Components can be used independently or in other projects (e.g., REST APIs)
- **Clean Organization**: Implementation details organized in `lib/` subdirectory
- **Debugging**: Easier to isolate issues to specific functional areas
- **Presentation Separation**: Modules return raw data, formatting handled by presentation layer

### Key Architecture Components

#### ConfigManager Responsibilities
- **Preflight Checks**: Validates Firecracker binary exists (silently)
- **Directory Management**: Creates all required directories recursively
- **Environment Setup**: Loads config file, applies defaults, validates parameters
- **Parameter Validation**: Validates action parameters, create parameters, network parameters
- **Path Management**: Provides paths via `get_env_config()`, `get_socket_path_prefix()`, `get_vm_socket_path()`
- **Socket Management**: Builds full socket paths for VMs from names
- **VM Configuration Caching**: 
  - Auto-creates `/var/lib/firecracker/cache/` directory for VM configurations
  - JSON storage: `/var/lib/firecracker/cache/<vm_name>.json` with complete VM state
  - Enables stop/start workflow without losing configuration
  - Stores: kernel, rootfs, TAP devices, IPs, CPU/memory, hostname, base_image, networkdriver, timestamp

#### Image-Based Rootfs Building
- Base images in IMAGES_PATH serve as templates
- VM-specific rootfs: `<ROOTFS_PATH>/<vm_name>.ext4`
- Automatic copying and `resize2fs` resizing
- Force overwrite protection with `--force-rootfs` override
- Supports: ext4, ext3, ext2, img, qcow2, raw formats

#### TAP Device Management (NetworkManager)
- **Unified Allocation**: Single `allocate_tap_device()` method handles both auto-generation and validation
- **Internal Mode (default)**: 
  - Auto-generation with system scan via `ip link show`
  - Sequential naming: tap0, tap1, tap2, etc.
  - Session tracking prevents conflicts via `allocated_tap_devices` set
  - Auto-generates both main and MMDS TAP devices
  - Validates explicitly specified devices don't exist
- **External Mode**: 
  - Uses existing TAP devices without creating/removing them
  - Validates TAP devices exist, have correct IPs, and routes are configured
  - `validate_external_network_setup()` ensures complete network configuration

#### VM Discovery and Monitoring
- Scans cache directory and socket files
- State detection: running (API responsive) vs stopped
- Mixed data sources: API for running VMs, cache for stopped
- Returns raw VM data for presentation layer formatting

### Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `KERNEL_PATH` | Kernel files directory | `/var/lib/firecracker/kernels` |
| `KERNEL` | Default kernel filename | Optional |
| `IMAGES_PATH` | Base image files | `/var/lib/firecracker/images` |
| `ROOTFS_PATH` | VM-specific rootfs files | `/var/lib/firecracker/rootfs` |
| `SOCKET_PATH_PREFIX` | Socket file directory | `/var/run/firecracker` |
| `CPUS` | Default vCPUs | Required |
| `MEMORY` | Default memory (MiB) | Required |
| `IMAGE` | Default image file | Optional |
| `ROOTFS_SIZE` | Default rootfs size | Optional |

**Note**: Cache directory is automatically set to `/var/lib/firecracker/cache` and is not configurable via environment variables.

**Directory Auto-Creation**: All required directories (`/var/lib/firecracker/kernels`, `/var/lib/firecracker/images`, `/var/lib/firecracker/rootfs`, `/var/lib/firecracker/cache`) are automatically created if they don't exist. Requires appropriate filesystem permissions.

## Configuration Management

### Configuration File Structure
The configuration file (default: `/etc/firecracker.env`) provides default configuration values. All settings can be overridden by command-line arguments. The config file location can be overridden with `--config` parameter.

```bash
# Firecracker VM Manager Configuration
# Command line arguments will override these values.

# Path to the kernel image files directory
# Default: /var/lib/firecracker/kernels (if not specified)
KERNEL_PATH=/var/lib/firecracker/kernels

# Default kernel filename (can be overridden with --kernel)
KERNEL=

# Path to image files directory (images are copied to create rootfs)
# Default: /var/lib/firecracker/images (if not specified)
IMAGES_PATH=/var/lib/firecracker/images

# Path to rootfs files directory (where built rootfs files are stored)
# Default: /var/lib/firecracker/rootfs (if not specified)
ROOTFS_PATH=/var/lib/firecracker/rootfs

# VM configuration cache directory is automatically set to:
# /var/lib/firecracker/cache (not configurable via config file)

# Default image file name (can be overridden with --image)
IMAGE=

# Default rootfs size (can be overridden with --rootfs-size)
ROOTFS_SIZE=1G

# Configure custom socket directory
SOCKET_PATH_PREFIX=/var/run/firecracker

# Optional: Default resource settings
CPUS=1
MEMORY=1024
```

### Directory Structure Overview
```
/var/lib/firecracker/           # Base directory (auto-created)
├── kernels/                    # Kernel files (auto-created)
├── images/                     # Base image templates (auto-created)
├── rootfs/                     # VM-specific rootfs files (auto-created)
└── cache/                      # VM configuration cache (auto-created)
```

### Configuration Precedence
1. **Command-line arguments** (highest priority)
2. **Configuration file** (default `/etc/firecracker.env` or specified with `--config`)
3. **Built-in defaults** (lowest priority)

### Custom Directory Configuration
To use different directories, modify the config file (default `/etc/firecracker.env`) or specify a custom config file with `--config`:
```bash
# Example: Use local directories for development
KERNEL_PATH=./dev/kernels
IMAGES_PATH=./dev/images
ROOTFS_PATH=./dev/rootfs
SOCKET_PATH_PREFIX=./dev/sockets
```

## Firecracker API Integration

### Key Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Health check/socket availability |
| `/vm/config` | GET | Complete VM configuration (for list) |
| `/machine-config` | PUT | Set CPU/memory |
| `/boot-source` | PUT | Set kernel and boot args |
| `/drives/rootfs` | PUT | Configure root filesystem |
| `/network-interfaces/{id}` | PUT | Configure network interfaces |
| `/mmds/config` | PUT | Configure MMDS access |
| `/mmds` | PUT/GET | Set/get metadata content |
| `/actions` | PUT | Start VM (InstanceStart) |

### Critical API Response Structure
```python
# /vm/config returns ARRAYS, not objects
config = response.json()
drives = config.get('drives', [])  # ARRAY - iterate to find rootfs
network_interfaces = config.get('network-interfaces', [])  # ARRAY - iterate by iface_id
```

### MMDS Configuration
- Always enabled with network_config object
- Dual interfaces: eth0 (main traffic), mmds0 (metadata access)
- MMDS IP: 169.254.169.254
- Automatic hostname injection from --hostname or VM name

## Command Line Interface

### Initial Setup

**Directory Structure**: The system automatically creates the required directories:
```bash
# Default setup - directories created automatically
sudo mkdir -p /var/lib/firecracker
sudo chown $USER:$USER /var/lib/firecracker  # Optional: for non-root usage
```

**File Placement**:
- Place kernel files in `/var/lib/firecracker/kernels/`
- Place base images in `/var/lib/firecracker/images/`
- VM rootfs files will be created in `/var/lib/firecracker/rootfs/`
- VM configurations cached in `/var/lib/firecracker/cache/`

### Usage Patterns

**Production (binary):**
```bash
fcm images                                       # List available images
fcm kernels                                      # List available kernels
fcm create --name vm1 --kernel vmlinux --image alpine.ext4 --rootfs-size 1G --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
fcm list                                         # Show all VMs with state
fcm stop --name vm1                             # Stop (preserve config)
fcm start --name vm1                            # Start from cache
fcm destroy --name vm1                          # Destroy (with confirmation)
```

**Development (fcm.sh):**
```bash
./fcm.sh images                                  # List available images
./fcm.sh kernels                                 # List available kernels
./fcm.sh create --name vm1 --kernel vmlinux --image alpine.ext4 --rootfs-size 1G --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
./fcm.sh list                                    # Show all VMs with state
./fcm.sh stop --name vm1                        # Stop (preserve config)
./fcm.sh start --name vm1                       # Start from cache
./fcm.sh destroy --name vm1                     # Destroy (with confirmation)
```

### Required Parameters (Create)
- `--name`: VM identifier
- `--kernel`: Kernel filename (in KERNEL_PATH, or set KERNEL in .env)
- `--image`: Image filename (in IMAGES_PATH, or set IMAGE in .env)
- `--rootfs-size`: Rootfs size (or set ROOTFS_SIZE in .env)
- `--cpus`: vCPUs (or set CPUS in .env)
- `--memory`: Memory in MiB (or set MEMORY in .env)
- `--tap-ip`: TAP device host IP
- `--vm-ip`: VM guest IP

### Optional Parameters
- `--tap-device`, `--mmds-tap`: Explicit TAP devices (auto-generated if omitted in internal mode)
- `--hostname`: VM hostname (defaults to VM name)
- `--metadata`: JSON metadata string or @file
- `--foreground`: Debug mode (no supervisor)
- `--force-rootfs`: Overwrite existing rootfs
- `--force-destroy`: Skip confirmation prompt
- `--networkdriver`: Network mode - `internal` (default, manages TAP devices) or `external` (uses existing TAP devices)
- `--version`, `-v`: Show version information

#### External Network Mode Requirements
When using `--networkdriver external`, these parameters become **mandatory**:
- `--tap-device`: Existing TAP device name
- `--tap-ip`: IP address that must be assigned to TAP device
- `--mmds-tap`: Existing MMDS TAP device name  
- `--vm-ip`: VM IP that must have a route via TAP device

## Development Guidelines

### When Making API Changes
1. Reference Swagger documentation: https://github.com/firecracker-microvm/firecracker/blob/main/src/firecracker/swagger/firecracker.yaml
2. Use WebFetch tool if documentation links change
3. Remember: `drives` and `network-interfaces` are ARRAYS in API responses

### Code Patterns
- **Modular class-based design**: Each module contains a focused class (`FirecrackerAPI`, `NetworkManager`, etc.)
- **Single responsibility principle**: Each module handles one aspect of VM management
- **Self-contained modules**: VMLifecycle creates its own dependencies internally
- **Data/Presentation separation**: Modules return raw data, main script handles formatting
- **Idempotent operations**: Operations can be safely repeated without side effects
- **Comprehensive error handling**: Each module provides graceful error handling with detailed messages
- **Session state tracking**: `NetworkManager` tracks allocated TAP devices across operations
- **Cache-first approach**: `ConfigManager` handles all VM configuration persistence
- **Clean imports**: Use relative imports within `lib/` package, absolute imports from CLI
- **Minimal main script**: Only argument parsing, module instantiation, and formatting

### Testing Approach
- Test with actual Firecracker binaries
- Validate TAP auto-generation and network configuration
- Test VM discovery across running/stopped states
- Verify supervisor integration and cleanup scenarios
- Test individual modules in isolation for unit testing
- Verify module integration through CLI commands

### Working with Modular Architecture
**Adding New Features**:
1. Identify which module should contain the new functionality
2. Add methods to the appropriate class (`FirecrackerAPI`, `NetworkManager`, etc.)
3. Update the CLI layer to use the new functionality
4. Test the feature through the CLI interface

**Modifying Existing Features**:
1. Locate the relevant module using the operation mapping table above
2. Make changes within the focused module
3. Ensure module interfaces remain compatible
4. Test through both unit tests and CLI integration

**Module Communication**:
- Main CLI creates ConfigManager and passes it where needed
- VMLifecycle is self-contained:
  - Takes just `args` for create operation
  - Creates its own NetworkManager and FilesystemManager internally
  - Handles ALL validation, preparation, and execution
- VMDiscovery and standalone FilesystemManager get ConfigManager from main
- Modules return raw data, main script handles presentation
- No business logic in main script, only orchestration and formatting

### Dependencies
**Auto-managed by `fcm.sh` development wrapper**:
- Python virtual environment in `venv/`
- `requests`, `requests-unixsocket` packages

**Production binary**: Self-contained, no external dependencies

**System Requirements**:
- Firecracker binary: `/usr/sbin/firecracker`
- Supervisor daemon running
- `resize2fs` utility for rootfs resizing
- Root/sudo access for network and supervisor operations

## Recent Changes Summary

### Latest Enhancements (2024)
1. **Binary Distribution**: Production-ready `fcm` binary available from releases page, `fcm.sh` for development
2. **Standardized Directory Structure**: Default paths moved to `/var/lib/firecracker/` with automatic directory creation
3. **Complete Modular Architecture**: 
   - Split monolithic script into 6 focused modules in `lib/` directory
   - Main script reduced to pure orchestration and presentation
   - VMLifecycle handles ALL creation logic internally (validation, network prep, filesystem prep)
4. **Strict Separation of Concerns**:
   - Business logic in modules (return raw data)
   - Presentation logic in main script (formatting functions)
   - Each action has dedicated elif block for clarity
5. **Self-Contained VMLifecycle**: 
   - Accepts just `args` for creation
   - Creates its own NetworkManager and FilesystemManager
   - Complete encapsulation of VM operations
6. **Clean Socket Management**: 
   - VMLifecycle accepts VM name or socket path
   - ConfigManager provides `get_vm_socket_path()` method
   - No socket path logic in main script
7. **Silent Firecracker Validation**: Binary check happens without verbose output
8. **Unified Network Preparation**: NetworkManager's `prepare_network_devices()` handles all modes
9. **External Network Driver**: `--networkdriver external` mode for using existing TAP devices
10. **Version Information**: `--version` parameter with proper argparse integration

### Breaking Changes
- Destroy action requires VM to be stopped first
- Destroy action signature changed (no longer needs explicit TAP device parameters)
- Uses cache-based cleanup (VMs created before caching system won't work with new destroy)

### Non-Breaking Changes
- **Standardized directories**: Default paths now use `/var/lib/firecracker/` but can be overridden in `.env`
- **Automatic directory creation**: System creates required directories automatically with appropriate permissions
- **Modular refactoring**: Internal architecture completely reorganized but all CLI interfaces remain identical
- **Clean organization**: Implementation moved to `lib/` directory without affecting user experience

### Backward Compatibility
- All existing create/list functionality preserved
- Legacy `discover_running_vms()` method maintained
- VMs created before base image tracking show "N/A" for base image

## Critical Setup Notes

### TAP Device Auto-Generation Logic
```python
# System scan → Session tracking → Sequential assignment
existing = discover_existing_tap_devices()  # ip link show
next_device = find_next_available_tap_device()  # find tap0, tap1, etc.
self.allocated_tap_devices.add(next_device)  # prevent conflicts
```

### Supervisor Configuration Template
```ini
[program:<vm_name>]
command=/usr/sbin/firecracker --id <vm_name> --api-sock <socket_path>
stdout_logfile=/var/log/<vm_name>.log
stderr_logfile=/var/log/<vm_name>.error.log
autostart=true
```

### Cache Structure
```json
{
  "kernel": "/path/to/kernel",
  "rootfs": "/path/to/vm.ext4", 
  "base_image": "alpine.ext4",
  "tap_device": "tap0",
  "mmds_tap": "tap1",
  "vm_ip": "10.0.1.1",
  "tap_ip": "192.168.1.1",
  "cpus": 2,
  "memory": 1024,
  "hostname": "vm-name",
  "networkdriver": "internal",
  "created_at": 1234567890
}
```

### Common Issues & Solutions
- **Socket permission errors**: Check `SOCKET_PATH_PREFIX` directory permissions
- **TAP device conflicts**: Use auto-generation instead of explicit names
- **List shows no VMs**: Check socket directory and `/var/lib/firecracker/cache/` directory
- **Directory permission errors**: System automatically creates `/var/lib/firecracker/` and subdirectories, but requires write permissions. Run with `sudo` or ensure user has access to `/var/lib/firecracker/`
- **Destroy fails**: Ensure VM is stopped first, use `--force-destroy` if needed
- **Missing dependencies (development)**: `fcm.sh` wrapper handles Python environment automatically
- **Binary not found**: Download from releases page and ensure it's in PATH

This document provides complete context for future development while maintaining all critical information in a significantly more compact format.