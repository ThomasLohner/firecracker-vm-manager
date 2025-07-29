# Firecracker VM Manager

A complete tool for managing Firecracker microVMs with automatic image-based rootfs building, network configuration, and TAP device auto-generation.

## Installation

Download the latest `fcm` binary from the [releases page](https://github.com/your-repo/firecracker-vm-manager/releases) and place it in your PATH:

```bash
# Download and install fcm binary
curl -L -o fcm https://github.com/your-repo/firecracker-vm-manager/releases/latest/download/fcm
chmod +x fcm
sudo mv fcm /usr/local/bin/
```

### Development Version

For development purposes, you can use the `fcm.sh` script directly from the source repository. This script handles Python virtual environment and dependencies automatically:

```bash
# Clone the repository and use fcm.sh for development
git clone https://github.com/your-repo/firecracker-vm-manager.git
cd firecracker-vm-manager
./fcm.sh create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2
```

## Quick Start

Just place kernel files in `/var/lib/firecracker/kernels/` and base images in `/var/lib/firecracker/images/`, then:

```bash
# Basic VM creation
fcm create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

# List VMs
fcm list

# VM lifecycle
fcm stop --name myvm
fcm start --name myvm
fcm destroy --name myvm
```

## Setup

### Prerequisites
- Firecracker binary at `/usr/sbin/firecracker`
- Supervisor daemon running
- Root/sudo access for network configuration
- `resize2fs` utility

### Directory Structure (Auto-Created)
```
/var/lib/firecracker/
├── kernels/     # Kernel files
├── images/      # Base image templates  
├── rootfs/      # VM-specific rootfs files
└── cache/       # VM configuration cache
```

For non-root usage: `sudo chown -R $USER:$USER /var/lib/firecracker`

### Configuration File (optional)
Default location: `/etc/firecracker.env` (override with `--config` parameter)

```bash
KERNEL_PATH=/var/lib/firecracker/kernels  # Kernel files directory
KERNEL=vmlinux-6.1.141                    # Default kernel filename
IMAGES_PATH=/var/lib/firecracker/images   # Base image templates
IMAGE=alpine.ext4                         # Default image filename
ROOTFS_PATH=/var/lib/firecracker/rootfs   # VM-specific rootfs files
ROOTFS_SIZE=1G                            # Default rootfs size
CPUS=1                                    # Default CPU count
MEMORY=1024                               # Default memory (MiB)
SOCKET_PATH_PREFIX=/var/run/firecracker   # Socket directory
```

### Getting Files
See main [README.md](README.md) for detailed instructions on:
- Downloading kernel images (Section 3)
- Creating base images (Section 4)

## Usage

### List Available Resources
```bash
fcm kernels    # List kernel files
fcm images     # List image files
```

### Basic Operations
```bash
# Create VM with auto-generated TAP devices
fcm create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

# With specific TAP devices
fcm create --name myvm --tap-device tap5 --mmds-tap tap6 --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

# List VMs (running and stopped)
fcm list

# VM lifecycle (preserves configuration)
fcm stop --name myvm      # Stops VM, keeps TAP/cache
fcm start --name myvm     # Restarts from cache
fcm restart --name myvm   # Stop + start

# Destroy VM (permanent deletion)
fcm destroy --name myvm                   # With confirmation
fcm destroy --name myvm --force-destroy   # Skip confirmation
```

### Help
```bash
fcm --help
```

## Parameters

### Required (All Actions)
- `--name`: VM identifier

### Required (CREATE)
- `--kernel`: Kernel filename (in KERNEL_PATH, or set KERNEL in config)
- `--image`: Image filename (in IMAGES_PATH, or set IMAGE in config)
- `--rootfs-size`: Rootfs size (1G, 512M, etc., or set ROOTFS_SIZE in config)
- `--cpus`: vCPUs (or set CPUS in config)
- `--memory`: Memory in MiB (or set MEMORY in config)
- `--tap-ip`: Host TAP device IP
- `--vm-ip`: VM guest IP

### Optional
- `--config`: Configuration file path (default: /etc/firecracker.env)
- `--tap-device`, `--mmds-tap`: Explicit TAP devices (auto-generated if omitted)
- `--hostname`: VM hostname (defaults to VM name)
- `--metadata`: JSON metadata string or @file
- `--foreground`: Debug mode (no supervisor)
- `--force-rootfs`: Overwrite existing rootfs
- `--force-destroy`: Skip destroy confirmation

## Key Features

### Configuration Priority
1. Command line arguments (highest)
2. Configuration file values (default: /etc/firecracker.env)
3. Built-in defaults (lowest)

### Image-Based Rootfs Building
- Base images in `IMAGES_PATH` serve as templates
- VM-specific rootfs built as `<vm_name>.ext4` in `ROOTFS_PATH`  
- Automatic `resize2fs` resizing to specified size
- Force overwrite protection (`--force-rootfs` to override)

### TAP Device Auto-Generation
- Scans existing devices, finds next available (tap0, tap1, etc.)
- Session tracking prevents conflicts
- Two devices per VM: main interface + MMDS

### VM Configuration Caching
- Automatic caching to `/var/lib/firecracker/cache/<vm_name>.json`
- Enables stop/start workflow without losing settings
- Stores all VM configuration: kernel, rootfs, TAP devices, IPs, resources

### Metadata Service (MMDS)
- Always configured with automatic network configuration injection
- Two interfaces: eth0 (main) + mmds0 (metadata at 169.254.169.254)
- Custom metadata via `--metadata` (JSON string or @file)
- Automatic hostname injection from `--hostname` or VM name

## Advanced Usage

### Custom Metadata Example
```bash
# With custom metadata and hostname
fcm create --name myvm --hostname web-server --image alpine.ext4 --rootfs-size 1G \
  --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 \
  --metadata '{"app": {"name": "web-server", "version": "1.2.3"}}'

# From file
echo '{"app": {"name": "web-server"}}' > metadata.json
fcm create --name myvm --image alpine.ext4 --rootfs-size 1G \
  --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --metadata @metadata.json
```

### Accessing Metadata in VM
```bash
# Setup mmds0 interface in guest
sudo ip link set mmds0 up
sudo ip route add 169.254.169.254 dev mmds0

# Get metadata (IMDSv2 style)
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-metadata-token-ttl-seconds: 21600")
curl -H "X-metadata-token: $TOKEN" "http://169.254.169.254/network_config"
```

### List Output Example
```
VM Name | Internal IP | CPUs | Memory  | Rootfs     | Kernel     | TAP Interface (IP) | MMDS TAP
--------|-------------|------|---------|------------|------------|--------------------|---------
vm1     | 10.4.17.1   | 1    | 2048 MiB| alpine.ext4| vmlinux    | tap2 (192.168.1.1) | tap3
vm2     | 10.4.17.2   | 2    | 512 MiB | ubuntu.ext4| vmlinux    | tap4 (192.168.1.2) | tap5
```

### Debug Mode
Use `--foreground` for debugging (shows direct Firecracker output, Ctrl+C cleanup):
```bash
fcm create --name myvm --kernel vmlinux --image alpine.ext4 --rootfs-size 1G \
  --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --foreground
```

## Troubleshooting

### Common Issues
- **Permission denied**: Run with sudo or ensure proper directory permissions
- **TAP device conflicts**: Use auto-generation instead of explicit device names
- **File not found**: Verify kernel/image file paths and configuration file settings
- **No VMs found**: Check socket directory and VM status

### Logs
- **Supervisor mode**: `/var/log/<vm_name>.log` and `/var/log/<vm_name>.error.log`
- **Foreground mode**: Direct terminal output

## What It Does

### CREATE
1. Build rootfs from base image (`resize2fs` to specified size)
2. Auto-generate or validate TAP devices (main + MMDS)
3. Create supervisor config and start Firecracker process
4. Configure VM via API (CPU/memory, kernel, rootfs, network, MMDS)
5. Start microVM and cache configuration

### DESTROY
1. Check VM is stopped, load cached config, get user confirmation
2. Remove socket, TAP devices, rootfs file, supervisor config, cache
3. **⚠️ WARNING**: Permanently deletes rootfs file

### STOP/START/RESTART
- **STOP**: Stop process, remove socket, preserve TAP devices and cache
- **START**: Load cache, start process, restore configuration
- **RESTART**: Stop + start sequence

The script handles all network configuration automatically: creates TAP devices, assigns IPs, configures routes, and sets up dual interfaces (eth0 + mmds0) for each VM.