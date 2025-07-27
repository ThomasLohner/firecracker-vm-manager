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
| `fcm` | Bash wrapper with auto Python environment setup |
| `firecracker_vm_manager.py` | Core Python script for VM operations |
| `.env` | Global configuration (KERNEL_PATH, IMAGES_PATH, ROOTFS_PATH, etc.) |
| `firecracker_vm_manager.md` | User documentation |

### Core Operations
| Action | Function | Description |
|--------|----------|-------------|
| `create` | `create_vm()` | Build rootfs from image, configure, start VM |
| `destroy` | `destroy_vm()` | Stop VM, confirm, cleanup all resources |
| `stop` | `stop_vm()` | Stop VM, preserve TAP devices and cache |
| `start` | `start_vm()` | Restart VM from cached configuration |
| `restart` | `restart_vm()` | Stop + start sequence |
| `list` | `discover_all_vms()` | Show all VMs (running/stopped) with details |
| `images` | `list_available_images()` | List base images from IMAGES_PATH |
| `kernels` | List kernel files from KERNEL_PATH |

### Key Architecture Components

#### VM Configuration Caching
- Auto-creates `cache/` directory for VM configurations
- JSON storage: `cache/<vm_name>.json` with complete VM state
- Enables stop/start workflow without losing configuration
- Stores: kernel, rootfs, TAP devices, IPs, CPU/memory, hostname, base_image, timestamp

#### Image-Based Rootfs Building
- Base images in IMAGES_PATH serve as templates
- VM-specific rootfs: `<ROOTFS_PATH>/<vm_name>.ext4`
- Automatic copying and `resize2fs` resizing
- Force overwrite protection with `--force-rootfs` override
- Supports: ext4, ext3, ext2, img, qcow2, raw formats

#### TAP Device Auto-Generation
- System scan: `ip link show` to find existing devices
- Sequential naming: tap0, tap1, tap2, etc.
- Session tracking prevents conflicts
- Auto-generates both main and MMDS TAP devices
- Validates explicitly specified devices don't exist

#### VM Discovery and Monitoring
- Scans cache directory and socket files
- State detection: running (API responsive) vs stopped
- Mixed data sources: API for running VMs, cache for stopped
- Comprehensive table display with all VM details

### Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `KERNEL_PATH` | Kernel files directory | Required |
| `KERNEL` | Default kernel filename | Optional |
| `IMAGES_PATH` | Base image files | `./images` |
| `ROOTFS_PATH` | VM-specific rootfs files | `./rootfs` |
| `SOCKET_PATH_PREFIX` | Socket file directory | `/tmp` |
| `CPUS` | Default vCPUs | Required |
| `MEMORY` | Default memory (MiB) | Required |
| `IMAGE` | Default image file | Optional |
| `ROOTFS_SIZE` | Default rootfs size | Optional |

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

### Usage Patterns
```bash
./fcm images                                     # List available images
./fcm kernels                                    # List available kernels
./fcm create --name vm1 --kernel vmlinux --image alpine.ext4 --rootfs-size 1G --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
./fcm list                                       # Show all VMs with state
./fcm stop --name vm1                           # Stop (preserve config)
./fcm start --name vm1                          # Start from cache
./fcm destroy --name vm1                        # Destroy (with confirmation)
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
- `--tap-device`, `--mmds-tap`: Explicit TAP devices (auto-generated if omitted)
- `--hostname`: VM hostname (defaults to VM name)
- `--metadata`: JSON metadata string or @file
- `--foreground`: Debug mode (no supervisor)
- `--force-rootfs`: Overwrite existing rootfs
- `--force-destroy`: Skip confirmation prompt

## Development Guidelines

### When Making API Changes
1. Reference Swagger documentation: https://github.com/firecracker-microvm/firecracker/blob/main/src/firecracker/swagger/firecracker.yaml
2. Use WebFetch tool if documentation links change
3. Remember: `drives` and `network-interfaces` are ARRAYS in API responses

### Code Patterns
- Single `FirecrackerVMManager` class design
- Idempotent operations where possible
- Comprehensive error handling with graceful fallbacks
- Session state tracking for TAP device allocation
- Cache-first approach for configuration persistence

### Testing Approach
- Test with actual Firecracker binaries
- Validate TAP auto-generation and network configuration
- Test VM discovery across running/stopped states
- Verify supervisor integration and cleanup scenarios

### Dependencies
**Auto-managed by `fcm` wrapper**:
- Python virtual environment in `venv/`
- `requests`, `requests-unixsocket` packages

**System Requirements**:
- Firecracker binary: `/usr/sbin/firecracker`
- Supervisor daemon running
- `resize2fs` utility for rootfs resizing
- Root/sudo access for network and supervisor operations

## Recent Changes Summary

### Latest Enhancements (2024)
1. **Destroy Action Refactoring**: Cache-based cleanup, confirmation prompts, VM running checks, `--force-destroy` flag
2. **Base Image Tracking**: VM cache stores original image filename, list command shows provenance
3. **VM State Monitoring**: List command shows both running and stopped VMs with state detection
4. **Hostname Support**: Configurable VM hostnames via `--hostname` parameter, auto-injected into MMDS
5. **Enhanced TAP Management**: Auto-generation with conflict prevention, session tracking
6. **Configuration Caching**: Complete stop/start workflow with JSON-based VM state persistence

### Breaking Changes
- Destroy action requires VM to be stopped first
- Destroy action signature changed (no longer needs explicit TAP device parameters)
- Uses cache-based cleanup (VMs created before caching system won't work with new destroy)

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
  "created_at": 1234567890
}
```

### Common Issues & Solutions
- **Socket permission errors**: Check `SOCKET_PATH_PREFIX` directory permissions
- **TAP device conflicts**: Use auto-generation instead of explicit names
- **List shows no VMs**: Check socket directory and cache directory
- **Destroy fails**: Ensure VM is stopped first, use `--force-destroy` if needed
- **Missing dependencies**: `fcm` wrapper handles Python environment automatically

This document provides complete context for future development while maintaining all critical information in a significantly more compact format.