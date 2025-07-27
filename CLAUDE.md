# Firecracker VM Manager - Development Context

This document provides complete context for the Firecracker VM Manager project for future development sessions.

## Essential Documentation Links

**CRITICAL**: Future development requires access to these Firecracker documentation sources:

### Primary Documentation
- **Getting Started Guide**: https://raw.githubusercontent.com/firecracker-microvm/firecracker/refs/heads/main/docs/getting-started.md
- **Network Setup**: https://raw.githubusercontent.com/firecracker-microvm/firecracker/refs/heads/main/docs/network-setup.md
- **API Documentation (Swagger)**: https://raw.githubusercontent.com/firecracker-microvm/firecracker/refs/heads/main/src/firecracker/swagger/firecracker.yaml
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

#### VM Config (/vm/config)
- Method: GET
- Used for: Getting complete VM configuration (used by list action)
- Response: 200 (success with JSON configuration), connection error (not listening)

#### MMDS Endpoints (/mmds, /mmds/config)
- `PUT /mmds` - Set metadata content
- `GET /mmds` - Get metadata content
- `PUT /mmds/config` - Configure MMDS interface access
- Response: 200/204 (success), 400 (error)

#### Root Endpoint (/)
- Method: GET
- Used for: Health check/socket availability testing
- Response: 200 (Firecracker listening), connection error (not listening)

## Project Overview

The Firecracker VM Manager is a Python script with a bash wrapper (`fcm`) that automates the creation, destruction, and listing of Firecracker microVMs with full lifecycle management including:
- Automatic supervisord integration for process management
- TAP device auto-generation and network configuration
- Complete resource cleanup
- Debugging support via foreground mode
- VM discovery and monitoring via list command
- Socket directory management with configurable paths

## Key Files

### Wrapper Script: `fcm`
- **Purpose**: Bash wrapper script providing zero-configuration Python environment management
- **Auto-Installation**: Creates virtual environment and installs dependencies automatically
- **Smart Detection**: Uses correct import names for module checking (`requests_unixsocket` vs `requests-unixsocket`)
- **Location**: Root directory alongside `firecracker_vm_manager.py`
- **Usage**: Primary entry point for all VM operations (`./fcm create`, `./fcm list`, etc.)
- **First Run**: Sets up complete Python environment automatically
- **Subsequent Runs**: Uses existing environment with no setup overhead

### Main Script: `firecracker_vm_manager.py`
- **Purpose**: Core Python script for VM lifecycle management (executed by `fcm` wrapper)
- **Actions**: `create`, `destroy`, and `list` VMs
- **Dependencies**: `requests`, `requests-unixsocket`, `subprocess`, `os`, `pathlib`
- **Requires**: Root/sudo access for network configuration and supervisor management

### Configuration File: `.env`
- **Purpose**: Global default configuration values that apply to all VMs
- **Required Settings**: `KERNEL_PATH`, `CPUS`, `MEMORY` - Must be provided in .env or via command line
- **New Settings**: `SOCKET_PATH_PREFIX` - Controls socket file directory (default: /tmp)
- **Priority**: Command line arguments override .env values
- **Note**: VM-specific parameters (rootfs, network settings) are not configurable in .env

### Documentation: `firecracker_vm_manager.md`
- **Purpose**: User documentation with setup instructions, usage examples, and troubleshooting
- **Sections**: Setup, Prerequisites, Usage, Parameters, Configuration, Workflows, API Reference
- **Status**: Updated to reflect all current features including TAP auto-generation and list command

## Architecture Overview

### Core Classes
- **FirecrackerVMManager**: Main class handling all VM operations
  - Socket communication with Firecracker API
  - Network device management and auto-generation
  - Supervisor configuration management
  - Process lifecycle management
  - VM discovery and information extraction

### Key Methods

#### VM Lifecycle
- `create_vm()`: Main entry point for VM creation
- `create_vm_supervisor()`: Creates VM using supervisord (default mode)
- `create_vm_foreground()`: Creates VM in foreground for debugging
- `destroy_vm()`: Destroys VM and cleans up all resources (including MMDS TAP)
- `configure_and_start()`: Configures Firecracker API and starts VM

#### TAP Device Management (NEW)
- `discover_existing_tap_devices()`: Scans system for existing TAP devices
- `find_next_available_tap_device()`: Generates next available device name (tap0, tap1, etc.)
- `validate_tap_device_available()`: Checks if explicitly specified devices exist
- `get_tap_device_ip()`: Extracts IP address from TAP device on system
- `setup_tap_device()`: Creates TAP device, assigns IP, adds routes
- `setup_mmds_tap_device()`: Creates MMDS TAP device
- `remove_tap_device()`: Removes TAP device (routes auto-removed)

#### VM Discovery and Monitoring (NEW)
- `discover_running_vms()`: Scans socket directory for running VMs
- `get_vm_config()`: Gets VM configuration via /vm/config API
- `format_vm_table()`: Formats VM information as a table
- `_get_mmds_data_for_vm()`: Gets MMDS data for internal IP extraction

#### Network Management
- All original network methods remain, enhanced with auto-generation

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

### Three Operation Modes

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

#### 3. List Mode (NEW)
- Discovers running VMs by scanning socket files
- Queries VM configuration via API
- Displays comprehensive table with VM information

### TAP Device Auto-Generation (NEW MAJOR FEATURE)

#### Auto-Generation Features
- **System Discovery**: Scans existing `tap*` devices using `ip link show`
- **Sequential Naming**: Generates tap0, tap1, tap2, etc. automatically
- **Session Tracking**: Prevents conflicts when creating multiple VMs in same session
- **Validation**: Checks that explicitly specified devices don't already exist
- **Both Interfaces**: Auto-generates both main TAP and MMDS TAP devices

#### TAP Device Behavior
**Auto-generation (default):**
```bash
# Creates tap0 (main) and tap1 (MMDS) automatically
./fcm create --name vm1 --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
```

**Explicit specification:**
```bash
# Uses specified devices (fails if they already exist)
./fcm create --name vm1 --tap-device tap5 --mmds-tap tap6 --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
```

### Socket Path Management (NEW)

#### SOCKET_PATH_PREFIX Environment Variable
- **Purpose**: Controls where VM socket files are stored
- **Default**: `/tmp` (backward compatible)
- **Recommended**: `/var/run/firecracker` for production
- **Auto-creation**: Directory created automatically if it doesn't exist
- **Usage**: Set in .env file as `SOCKET_PATH_PREFIX=/var/run/firecracker`

### Network Configuration
- Creates TAP devices if they don't exist (with auto-generation)
- Assigns /32 host IP addresses
- Installs host routes for VM IPs
- Handles existing configurations gracefully
- Automatic route cleanup when TAP device is removed
- Always creates both main and MMDS TAP devices

### Resource Management
- Socket file creation/cleanup in configurable directory
- TAP device lifecycle management with auto-generation
- Supervisor configuration management
- Process monitoring and cleanup

### Metadata Service (MMDS) Support (ENHANCED)
- **Always Enabled**: All VMs now get MMDS with network_config
- JSON metadata parsing from command line or file
- Automatic network configuration injection (always includes network_config object with hostname)
- Dual network interface setup with separate TAP devices
  - eth0 (via main TAP) for application traffic
  - mmds0 (via MMDS TAP) for metadata access
- Dedicated MMDS interface configuration via `/mmds/config` endpoint
- MMDS IP address explicitly configured as 169.254.169.254
- Support for custom application metadata
- **Hostname Configuration**: Configurable via --hostname parameter, defaults to VM name

### VM Discovery and Monitoring (NEW MAJOR FEATURE)

#### List Command Features
- **Socket Scanning**: Discovers VMs by finding .sock files in socket directory
- **API Querying**: Connects to each VM's Firecracker API for configuration
- **Real-time Data**: Shows current VM state and configuration
- **Rich Information**: Comprehensive table with all VM details

#### Information Displayed
- **VM Name**: Extracted from socket filename
- **Internal IP**: VM's guest IP from MMDS network_config
- **CPUs**: Number of virtual CPUs from machine-config
- **Memory**: RAM allocation from machine-config
- **Rootfs**: Root filesystem filename (path stripped)
- **Kernel**: Kernel image filename (path stripped)
- **TAP Interface (IP)**: Main interface device and host IP address
- **MMDS TAP**: MMDS interface device name

## Command Line Interface

### Actions
- `create`: Create and start a new VM
- `destroy`: Stop and destroy an existing VM
- `list`: List all running VMs with configuration details
- `kernels`: List available kernel files from KERNEL_PATH directory (NEW)

### Primary Usage
All commands are executed through the `fcm` wrapper script:
```bash
./fcm kernels                                    # List available kernels
./fcm create --name myvm --kernel vmlinux-6.1.141 --rootfs disk.ext4 ...
./fcm list                                       # List running VMs
./fcm destroy --name myvm                        # Destroy VM
```

### Parameters

#### Required
- `--name`: VM identifier (not required for list action)

#### Create Action Required
- `--kernel`: Kernel filename (must exist in KERNEL_PATH directory)
- `--rootfs`: Path to root filesystem image
- `--cpus`: Number of vCPUs - can be set in .env as CPUS
- `--memory`: Memory in MiB - can be set in .env as MEMORY
- `--tap-ip`: IP address for TAP device on host
- `--vm-ip`: IP address for VM guest

#### Create Action Optional (MAJOR CHANGES)
- `--tap-device`: Host TAP device name (AUTO-GENERATED if not specified)
- `--mmds-tap`: TAP device name for MMDS interface (AUTO-GENERATED if not specified)
- `--socket`: Path to Firecracker API socket (default: `<SOCKET_PATH_PREFIX>/<vm_name>.sock`)
- `--metadata`: JSON metadata for MMDS (provide JSON string or file path starting with @)
- `--hostname`: Hostname for the VM (defaults to VM name if not specified)
- `--foreground`: Run in foreground for debugging

#### Destroy Action Optional (ENHANCED)
- `--tap-device`: TAP device name to remove (optional with warning if not specified)
- `--mmds-tap`: MMDS TAP device name to remove (optional)

#### List Action
- No additional parameters required
- Uses socket directory from SOCKET_PATH_PREFIX

#### Kernels Action (NEW)
- No additional parameters required
- Uses KERNEL_PATH from .env file to scan for available kernels
- KERNEL_PATH must be a directory containing kernel files

## Firecracker API Integration

### Endpoints Used
- `GET /`: Check if Firecracker is listening
- `GET /vm/config`: Get complete VM configuration (NEW - used by list)
- `PUT /machine-config`: Set CPU and memory
- `PUT /boot-source`: Set kernel and boot arguments
- `PUT /drives/rootfs`: Configure root filesystem
- `PUT /network-interfaces/eth0`: Configure primary network interface
- `PUT /network-interfaces/mmds0`: Configure MMDS network interface (ALWAYS used now)
- `PUT /mmds/config`: Configure MMDS interface access (ALWAYS used now)
- `PUT /mmds`: Set metadata content (ALWAYS used now)
- `GET /mmds`: Get metadata content (NEW - used by list for internal IP)
- `PUT /actions`: Start the VM (action_type: "InstanceStart")

### API Response Structure (CRITICAL for list functionality)

#### /vm/config Response Format
```json
{
  "drives": [
    {
      "drive_id": "rootfs",
      "is_root_device": true,
      "path_on_host": "/root/vm2-alpine.ext4"
    }
  ],
  "boot-source": {
    "kernel_image_path": "/root/firecracker/resources/x86_64/vmlinux-6.1.141"
  },
  "machine-config": {
    "vcpu_count": 1,
    "mem_size_mib": 2048
  },
  "network-interfaces": [
    {
      "iface_id": "eth0",
      "host_dev_name": "tap2"
    },
    {
      "iface_id": "mmds0", 
      "host_dev_name": "tap3"
    }
  ]
}
```

**IMPORTANT**: 
- `drives` is an ARRAY, not object - iterate to find rootfs
- `network-interfaces` is an ARRAY, not object - iterate by iface_id
- Always check for both eth0 and mmds0 interfaces

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

### TAP Device Setup (ENHANCED)
1. **Auto-discovery**: `ip link show | grep tap` to find existing devices
2. **Auto-generation**: Find next available tapN device name
3. **Validation**: Check if explicitly specified devices exist (fail if they do)
4. **Creation**: Create if needed: `sudo ip tuntap add <device> mode tap`
5. **IP Assignment**: Add IP if needed: `sudo ip addr add <ip>/32 dev <device>`
6. **Activation**: Bring up: `sudo ip link set <device> up`
7. **Routing**: Add route if needed: `sudo ip route add <vm_ip>/32 dev <device>`

### TAP Device Session Tracking (NEW)
- Maintains `allocated_tap_devices` set in FirecrackerVMManager
- Tracks devices allocated during current session
- Prevents conflicts when creating multiple VMs
- Validates explicitly specified devices don't conflict

### IP Address Resolution (NEW)
- Queries system for TAP device IPs using `ip addr show <device>`
- Parses output to extract IPv4 addresses
- Used by list command to show host IP addresses
- Gracefully handles missing devices or IPs

### Cleanup Process
1. Remove TAP device: `sudo ip link del <device>`
   - Routes are automatically removed when device is deleted
   - No need to manually remove routes

## Error Handling

### Socket Management
- Checks if socket is in use before operations
- Removes stale socket files
- Prevents conflicts with running instances
- Handles configurable socket directories

### Network Conflicts (ENHANCED)
- Checks for existing IP assignments
- Checks for existing routes
- Graceful handling of pre-existing configurations
- Validates explicitly specified TAP devices don't exist
- Auto-generates alternative device names

### Process Management
- Signal handling for graceful shutdown in foreground mode
- Cleanup on abnormal termination
- Resource leak prevention

### API Error Handling (ENHANCED)
- Graceful handling of offline VMs in list command
- Proper error messages for API failures
- Fallback to device names when IP resolution fails

## Dependencies

### Automatic Python Environment Management
The `fcm` wrapper script provides **zero-configuration** Python environment management:

#### Auto-Installation Features
- **Virtual Environment**: Automatically creates `venv/` directory on first run
- **Smart Dependency Detection**: Checks for required modules using correct import names
- **Automatic Installation**: Installs missing packages (`requests`, `requests-unixsocket`) 
- **Skip Existing**: Only installs packages that aren't already present
- **Seamless Execution**: Handles all environment setup transparently

#### First Run Experience
```bash
./fcm create --name vm1 --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
# Output: Creating Python virtual environment...
#         Installing missing Python modules: requests requests-unixsocket
#         [Continues with VM creation...]
```

#### Subsequent Runs
```bash
./fcm list
# No setup output - runs immediately with existing environment
```

### Manual Installation (if not using fcm wrapper)
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
- `ip` command for network operations (gracefully handles absence)

### File Permissions
- Read access to kernel and rootfs files
- Write access to socket directory (configurable)
- Write access to `/etc/supervisor/conf.d/`
- Write access to `/var/log/` for Firecracker logs

## Common Workflows

### Creating VMs with Auto-Generation (NEW DEFAULT)
1. Parse command line arguments and .env configuration
2. Auto-generate TAP device names if not specified
3. Validate explicitly specified devices don't exist
4. Check socket availability in configured directory
5. Clean up stale socket files
6. Either:
   - **Supervisor mode**: Create config → reload supervisor → configure VM
   - **Foreground mode**: Setup network → start Firecracker → configure VM
7. Setup TAP devices and networking (both main and MMDS)
8. Configure Firecracker via API (including MMDS)
9. Start the VM

### Listing VMs (NEW)
1. Scan socket directory for .sock files
2. For each socket file:
   - Extract VM name from filename
   - Test if Firecracker is listening
   - Query /vm/config API for configuration
   - Query /mmds API for metadata (internal IP)
   - Query system for TAP device IPs
3. Format and display comprehensive table

### Destroying VMs (ENHANCED)
1. Parse command line arguments
2. Check socket is not in use (VM should be stopped)
3. Remove socket file from configured directory
4. Remove TAP devices if specified (routes auto-removed)
5. Remove supervisor configuration
6. Reload supervisor

## Debugging and Troubleshooting

### Foreground Mode Benefits
- Direct process output visibility
- Easy termination with Ctrl+C
- No supervisor configuration required
- Immediate feedback on configuration issues
- Clear command visibility for manual testing

### List Command for Monitoring (NEW)
- Real-time VM status checking
- Configuration verification
- Network troubleshooting
- Resource usage overview

### Common Issues
- Socket permission errors → Check socket directory permissions and SOCKET_PATH_PREFIX
- TAP device creation failures → Check sudo access and network permissions
- TAP device conflicts → Use auto-generation instead of explicit names
- Firecracker startup failures → Check binary path and kernel/rootfs files
- Supervisor issues → Check supervisor daemon status and configuration directory
- List command shows no VMs → Check socket directory and VM status

### Log Locations
- **Supervisor mode**: `/var/log/<vm_name>.log` and `/var/log/<vm_name>.error.log`
- **Foreground mode**: Direct terminal output

## Future Enhancement Areas

### Potential Improvements
1. **Configuration files**: Support for VM configuration files
2. **Multiple network interfaces**: Support for additional network devices beyond eth0/mmds0
3. **Storage devices**: Support for additional block devices
4. **Resource monitoring**: VM resource usage monitoring via API
5. **Template management**: VM template system
6. **Batch operations**: Multiple VM management
7. **Integration**: Cloud-init, metadata service integration
8. **TAP device IP management**: Auto-assign IP addresses for TAP devices
9. **VM state management**: Start/stop/pause operations for existing VMs
10. **Performance metrics**: Integration with Firecracker metrics API

### API Extensions
- Health checking endpoints
- Metrics collection
- VM state management
- Snapshot/restore functionality

## Development Guidelines

### Code Structure
- Single class design for simplicity
- Clear separation of concerns (network, supervisor, API, discovery)
- Comprehensive error handling
- Idempotent operations where possible
- Session state management for TAP devices

### Testing Approach
- Test with actual Firecracker binaries
- Validate network configuration and auto-generation
- Test cleanup scenarios
- Verify supervisor integration
- Test VM discovery and listing functionality

### Documentation Standards
- Keep `firecracker_vm_manager.md` updated with all changes
- Update help text for new parameters
- Include example usage for new features
- Document any new dependencies or requirements
- Update CLAUDE.md with architectural changes

## Critical Setup Information for Future Development

### When Making API Changes
1. **Always reference the Swagger documentation**: https://github.com/firecracker-microvm/firecracker/blob/main/src/firecracker/swagger/firecracker.yaml
2. **Check the getting started guide for examples**: https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md
3. **Use WebFetch tool to get latest API information** if documentation links change
4. **Remember API response structure**: drives and network-interfaces are ARRAYS, not objects

### Example API Response Parsing (CRITICAL)
When working with /vm/config responses, remember:

```python
# CORRECT - drives is an array
drives = config.get('drives', [])
for drive in drives:
    if drive.get('drive_id') == 'rootfs' and drive.get('is_root_device', False):
        rootfs_path = drive.get('path_on_host', 'N/A')

# CORRECT - network-interfaces is an array  
network_interfaces = config.get('network-interfaces', [])
for interface in network_interfaces:
    iface_id = interface.get('iface_id')
    if iface_id == 'eth0':
        tap_device = interface.get('host_dev_name')
```

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

### TAP Device Auto-Generation Logic (NEW CRITICAL FEATURE)
The auto-generation system works as follows:

1. **System Scan**: `ip link show` to find existing tap devices
2. **Index Extraction**: Parse device names to extract indices (tap0 → 0, tap1 → 1)
3. **Session Tracking**: Maintain set of allocated devices in current session
4. **Conflict Prevention**: Check both system devices and session allocations
5. **Sequential Assignment**: Find first available index starting from 0

```python
# Key data structures
self.allocated_tap_devices = set()  # Session tracking

# Auto-generation flow
existing = discover_existing_tap_devices()  # System scan
next_device = find_next_available_tap_device()  # Find available
self.allocated_tap_devices.add(next_device)  # Track allocation
```

### If Documentation Links Break
If the GitHub links become unavailable, you can:
1. Use the WebFetch tool to get current documentation
2. Search for "firecracker microvm api documentation" 
3. Look for the official Firecracker repository on GitHub
4. Check the swagger/OpenAPI specification in the source code

## Project Status Summary

### Recently Implemented Features (Latest Session)
1. **Kernels Action**: New command to list available kernel files from KERNEL_PATH directory
2. **Simplified Kernel Resolution**: --kernel parameter takes filename, KERNEL_PATH is always a directory
3. **FCM Wrapper Script**: Bash wrapper that auto-manages Python virtual environment and dependencies
4. **TAP Device Auto-Generation**: Complete system for automatic TAP device discovery and assignment
5. **Socket Path Configuration**: SOCKET_PATH_PREFIX environment variable for configurable socket directories
6. **VM Listing and Monitoring**: Comprehensive list command with API querying and table display
7. **Enhanced Network Management**: TAP device IP resolution and display
8. **Session-Based Conflict Prevention**: Tracks allocated devices within script execution
9. **Validation System**: Checks for existing devices when explicitly specified
10. **Always-On MMDS**: All VMs now get MMDS with network configuration and hostname
11. **Hostname Parameter**: New --hostname parameter automatically injected into MMDS network_config

### Current Capabilities
- **Zero-Setup Execution**: `fcm` wrapper handles all environment and dependency management
- **Kernel Management**: List available kernels and use filenames instead of full paths
- **Full VM Lifecycle**: Create, destroy, and list VMs
- **Automatic Network Setup**: TAP device auto-generation and configuration
- **Production Ready**: Supervisor integration with configurable paths
- **Development Friendly**: Foreground mode for debugging
- **Monitoring**: Real-time VM discovery and status display
- **Robust**: Comprehensive error handling and validation

### Architecture Status
- **Stable**: Core architecture is mature and well-tested
- **Extensible**: Clean separation allows for easy feature additions
- **Documented**: Comprehensive documentation for users and developers
- **Backward Compatible**: All existing functionality preserved

### Latest Enhancement Details (Hostname Support)

#### parse_metadata Function Enhancement
The `parse_metadata()` function has been updated to include hostname support:

**Function Signature:**
```python
def parse_metadata(metadata_arg, tap_ip, vm_ip, hostname=None):
```

**Key Changes:**
1. Added optional `hostname` parameter to function signature
2. Hostname is automatically injected into the `network_config` object
3. If hostname is None, it defaults to the VM name in the main function
4. The network_config structure now includes three fields: `ip`, `gateway`, and `hostname`

**Example Network Config Output:**
```json
{
  "network_config": {
    "ip": "10.0.1.1",
    "gateway": "192.168.1.1", 
    "hostname": "web-server"
  }
}
```

**Usage Examples:**
```bash
# Uses VM name as hostname
./fcm create --name web-vm --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1

# Custom hostname
./fcm create --name vm1 --hostname production-nginx --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
```

This enhancement ensures all VMs have proper hostname configuration available through the MMDS interface, improving VM identification and configuration management.

---

This context document provides all necessary information for future development sessions, including the complete architecture, current implementation details, recent enhancements, potential future directions, and critical external documentation references.