# Firecracker VM Manager

A complete tool for managing [Firecracker microVMs](https://firecracker-microvm.github.io) with automatic image-based rootfs building, network configuration, and TAP device auto-generation.

## Installation

Download the latest `fcm` binary from the [releases page](https://github.com/ThomasLohner/firecracker-vm-manager/releases/) and place it in your PATH:

```bash
# Download and install fcm binary
curl -L -o fcm https://github.com/ThomasLohner/firecracker-vm-manager/releases/download/v1.1.0/fcm-v1.1.0-Ubuntu_24_04_x86.tgz
tar xfz fcm-v1.1.0-Ubuntu_24_04_x86.tgz
sudo mv fcm-v1.1.0 /usr/local/bin/fcm
```

### Development Version

For development purposes, you can use the `fcm.sh` script directly from the source repository. This script handles Python virtual environment and dependencies automatically:

```bash
# Clone the repository and use fcm.sh for development
git clone https://github.com/ThomasLohner/firecracker-vm-manager.git
cd firecracker-vm-manager
./fcm.sh create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2
```

### Binary release for easy distribution
The [releases](https://github.com/ThomasLohner/firecracker-vm-manager/releases/) include a `fcm` binary build on Ubuntu 24.04 for easy distribution. You can build your own version with a single comand using tools like [Nuitka](https://nuitka.net):
```bash
git clone https://github.com/ThomasLohner/firecracker-vm-manager.git
cd firecracker-vm-manager
pip3 install nuitka
nuitka --onefile firecracker-vm-manager.py
```

## Why Python?

Firecracker VM Manager is written in Python for three key reasons:

1. **Learning Journey**: This tool started as an exploration project to understand how Firecracker works internally. Python's
interactive development and clear syntax made it perfect for experimenting with the API and understanding VM lifecycle
management.

2. **Easy Binary Distribution**: Python's ecosystem ([PyInstaller](https://pyinstaller.org/en/stable/), [Nuitka](https://nuitka.net)) makes it trivial to create self-contained binaries
for distribution, eliminating dependency management for end users while keeping development simple.

3. **Rapid Development & Maintenance**: Python's readable syntax and rich standard library enabled rapid prototyping and
iterative development, while the modular architecture ensures long-term maintainability as the tool evolved from a learning
experiment to production ready management system.

The result is a robust, maintainable tool that feels natural for both development and production use, with the flexibility
  to evolve alongside Firecracker's API changes.

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
- `--tap-device`, `--mmds-tap`: Explicit TAP devices (auto-generated if omitted in internal mode)
- `--hostname`: VM hostname (defaults to VM name)
- `--metadata`: JSON metadata string or @file
- `--foreground`: Debug mode (no supervisor)
- `--force-rootfs`: Overwrite existing rootfs
- `--force-destroy`: Skip destroy confirmation
- `--networkdriver`: Network mode - `internal` (default, manages TAP devices) or `external` (uses existing TAP devices)
- `--version`, `-v`: Show version information

### External Network Driver Mode

When using `--networkdriver external`, the system uses existing TAP devices and network configuration instead of creating/managing them. This mode requires:

**Mandatory Parameters:**
- `--tap-device`: Name of existing TAP device (must already exist)
- `--tap-ip`: IP address (must already be assigned to the TAP device)
- `--mmds-tap`: Name of existing MMDS TAP device (must already exist)
- `--vm-ip`: VM IP address (must have a route via the TAP device)

**Pre-Creation Validation:**
- TAP devices exist on the system
- TAP device has the specified IP address assigned
- Host route exists for VM IP via TAP device

**Behavior Differences:**
- **CREATE**: Validates existing network setup, skips TAP/route creation
- **DESTROY**: Preserves TAP devices and routes (only removes VM-specific resources)
- **LIST**: Shows "external" in Network Driver column

**Example:**
```bash
# Setup existing TAP devices first (manual setup)
sudo ip tuntap add tap10 mode tap
sudo ip addr add 192.168.10.1/32 dev tap10
sudo ip link set tap10 up
sudo tuntap add tap11 mode tap
sudo ip link set tap11 up
sudo ip route add 192.168.10.2/32 dev tap10

# Create VM using external network mode
fcm create --name myvm --networkdriver external \
  --tap-device tap10 --tap-ip 192.168.10.1 \
  --mmds-tap tap11 --vm-ip 192.168.10.2 \
  --kernel vmlinux --image alpine.ext4 --rootfs-size 1G
```

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

### TAP Device Management
- **Internal Mode (default)**: Auto-generation by scanning existing devices, finds next available (tap0, tap1, etc.)
- Session tracking prevents conflicts
- Two devices per VM: main interface + MMDS
- **External Mode**: Uses existing TAP devices without creating/removing them

### VM Configuration Caching
- Automatic caching to `/var/lib/firecracker/cache/<vm_name>.json`
- Enables stop/start workflow without losing settings
- Stores all VM configuration: kernel, rootfs, TAP devices, IPs, resources, network driver mode

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
VM Name | State   | Internal IP | CPUs | Memory   | Rootfs      | Base Image  | Kernel  | TAP Interface (IP) | MMDS TAP | Network Driver
--------|---------|-------------|------|----------|-------------|-------------|---------|--------------------|---------|--------------
vm1     | running | 10.4.17.1   | 1    | 2048 MiB | alpine.ext4 | alpine.ext4 | vmlinux | tap2 (192.168.1.1) | tap3     | internal
vm2     | stopped | 10.4.17.2   | 2    | 512 MiB  | ubuntu.ext4 | ubuntu.ext4 | vmlinux | tap4 (192.168.1.2) | tap5     | external
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
1. Validate network setup (external mode) or prepare TAP devices (internal mode)
2. Build rootfs from base image (`resize2fs` to specified size)
3. Setup/validate TAP devices based on network driver mode
4. Create supervisor config and start Firecracker process
5. Configure VM via API (CPU/memory, kernel, rootfs, network, MMDS)
6. Start microVM and cache configuration (including network driver mode)

### DESTROY
1. Check VM is stopped, load cached config, get user confirmation
2. Remove VM-specific resources based on network driver mode:
   - **Internal mode**: Remove socket, TAP devices, rootfs file, supervisor config, cache
   - **External mode**: Remove socket, rootfs file, supervisor config, cache (preserves TAP devices)
3. **⚠️ WARNING**: Permanently deletes rootfs file

### STOP/START/RESTART
- **STOP**: Stop process, remove socket, preserve TAP devices and cache
- **START**: Load cache (including network driver mode), start process, restore configuration
- **RESTART**: Stop + start sequence

**Network Management:**
- **Internal mode**: Automatically creates TAP devices, assigns IPs, configures routes, and sets up dual interfaces (eth0 + mmds0)
- **External mode**: Uses existing TAP devices and network configuration without modification