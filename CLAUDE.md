# Firecracker VM Manager - Development Context

This document provides complete context for the Firecracker VM Manager project for future development sessions.

## Essential Documentation Links

**CRITICAL**: Future development requires access to these Firecracker documentation sources:

### Primary Documentation
- **Getting Started Guide**: https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md
- **Network Setup**: https://github.com/firecracker-microvm/firecracker/blob/main/docs/network-setup.md
- **API Documentation (Swagger)**: https://github.com/firecracker-microvm/firecracker/blob/main/src/firecracker/swagger/firecracker.yaml
- **Main Repository**: https://github.com/firecracker-microvm/firecracker
- **Official Website**: https://firecracker-microvm.github.io

### Creating and Updating Documentation
When making changes to the code also update the documentation. Do not touch README.md instead the correct Doc is firecracker_vm_manager.md

### Key API Information Extracted
From the documentation review, these are the critical API details:

#### Boot Source Endpoint (/boot-source)
- Method: PUT
- Required: `kernel_image_path` (string)
- Optional: `boot_args` (string), `initrd_path` (string)
- Response: 204 (success), 400 (error)

#### Drives Endpoint (/drives/{drive_id})
- Method: PUT
- Required: `drive_id` (string), `is_root_device` (boolean)
- Optional: `path_on_host` (string), `rate_limiter`, `cache_type`
- Response: 204 (success), 400 (error)

#### Network Interfaces (/network-interfaces/{iface_id})
- Method: PUT
- Required: `host_dev_name` (string), `iface_id` (string)  
- Optional: `guest_mac`, `rx_rate_limiter`, `tx_rate_limiter`
- Response: 204 (success), 400 (error)

#### Machine Config (/machine-config)
- Method: PUT
- Required: `vcpu_count` (int), `mem_size_mib` (int)
- Response: 204 (success), 400 (error)

#### Actions (/actions)
- Method: PUT
- Required: `action_type` (enum: FlushMetrics, InstanceStart, SendCtrlAltDel)
- Response: 204 (success), 400 (error)

#### Root Endpoint (/)
- Method: GET
- Used for: Health check/socket availability testing
- Response: 200 (Firecracker listening), connection error (not listening)

## Project Overview

The Firecracker VM Manager is a Python script that automates the creation and destruction of Firecracker microVMs with full lifecycle management including:
- Automatic supervisord integration for process management
- TAP device creation and network configuration
- Complete resource cleanup
- Debugging support via foreground mode

## Key Files

### Main Script: `firecracker_vm_manager.py`
- **Purpose**: Main executable script for VM lifecycle management
- **Actions**: `create` and `destroy` VMs
- **Dependencies**: `requests`, `requests-unixsocket`, `subprocess`, `os`, `pathlib`
- **Requires**: Root/sudo access for network configuration and supervisor management

### Configuration File: `.env`
- **Purpose**: Global default configuration values that apply to all VMs
- **Required Settings**: `KERNEL_PATH`, `CPUS`, `MEMORY` - Must be provided in .env or via command line
- **Priority**: Command line arguments override .env values
- **Note**: VM-specific parameters (rootfs, network settings) are not configurable in .env

### Documentation: `firecracker_vm_manager.md`
- **Purpose**: User documentation with setup instructions, usage examples, and troubleshooting
- **Sections**: Setup, Prerequisites, Usage, Parameters, Configuration, Workflows, API Reference

## Architecture Overview

### Core Classes
- **FirecrackerVMManager**: Main class handling all VM operations
  - Socket communication with Firecracker API
  - Network device management
  - Supervisor configuration management
  - Process lifecycle management

### Key Methods

#### VM Lifecycle
- `create_vm()`: Main entry point for VM creation
- `create_vm_supervisor()`: Creates VM using supervisord (default mode)
- `create_vm_foreground()`: Creates VM in foreground for debugging
- `destroy_vm()`: Destroys VM and cleans up all resources (including MMDS TAP if provided)
- `configure_and_start()`: Configures Firecracker API and starts VM

#### Network Management
- `setup_tap_device()`: Creates TAP device, assigns IP, adds routes
- `remove_tap_device()`: Removes TAP device (routes auto-removed)

#### Supervisor Integration
- `create_supervisor_config()`: Creates `/etc/supervisor/conf.d/<vm_name>.conf`
- `remove_supervisor_config()`: Removes supervisor config file
- `supervisor_reload()`: Runs `supervisorctl update`

#### Firecracker API
- `_make_request()`: HTTP requests to Firecracker API via Unix socket
- `check_socket_in_use()`: Tests if Firecracker is listening on socket
- `set_machine_config()`: CPU/memory configuration
- `set_boot_source()`: Kernel and boot arguments
- `set_rootfs()`: Root filesystem configuration
- `set_network_interface()`: Primary network interface configuration (eth0)
- `set_mmds_network_interface()`: Dedicated MMDS network interface configuration (mmds0)
- `configure_mmds_interface()`: Configure MMDS interface access permissions
- `set_mmds_metadata()`: Set metadata content for MMDS
- `start_microvm()`: Starts the VM via API

## Current Features

### Two Operation Modes

#### 1. Supervisor Mode (Default)
- Creates supervisor configuration file
- Firecracker runs as supervised daemon
- Automatic restart capability
- Logs to `/var/log/<vm_name>.log` and `/var/log/<vm_name>.error.log`

#### 2. Foreground Mode (`--foreground`)
- Runs Firecracker directly in terminal
- For debugging purposes
- No supervisor configuration
- Automatic cleanup on termination (Ctrl+C or process exit)

### Network Configuration
- Creates TAP devices if they don't exist
- Assigns /32 host IP addresses
- Installs host routes for VM IPs
- Handles existing configurations gracefully
- Automatic route cleanup when TAP device is removed

### Resource Management
- Socket file creation/cleanup
- TAP device lifecycle management
- Supervisor configuration management
- Process monitoring and cleanup

### Metadata Service (MMDS) Support
- JSON metadata parsing from command line or file
- Automatic network configuration injection (always includes network_config object)
- Dual network interface setup with separate TAP devices
  - eth0 (via --tap-device) for application traffic
  - mmds0 (via --mmds-tap) for metadata access
- Dedicated MMDS interface configuration via `/mmds/config` endpoint
- MMDS IP address explicitly configured as 169.254.169.254
- Support for custom application metadata

## Command Line Interface

### Actions
- `create`: Create and start a new VM
- `destroy`: Stop and destroy an existing VM

### Parameters

#### Required
- `--name`: VM identifier (used in supervisor config)

#### Create Action Required
- `--kernel`: Path to kernel image (vmlinux) - can be set in .env as KERNEL_PATH
- `--rootfs`: Path to root filesystem image
- `--cpus`: Number of vCPUs - can be set in .env as CPUS
- `--memory`: Memory in MiB - can be set in .env as MEMORY
- `--tap-device`: Host TAP device name
- `--tap-ip`: IP address for TAP device on host
- `--vm-ip`: IP address for VM guest

#### Optional Parameters
- `--socket`: Path to Firecracker API socket (default: `/tmp/<vm_name>.sock`)
- `--metadata`: JSON metadata for MMDS (provide JSON string or file path starting with @)
- `--mmds-tap`: TAP device name for MMDS interface (enables MMDS with network config)
- `--foreground`: Run in foreground for debugging

#### Destroy Action Required
- `--tap-device`: TAP device name to remove

#### Destroy Action Optional
- `--mmds-tap`: MMDS TAP device name to remove (if VM was created with metadata)

## Firecracker API Integration

### Endpoints Used
- `GET /`: Check if Firecracker is listening
- `PUT /machine-config`: Set CPU and memory
- `PUT /boot-source`: Set kernel and boot arguments
- `PUT /drives/rootfs`: Configure root filesystem
- `PUT /network-interfaces/eth0`: Configure network interface
- `PUT /actions`: Start the VM (action_type: "InstanceStart")

### Communication
- Uses Unix domain sockets for API communication
- `requests-unixsocket` library for HTTP over Unix sockets
- Base URL format: `http+unix://<escaped_socket_path>`

## Supervisor Integration

### Configuration Template
```ini
[program:<vm_name>]
command=/usr/sbin/firecracker --id <vm_name> --api-sock <socket_path>
stdout_logfile=/var/log/<vm_name>.log
stderr_logfile=/var/log/<vm_name>.error.log
autostart=true
```

### Management Commands
- `supervisorctl update`: Reload configuration and start new programs
- Config location: `/etc/supervisor/conf.d/<vm_name>.conf`

## Network Configuration Details

### TAP Device Setup
1. Check if device exists: `ip link show <device>`
2. Create if needed: `sudo ip tuntap add <device> mode tap`
3. Check current IP: `ip addr show <device>`
4. Add IP if needed: `sudo ip addr add <ip>/32 dev <device>`
5. Bring up: `sudo ip link set <device> up`
6. Check route: `ip route show <vm_ip>/32`
7. Add route if needed: `sudo ip route add <vm_ip>/32 dev <device>`

### Cleanup Process
1. Remove TAP device: `sudo ip link del <device>`
   - Routes are automatically removed when device is deleted
   - No need to manually remove routes

## Error Handling

### Socket Management
- Checks if socket is in use before operations
- Removes stale socket files
- Prevents conflicts with running instances

### Network Conflicts
- Checks for existing IP assignments
- Checks for existing routes
- Graceful handling of pre-existing configurations

### Process Management
- Signal handling for graceful shutdown in foreground mode
- Cleanup on abnormal termination
- Resource leak prevention

## Dependencies

### Python Packages
```bash
pip install requests requests-unixsocket
```

### System Requirements
- Firecracker binary at `/usr/sbin/firecracker`
- Supervisor daemon running
- Root/sudo access for:
  - Network device management (`ip` commands)
  - Supervisor configuration (`/etc/supervisor/conf.d/`)
  - Supervisor control (`supervisorctl`)

### File Permissions
- Read access to kernel and rootfs files
- Write access to socket directory
- Write access to `/etc/supervisor/conf.d/`
- Write access to `/var/log/` for Firecracker logs

## Common Workflows

### Creating a VM
1. Parse command line arguments
2. Validate required parameters
3. Check socket availability
4. Clean up stale socket files
5. Either:
   - **Supervisor mode**: Create config → reload supervisor → configure VM
   - **Foreground mode**: Setup network → start Firecracker → configure VM
6. Setup TAP device and networking
7. Configure Firecracker via API
8. Start the VM

### Destroying a VM
1. Parse command line arguments
2. Check socket is not in use (VM should be stopped)
3. Remove socket file
4. Remove TAP device (routes auto-removed)
5. Remove supervisor configuration
6. Reload supervisor

## Debugging and Troubleshooting

### Foreground Mode Benefits
- Direct process output visibility
- Easy termination with Ctrl+C
- No supervisor configuration required
- Immediate feedback on configuration issues
- Clear command visibility for manual testing

### Common Issues
- Socket permission errors → Check socket directory permissions
- TAP device creation failures → Check sudo access and network permissions
- Firecracker startup failures → Check binary path and kernel/rootfs files
- Supervisor issues → Check supervisor daemon status and configuration directory

### Log Locations
- **Supervisor mode**: `/var/log/<vm_name>.log` and `/var/log/<vm_name>.error.log`
- **Foreground mode**: Direct terminal output

## Future Enhancement Areas

### Potential Improvements
1. **Configuration files**: Support for VM configuration files
2. **Multiple network interfaces**: Support for additional network devices
3. **Storage devices**: Support for additional block devices
4. **Resource monitoring**: VM resource usage monitoring
5. **Template management**: VM template system
6. **Batch operations**: Multiple VM management
7. **Integration**: Cloud-init, metadata service integration

### API Extensions
- Health checking endpoints
- Metrics collection
- VM state management
- Snapshot/restore functionality

## Development Guidelines

### Code Structure
- Single class design for simplicity
- Clear separation of concerns (network, supervisor, API)
- Comprehensive error handling
- Idempotent operations where possible

### Testing Approach
- Test with actual Firecracker binaries
- Validate network configuration
- Test cleanup scenarios
- Verify supervisor integration

### Documentation Standards
- Keep `firecracker_vm_manager.md` updated with all changes
- Update help text for new parameters
- Include example usage for new features
- Document any new dependencies or requirements

## Critical Setup Information for Future Development

### When Making API Changes
1. **Always reference the Swagger documentation**: https://github.com/firecracker-microvm/firecracker/blob/main/src/firecracker/swagger/firecracker.yaml
2. **Check the getting started guide for examples**: https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md
3. **Use WebFetch tool to get latest API information** if documentation links change

### Example curl commands from Getting Started Guide
These were the original curl commands the script abstracts:

```bash
# Set boot source
curl --unix-socket /tmp/firecracker.socket -i \
  -X PUT 'http://localhost/boot-source' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "kernel_image_path": "hello-vmlinux.bin",
    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"
  }'

# Set rootfs
curl --unix-socket /tmp/firecracker.socket -i \
  -X PUT 'http://localhost/drives/rootfs' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "drive_id": "rootfs",
    "path_on_host": "hello-rootfs.ext4",
    "is_root_device": true,
    "is_read_only": false
  }'

# Set network interface  
curl --unix-socket /tmp/firecracker.socket -i \
  -X PUT 'http://localhost/network-interfaces/net1' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "iface_id": "net1",
    "guest_mac": "AA:FC:00:00:00:01",
    "host_dev_name": "tap0"
  }'

# Start microVM
curl --unix-socket /tmp/firecracker.socket -i \
  -X PUT 'http://localhost/actions' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "action_type": "InstanceStart"
  }'
```

### Supervisor Configuration Template Used
```ini
[program:<vm_name>]
command=/usr/sbin/firecracker --id <vm_name> --api-sock <socket_path>
stdout_logfile=/var/log/<vm_name>.log
stderr_logfile=/var/log/<vm_name>.error.log
autostart=true
```

### If Documentation Links Break
If the GitHub links become unavailable, you can:
1. Use the WebFetch tool to get current documentation
2. Search for "firecracker microvm api documentation" 
3. Look for the official Firecracker repository on GitHub
4. Check the swagger/OpenAPI specification in the source code

This context document should provide all necessary information for future development sessions, including the complete architecture, current implementation details, potential enhancement directions, and critical external documentation references.