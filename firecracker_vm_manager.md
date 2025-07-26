# Firecracker VM Manager

A Python script to create and destroy Firecracker microVMs with automatic supervisord integration and network configuration.

## Setup

### 1. Create Python Environment

```bash
# Create a virtual environment
python3 -m venv firecracker-env

# Activate the environment
source firecracker-env/bin/activate  # On Linux/macOS
# or
firecracker-env\Scripts\activate     # On Windows
```

### 2. Install Dependencies

```bash
pip install requests requests-unixsocket
```

### 3. Make Script Executable

```bash
chmod +x firecracker_vm_manager.py
```

### 4. Configure Environment (Optional)

Create a `.env` file in the same directory as the script to set default configuration values:

```bash
# .env file example
KERNEL_PATH=vmlinux
CPUS=1
MEMORY=128
```

**Note:** Command line arguments override values in the .env file.

## Prerequisites

Before using this script, ensure you have:

1. **Firecracker binary** installed at `/usr/sbin/firecracker`
2. **Supervisor daemon** running on the system
3. **Root/sudo access** for network configuration and supervisor management
4. **Kernel image** (vmlinux file)
5. **Root filesystem** image (ext4 file)

**Note:** The script automatically manages Firecracker processes via supervisord, creates/removes TAP devices, and handles all network configuration.

## Usage

The script supports two main actions: **create** and **destroy** VMs.

### Create a VM

```bash
./firecracker_vm_manager.py create \
  --name myvm \
  --kernel vmlinux \
  --rootfs rootfs.ext4 \
  --tap-device tap0 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2
```

**Note:** The socket path defaults to `/tmp/myvm.sock` based on the VM name. You can override it with `--socket /custom/path.sock` if needed.

### Create a VM with Custom Resources

```bash
./firecracker_vm_manager.py create \
  --name myvm \
  --kernel vmlinux \
  --rootfs rootfs.ext4 \
  --tap-device tap0 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --cpus 2 \
  --memory 512
```

### Destroy a VM

```bash
./firecracker_vm_manager.py destroy \
  --name myvm \
  --tap-device tap0 \
  --mmds-tap tap1
```

### Get Help

```bash
./firecracker_vm_manager.py --help
```

## Parameters

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--name` | VM name (used for supervisor config) | `myvm` |

### Required for CREATE Action

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--kernel` | Path to kernel image (can be set in .env as KERNEL_PATH) | `vmlinux` |
| `--rootfs` | Path to rootfs device | `rootfs.ext4` |
| `--cpus` | Number of vCPUs (can be set in .env as CPUS) | `2` |
| `--memory` | Memory in MiB (can be set in .env as MEMORY) | `512` |
| `--tap-device` | TAP device name on host | `tap0` |
| `--tap-ip` | IP address for TAP device on host | `172.16.0.1` |
| `--vm-ip` | IP address for VM (guest) | `172.16.0.2` |

### Required for DESTROY Action

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--tap-device` | TAP device name to remove | `tap0` |

### Optional for DESTROY Action

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--mmds-tap` | MMDS TAP device name to remove (use if VM was created with metadata) | `tap1` |

### Optional Parameters (CREATE only)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--socket` | `/tmp/<vm_name>.sock` | Path to Firecracker API socket |
| `--metadata` | none | JSON metadata for MMDS (provide JSON string or file path starting with @) |
| `--mmds-tap` | none | TAP device name for MMDS interface (enables MMDS with network config) |
| `--foreground` | false | Run Firecracker in foreground for debugging (skips supervisor) |

## Configuration File

The script supports a `.env` configuration file for setting default values that apply to all VMs. This includes the kernel path and resource settings (CPU and memory) which are all required for VM creation.

### .env File Format

```bash
# Required for VM creation
KERNEL_PATH=vmlinux
CPUS=1
MEMORY=128
```

### Configuration Priority

1. **Command line arguments** (highest priority)
2. **Environment file (.env)** values
3. **Built-in defaults** (lowest priority)

## Metadata Service (MMDS)

The script supports Firecracker's Metadata Service (MMDS) which allows VMs to access configuration data via HTTP requests to a special IP address.

### Metadata Features

- **User-provided metadata**: Custom JSON data via `--metadata` parameter
- **Automatic network configuration**: Always includes `network_config` object with VM and gateway IPs
- **Two input methods**: Direct JSON string or file reference with `@filename`

### Metadata Structure

All VMs automatically receive a `network_config` object containing:
```json
{
  "network_config": {
    "ip": "172.16.0.2",     // VM IP address
    "gateway": "172.16.0.1"  // TAP device IP (gateway)
  }
}
```

### Usage Examples

**MMDS with network config only:**
```bash
./firecracker_vm_manager.py create \
  --name myvm \
  --rootfs rootfs.ext4 \
  --tap-device tap0 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --mmds-tap tap1
```

**MMDS with custom metadata:**
```bash
./firecracker_vm_manager.py create \
  --name myvm \
  --rootfs rootfs.ext4 \
  --tap-device tap0 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --metadata '{"app": {"name": "web-server", "version": "1.2.3"}}' \
  --mmds-tap tap1
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
./firecracker_vm_manager.py create \
  --name myvm \
  --rootfs rootfs.ext4 \
  --tap-device tap0 \
  --tap-ip 172.16.0.1 \
  --vm-ip 172.16.0.2 \
  --metadata @metadata.json \
  --mmds-tap tap1
```

### Network Interface Configuration

When `--mmds-tap` is provided, the script automatically configures two network interfaces:

- **eth0**: Primary network interface for regular VM traffic (uses `--tap-device`)
- **mmds0**: Dedicated interface for MMDS (Metadata Service) access (uses `--mmds-tap`)

Each interface requires its own dedicated TAP device on the host for proper network isolation.

### Accessing Metadata from VM

Inside the VM, metadata is accessible via HTTP requests to `169.254.169.254` through the `mmds0` interface:

#### 1. Setup Network Interface in Guest

The VM will see two network interfaces when metadata is configured:
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

#### 3. Debugging MMDS Issues

If you can't connect to MMDS, check these steps:

```bash
# 1. Verify interfaces are present
ip link show

# 2. Verify MMDS interface is up
ip link show mmds0

# 3. Check routing table
ip route show | grep 169.254.169.254

# 4. Test basic connectivity
ping -c 1 169.254.169.254

# 5. Check if MMDS is responding
curl -v http://169.254.169.254/
```

**Common Issues:**
- Using wrong IP address (should be `169.254.169.254`, not `169.254.170.2`)
- MMDS interface not brought up (`ip link set mmds0 up`)
- Missing route (`ip route add 169.254.169.254 dev mmds0`)
- Using wrong interface name in route (should be `mmds0`, not `eth1`)

## Example Workflow

### Creating a VM with .env Configuration

1. **Set up .env file:**
   ```bash
   cat > .env << EOF
   KERNEL_PATH=vmlinux
   CPUS=2
   MEMORY=512
   EOF
   ```

2. **Create and start a VM (kernel, CPU, and memory automatically loaded from .env):**
   ```bash
   ./firecracker_vm_manager.py create \
     --name myvm \
     --rootfs rootfs.ext4 \
     --tap-device tap0 \
     --tap-ip 172.16.0.1 \
     --vm-ip 172.16.0.2
   ```

### Creating a VM with Command Line Override

1. **Override .env values with command line:**
   ```bash
   ./firecracker_vm_manager.py create \
     --name myvm \
     --kernel custom-kernel.bin \
     --cpus 4 \
     --memory 1024 \
     --rootfs rootfs.ext4 \
     --tap-device tap0 \
     --tap-ip 172.16.0.1 \
     --vm-ip 172.16.0.2
   ```

2. **Expected output:**
   ```
   Creating VM: myvm...
   ✓ Supervisor config created: /etc/supervisor/conf.d/myvm.conf
   ✓ Supervisor configuration reloaded
   Configuring Firecracker VM...
   ✓ Machine config set: 1 vCPUs, 128 MiB RAM
   ✓ Boot source set: vmlinux
   ✓ Rootfs set: rootfs.ext4
   Creating TAP device: tap0
   ✓ TAP device tap0 created
   ✓ IP 172.16.0.1/32 configured on tap0
   ✓ tap0 is up
   ✓ Route for 172.16.0.2 via tap0 added
   ✓ Network interface set: tap0
   ✓ MicroVM started successfully!
   ```

### Creating a VM in Foreground Mode (for debugging)

1. **Create and start a VM in foreground:**
   ```bash
   ./firecracker_vm_manager.py create \
     --name myvm \
     --kernel vmlinux \
     --rootfs rootfs.ext4 \
     --tap-device tap0 \
     --tap-ip 172.16.0.1 \
     --vm-ip 172.16.0.2 \
     --foreground
   ```

2. **Expected output:**
   ```
   Creating VM: myvm...
   Creating TAP device: tap0
   ✓ TAP device tap0 created
   ✓ IP 172.16.0.1/32 configured on tap0
   ✓ tap0 is up
   ✓ Route for 172.16.0.2 via tap0 added
   Starting Firecracker in foreground mode...
   Command: /usr/sbin/firecracker --id myvm --api-sock /tmp/myvm.sock
   Configuring Firecracker VM...
   ✓ Machine config set: 1 vCPUs, 128 MiB RAM
   ✓ Boot source set: vmlinux
   ✓ Rootfs set: rootfs.ext4
   ✓ Network interface set: tap0
   ✓ MicroVM started successfully!

   ✓ VM running in foreground mode. Press Ctrl+C to stop and cleanup.
   ```

3. **When you press Ctrl+C:**
   ```
   ^C
   Received interrupt signal

   Cleaning up...
   ✓ TAP device tap0 removed (routes automatically removed)
   ✓ Socket file removed: /tmp/myvm.sock
   ```

### Destroying a VM

1. **Stop and destroy a VM without metadata:**
   ```bash
   ./firecracker_vm_manager.py destroy \
     --name myvm \
     --tap-device tap0
   ```

2. **Stop and destroy a VM with metadata (includes MMDS TAP cleanup):**
   ```bash
   ./firecracker_vm_manager.py destroy \
     --name myvm \
     --tap-device tap0 \
     --mmds-tap tap1
   ```

3. **Expected output:**
   ```
   Destroying VM: myvm...
   ✓ Socket file removed
   ✓ TAP device tap0 removed (routes automatically removed)
   ✓ TAP device tap1 removed (routes automatically removed)
   ✓ Supervisor config removed: /etc/supervisor/conf.d/myvm.conf
   ✓ Supervisor configuration reloaded
   ✓ VM myvm destroyed successfully!
   ```

## What the Script Does

### CREATE Action

The script performs these operations in sequence:

1. **Check socket availability** - Ensures socket is not in use
2. **Clean up stale socket** - Removes existing socket file if present
3. **Create supervisor config** - Generates supervisord configuration for VM (skipped in --foreground mode)
4. **Start Firecracker process** - Uses supervisor to launch Firecracker daemon (or runs in foreground for debugging)
5. **Set machine configuration** - Configures CPU and memory
6. **Set boot source** - Points to kernel image with boot arguments
7. **Set rootfs drive** - Configures the root filesystem
8. **Setup TAP device** - Creates TAP device if needed, configures IP and routing
9. **Set network interface** - Links host TAP device to guest eth0
10. **Start microVM** - Initiates the virtual machine

### DESTROY Action

The script performs these cleanup operations:

1. **Check socket status** - Ensures VM is not running
2. **Remove socket file** - Cleans up API socket
3. **Remove TAP device** - Deletes TAP interface (routes automatically removed)
4. **Remove supervisor config** - Deletes supervisord configuration file
5. **Reload supervisor** - Updates supervisor to stop managing the VM process

### Network Setup Details

The script automatically handles network configuration:
- Creates TAP device if it doesn't exist
- Assigns the specified IP address to the TAP device (/32 subnet)
- Brings the TAP device up
- Installs a host route for the VM IP via the TAP device
- Configures the Firecracker network interface
- On destroy: removes TAP device (which automatically removes associated routes)

## Troubleshooting

### Common Issues

**Socket not found:**
```
Error: Socket file /tmp/myvm.sock does not exist
```
- Ensure Firecracker is running with the correct socket path

**File not found:**
```
Error: Kernel file vmlinux does not exist
```
- Verify kernel and rootfs file paths are correct

**Permission denied:**
```
Request failed: [Errno 13] Permission denied
```
- Check socket file permissions
- Ensure TAP device is properly configured

**API call failures:**
- Verify Firecracker is in the correct state (not already configured/running)
- Check Firecracker logs for detailed error messages

### Debug Mode

For debugging, you can modify the script to print more verbose output or check the Firecracker logs directly.

## API Reference

The script uses these Firecracker API endpoints:

- `GET /` - Check if Firecracker is listening on socket
- `PUT /machine-config` - Set CPU and memory  
- `PUT /boot-source` - Set kernel and boot arguments
- `PUT /drives/rootfs` - Set root filesystem
- `PUT /network-interfaces/eth0` - Configure network
- `PUT /actions` - Start the VM

### Supervisor Integration

The script creates supervisor configuration files with this template:
```ini
[program:myvm]
command=/usr/sbin/firecracker --id myvm --api-sock /tmp/myvm.sock
stdout_logfile=/var/log/myvm.log
stderr_logfile=/var/log/myvm.error.log
autostart=true
```