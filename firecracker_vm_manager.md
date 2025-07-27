# Firecracker VM Manager

A Python script to create, destroy, and list Firecracker microVMs with automatic supervisord integration, network configuration, and TAP device auto-generation.

## Setup

### 1. Ready to Use - Zero Configuration Required!

**The `fcm` wrapper script handles everything automatically:**

✅ **Virtual Environment**: Creates `venv/` directory if it doesn't exist  
✅ **Dependency Installation**: Automatically installs `requests` and `requests-unixsocket`  
✅ **Environment Activation**: Activates the virtual environment before execution  
✅ **Smart Detection**: Only installs missing packages, skips if already installed  

**First run** (fresh setup):
```bash
./fcm create --name myvm --rootfs disk.ext4 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2
# Output: Creating Python virtual environment...
#         Installing missing Python modules: requests requests-unixsocket
#         [VM creation proceeds...]
```

**Subsequent runs** (environment ready):
```bash
./fcm list
# No setup messages, runs immediately
```

**No manual Python environment management needed** - just run `./fcm` and it works!

### 2. Configure Environment (Optional)

Create a `.env` file in the same directory as the script to set default configuration values:

```bash
# .env file example
KERNEL_PATH=vmlinux
CPUS=1
MEMORY=128
SOCKET_PATH_PREFIX=/var/run/firecracker
```

**Note:** Command line arguments override values in the .env file.

## Prerequisites

Before using this script, ensure you have:

1. **Firecracker binary** installed at `/usr/sbin/firecracker`
2. **Supervisor daemon** running on the system
3. **Root/sudo access** for network configuration and supervisor management
4. **Kernel image** (vmlinux file)
5. **Root filesystem** image (ext4 file)

**Note:** The script automatically manages Firecracker processes via supervisord, creates/removes TAP devices, and handles all network configuration with auto-generation capabilities.

## Usage

The script supports four main actions: **create**, **destroy**, **list** VMs, and **kernels** (list available kernels).

### Create a VM (Simplest Form)

```bash
./fcm create \
  --name myvm \
  --kernel vmlinux \
  --rootfs rootfs.ext4 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2
```

This will automatically generate TAP devices (tap0 for main interface, tap1 for MMDS).

### Create a VM with Specific TAP Devices

```bash
./fcm create \
  --name myvm \
  --kernel vmlinux \
  --rootfs rootfs.ext4 \
  --tap-device tap5 \
  --mmds-tap tap6 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2
```

### Create a VM with Custom Resources

```bash
./fcm create \
  --name myvm \
  --kernel vmlinux \
  --rootfs rootfs.ext4 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --cpus 2 \
  --memory 512
```

### List Available Kernels

```bash
./fcm kernels
```

### List Running VMs

```bash
./fcm list
```

### Destroy a VM

```bash
./fcm destroy --name myvm
```

### Get Help

```bash
./fcm --help
```

## Parameters

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--name` | VM name (not required for list action) | `myvm` |

### Required for CREATE Action

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--kernel` | Kernel filename (must exist in KERNEL_PATH directory) | `vmlinux-6.1.141` |
| `--rootfs` | Path to rootfs device | `rootfs.ext4` |
| `--cpus` | Number of vCPUs (can be set in .env as CPUS) | `2` |
| `--memory` | Memory in MiB (can be set in .env as MEMORY) | `512` |
| `--tap-ip` | IP address for TAP device on host | `172.16.0.1` |
| `--vm-ip` | IP address for VM (guest) | `172.16.0.2` |

### Optional for CREATE Action

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--tap-device` | TAP device name on host (auto-generated if not specified) | `tap0` |
| `--mmds-tap` | MMDS TAP device name (auto-generated if not specified) | `tap1` |
| `--hostname` | Hostname for the VM (defaults to VM name if not specified) | `web-server` |

### Optional for DESTROY Action

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--tap-device` | TAP device name to remove (required if not using auto-discovery) | `tap0` |
| `--mmds-tap` | MMDS TAP device name to remove (required if VM was created with metadata) | `tap1` |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--socket` | `<SOCKET_PATH_PREFIX>/<vm_name>.sock` | Path to Firecracker API socket |
| `--metadata` | none | JSON metadata for MMDS (provide JSON string or file path starting with @) |
| `--foreground` | false | Run Firecracker in foreground for debugging (skips supervisor) |

## Configuration File

The script supports a `.env` configuration file for setting default values that apply to all VMs.

### .env File Format

```bash
# Required for VM creation
KERNEL_PATH=vmlinux
CPUS=1
MEMORY=128

# Socket directory configuration
SOCKET_PATH_PREFIX=/var/run/firecracker
```

### Configuration Priority

1. **Command line arguments** (highest priority)
2. **Environment file (.env)** values
3. **Built-in defaults** (lowest priority)

### Socket Path Configuration

The `SOCKET_PATH_PREFIX` environment variable controls where VM socket files are stored:
- **Default**: `/tmp`
- **Recommended**: `/var/run/firecracker` for production use
- **Auto-creation**: Directory is created automatically if it doesn't exist

### Kernel Path Configuration

The `KERNEL_PATH` environment variable must point to a directory containing kernel files:

```bash
KERNEL_PATH=/path/to/kernels
```

#### Features
- **Directory Only**: KERNEL_PATH must always be a directory path
- **Filename Selection**: Use `--kernel <filename>` to select specific kernel from the directory
- **Auto-Discovery**: Use `./fcm kernels` to see all available kernel files
- **Pattern Matching**: Automatically finds files matching: vmlinux*, bzImage*, kernel*, Image*

#### Usage Examples
```bash
# List available kernels in KERNEL_PATH directory
./fcm kernels

# Use specific kernel by filename
./fcm create --name vm1 --kernel vmlinux-6.1.141 --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
```

## TAP Device Auto-Generation

The script automatically manages TAP device creation and assignment:

### Auto-Generation Features

- **Scans existing devices**: Discovers existing `tap*` devices on the system
- **Finds next available**: Generates sequential names (tap0, tap1, tap2, etc.)
- **Session tracking**: Prevents conflicts when creating multiple VMs
- **Validation**: Checks that explicitly specified devices don't already exist

### TAP Device Behavior

**Auto-generation (recommended):**
```bash
# Creates tap0 (main) and tap1 (MMDS) automatically
./fcm create --name vm1 --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
```

**Explicit specification:**
```bash
# Uses specified devices (fails if they already exist)
./fcm create --name vm1 --tap-device tap5 --mmds-tap tap6 --rootfs disk.ext4 --tap-ip 192.168.1.1 --vm-ip 10.0.1.1
```

## Metadata Service (MMDS)

The script always configures Firecracker's Metadata Service (MMDS) with automatic network configuration injection.

### Metadata Features

- **Automatic network configuration**: Always includes `network_config` object with VM and gateway IPs
- **Two network interfaces**: Primary (eth0) and dedicated MMDS (mmds0) interfaces
- **User-provided metadata**: Custom JSON data via `--metadata` parameter
- **Two input methods**: Direct JSON string or file reference with `@filename`

### Metadata Structure

All VMs automatically receive a `network_config` object containing:
```json
{
  "network_config": {
    "ip": "172.16.0.2",     // VM IP address
    "gateway": "172.16.0.1",  // TAP device IP (gateway)
    "hostname": "myvm"       // VM hostname (defaults to VM name)
  }
}
```

### Usage Examples

**Basic VM (network config only):**
```bash
./fcm create \
  --name myvm \
  --rootfs rootfs.ext4 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2
```

**With custom metadata and hostname:**
```bash
./fcm create \
  --name myvm \
  --hostname web-server \
  --rootfs rootfs.ext4 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --metadata '{"app": {"name": "web-server", "version": "1.2.3"}}'
```

**From file:**
```bash
# Create metadata.json
cat > metadata.json << EOF
{
  "app": {
    "name": "web-server",
    "version": "1.2.3",
    "config": {
      "port": 8080,
      "debug": false
    }
  }
}
EOF

# Use metadata file
./fcm create \
  --name myvm \
  --rootfs rootfs.ext4 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --metadata @metadata.json
```

### Network Interface Configuration

The script automatically configures two network interfaces for all VMs:

- **eth0**: Primary network interface for regular VM traffic (uses main TAP device)
- **mmds0**: Dedicated interface for MMDS (Metadata Service) access (uses MMDS TAP device)

Each interface uses its own dedicated TAP device on the host for proper network isolation.

### Accessing Metadata from VM

Inside the VM, metadata is accessible via HTTP requests to `169.254.169.254` through the `mmds0` interface:

#### 1. Setup Network Interface in Guest

The VM will see two network interfaces:
- **eth0**: Primary network interface (configure with your VM IP)
- **mmds0**: MMDS interface (used for metadata access)

First, bring up the MMDS interface and add the route:
```bash
# Bring up the MMDS interface
sudo ip link set mmds0 up

# Add route to MMDS IP via MMDS interface
sudo ip route add 169.254.169.254 dev mmds0
```

#### 2. Access Metadata

```bash
# Get session token (IMDSv2 style)
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-metadata-token-ttl-seconds: 21600")

# Access network configuration
curl -H "X-metadata-token: $TOKEN" \
  "http://169.254.169.254/network_config"

# Access custom metadata
curl -H "X-metadata-token: $TOKEN" \
  "http://169.254.169.254/app/name"
```

## VM Listing and Management

The `list` action provides comprehensive information about running VMs by connecting to their Firecracker API sockets.

### List Command Features

- **Auto-discovery**: Scans socket directory for running VMs
- **Rich information**: Shows VM configuration, network details, and resource allocation
- **Real-time data**: Queries live VMs via API calls

### List Output Example

```bash
./fcm list
```

```
VM Name | Internal IP | CPUs | Memory  | Rootfs          | Kernel          | TAP Interface (IP) | MMDS TAP
--------|-------------|------|---------|-----------------|-----------------|--------------------|---------
vm1     | 10.4.17.1   | 1    | 2048 MiB| vm2-alpine.ext4 | vmlinux-6.1.141 | tap2 (192.168.1.1) | tap3
vm2     | 10.4.17.2   | 2    | 512 MiB | ubuntu.ext4     | vmlinux         | tap4 (192.168.1.2) | tap5
```

### Information Displayed

| Column | Description | Source |
|--------|-------------|--------|
| VM Name | VM identifier | Socket filename |
| Internal IP | VM's guest IP address | MMDS network_config |
| CPUs | Number of virtual CPUs | VM config API |
| Memory | RAM allocation | VM config API |
| Rootfs | Root filesystem filename | VM config API |
| Kernel | Kernel image filename | VM config API |
| TAP Interface (IP) | Main interface device and host IP | VM config + system query |
| MMDS TAP | MMDS interface device name | VM config API |

## Example Workflows

### Creating VMs with Auto-Generation

1. **Set up .env file:**
   ```bash
   cat > .env << EOF
   KERNEL_PATH=/path/to/kernels
   CPUS=2
   MEMORY=512
   SOCKET_PATH_PREFIX=/var/run/firecracker
   EOF
   ```

2. **Check available kernels:**
   ```bash
   ./fcm kernels
   # Output shows available kernel files:
   # Available kernels in /path/to/kernels:
   # vmlinux-6.1.141     15.2 MB  2024-01-15 10:30
   # vmlinux-5.15.0      14.8 MB  2024-01-10 09:45
   ```

3. **Create first VM (gets tap0/tap1):**
   ```bash
   ./fcm create \
     --name vm1 \
     --hostname alpine-vm \
     --kernel vmlinux-6.1.141 \
     --rootfs alpine.ext4 \
     --tap-ip 192.168.1.1 \
     --vm-ip 10.0.1.1
   ```

4. **Create second VM (gets tap2/tap3):**
   ```bash
   ./fcm create \
     --name vm2 \
     --hostname ubuntu-server \
     --kernel vmlinux-5.15.0 \
     --rootfs ubuntu.ext4 \
     --tap-ip 192.168.1.2 \
     --vm-ip 10.0.1.2
   ```

5. **List running VMs:**
   ```bash
   ./fcm list
   ```

6. **Destroy VMs:**
   ```bash
   ./fcm destroy --name vm1
   ./fcm destroy --name vm2
   ```

### Creating VMs in Foreground Mode (for debugging)

1. **Create and start a VM in foreground:**
   ```bash
   ./fcm create \
     --name myvm \
     --kernel vmlinux-6.1.141 \
     --rootfs rootfs.ext4 \
     --tap-ip 172.16.0.1 \
     --vm-ip 172.16.0.2 \
     --foreground
   ```

2. **Expected output:**
   ```
   Creating VM: myvm...
   Auto-generated TAP device: tap0
   Auto-generated MMDS TAP device: tap1
   Creating TAP device: tap0
   ✓ TAP device tap0 created
   ✓ IP 172.16.0.1/32 configured on tap0
   ✓ tap0 is up
   ✓ Route for 172.16.0.2 via tap0 added
   Starting Firecracker in foreground mode...
   Command: /usr/sbin/firecracker --id myvm --api-sock /var/run/firecracker/myvm.sock
   Configuring Firecracker VM...
   ✓ Machine config set: 1 vCPUs, 128 MiB RAM
   ✓ Boot source set: vmlinux
   ✓ Rootfs set: rootfs.ext4
   ✓ Primary network interface set: eth0 -> tap0
   ✓ MMDS network interface set: mmds0 -> tap1
   ✓ MMDS interface configured
   ✓ MMDS metadata configured
   ✓ MicroVM started successfully!

   ✓ VM running in foreground mode. Press Ctrl+C to stop and cleanup.
   ```

3. **When you press Ctrl+C:**
   ```
   ^C
   Received interrupt signal

   Cleaning up...
   ✓ TAP device tap0 removed (routes automatically removed)
   ✓ TAP device tap1 removed (routes automatically removed)
   ✓ Socket file removed: /var/run/firecracker/myvm.sock
   ```

## What the Script Does

### CREATE Action

The script performs these operations in sequence:

1. **Load configuration** - Read .env file and process arguments
2. **Auto-generate TAP devices** - Find available device names or validate explicit ones
3. **Check socket availability** - Ensures socket is not in use
4. **Clean up stale socket** - Removes existing socket file if present
5. **Create supervisor config** - Generates supervisord configuration for VM (skipped in --foreground mode)
6. **Start Firecracker process** - Uses supervisor to launch Firecracker daemon (or runs in foreground for debugging)
7. **Set machine configuration** - Configures CPU and memory
8. **Set boot source** - Points to kernel image with boot arguments
9. **Set rootfs drive** - Configures the root filesystem
10. **Setup TAP devices** - Creates both main and MMDS TAP devices with IP configuration
11. **Set network interfaces** - Links host TAP devices to guest eth0 and mmds0
12. **Configure MMDS** - Sets up metadata service with network configuration
13. **Start microVM** - Initiates the virtual machine

### DESTROY Action

The script performs these cleanup operations:

1. **Check socket status** - Ensures VM is not running
2. **Remove socket file** - Cleans up API socket
3. **Remove TAP devices** - Deletes both main and MMDS TAP interfaces (routes automatically removed)
4. **Remove supervisor config** - Deletes supervisord configuration file
5. **Reload supervisor** - Updates supervisor to stop managing the VM process

### LIST Action

The script performs these discovery operations:

1. **Scan socket directory** - Find all .sock files in configured directory
2. **Test socket connectivity** - Check which VMs are actually running
3. **Query VM configurations** - Get details via /vm/config API endpoint
4. **Extract system information** - Get TAP device IP addresses from host
5. **Format table output** - Display comprehensive VM information

### Network Setup Details

The script automatically handles network configuration:
- Creates TAP devices if they don't exist
- Assigns the specified IP addresses to TAP devices (/32 subnet)
- Brings TAP devices up
- Installs host routes for VM IPs via TAP devices
- Configures Firecracker network interfaces
- Sets up MMDS service with dedicated interface
- On destroy: removes TAP devices (which automatically removes associated routes)

## Troubleshooting

### Common Issues

**Socket directory issues:**
```
Warning: Could not create socket directory /var/run/firecracker: Permission denied
```
- Ensure write permissions to socket directory
- Run with sudo if using system directories

**TAP device conflicts:**
```
Error: TAP device 'tap0' already exists on the system
```
- Use auto-generation instead of explicit device names
- Or specify different device names

**File not found:**
```
Error: Kernel file vmlinux does not exist
```
- Verify kernel and rootfs file paths are correct
- Check .env file configuration

**Permission denied:**
```
Request failed: [Errno 13] Permission denied
```
- Check socket file permissions
- Ensure TAP device configuration permissions
- Run with appropriate privileges

**VM discovery issues:**
```
No running VMs found.
```
- Check socket directory configuration
- Verify VMs are actually running
- Check socket file permissions

### Debug Mode

For debugging, use the `--foreground` option to see direct Firecracker output and easier termination with Ctrl+C.

### Log Locations

- **Supervisor mode**: `/var/log/<vm_name>.log` and `/var/log/<vm_name>.error.log`
- **Foreground mode**: Direct terminal output

## API Reference

The script uses these Firecracker API endpoints:

### VM Management
- `GET /` - Check if Firecracker is listening on socket
- `GET /vm/config` - Get complete VM configuration (used by list action)
- `PUT /machine-config` - Set CPU and memory  
- `PUT /boot-source` - Set kernel and boot arguments
- `PUT /drives/rootfs` - Set root filesystem
- `PUT /network-interfaces/eth0` - Configure primary network interface
- `PUT /network-interfaces/mmds0` - Configure MMDS network interface
- `PUT /mmds/config` - Configure MMDS interface access
- `PUT /mmds` - Set metadata content
- `GET /mmds` - Get metadata content (used by list action for internal IP)
- `PUT /actions` - Start the VM

### Supervisor Integration

The script creates supervisor configuration files with this template:
```ini
[program:myvm]
command=/usr/sbin/firecracker --id myvm --api-sock /var/run/firecracker/myvm.sock
stdout_logfile=/var/log/myvm.log
stderr_logfile=/var/log/myvm.error.log
autostart=true
```

## Advanced Features

### Session-Based TAP Device Tracking

The script maintains session state to prevent TAP device conflicts:
- Tracks devices allocated during the current session
- Prevents duplicate allocation within the same script execution
- Validates that explicitly specified devices are available

### Automatic Directory Management

Socket directories are automatically created with proper error handling:
- Creates parent directories as needed
- Handles permission issues gracefully
- Provides clear feedback on directory creation

### Comprehensive VM Discovery

The list feature provides production-ready VM monitoring:
- Real-time configuration querying
- Network interface mapping
- System-level IP address resolution
- Graceful handling of offline or inaccessible VMs