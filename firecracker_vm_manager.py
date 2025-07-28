#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from lib.config_manager import ConfigManager
from lib.filesystem_manager import FilesystemManager
from lib.network_manager import NetworkManager
from lib.vm_discovery import VMDiscovery
from lib.vm_lifecycle import VMLifecycle


def show_help_and_exit():
    """Show help message with examples and exit"""
    help_text = """
Firecracker VM Manager - Create and destroy Firecracker VMs

USAGE:
    firecracker_vm_manager.py ACTION --name VM_NAME [OPTIONS]

ACTIONS:
    create          Create and start a new VM (builds rootfs from image)
    destroy         Destroy an existing VM and clean up resources
    stop            Stop a VM without removing TAP devices
    start           Start a previously created VM from cached configuration
    restart         Restart a VM by stopping and then starting it
    list            List all VMs (both running and stopped) with their configuration and state
    kernels         List available kernel files from KERNEL_PATH directory
    images          List available image files from IMAGES_PATH directory

REQUIRED PARAMETERS:
    --name          Name of the VM (not required for list, kernels, and images actions)

OPTIONAL PARAMETERS:
    --socket        Path to Firecracker API socket file (default: /tmp/<vm_name>.sock)

REQUIRED FOR CREATE ACTION:
    --kernel        Kernel filename (must exist in KERNEL_PATH directory, can be set in .env as KERNEL)
    --image         Image filename (must exist in IMAGES_PATH directory)
    --rootfs-size   Size to resize rootfs to (e.g., 1G, 512M, 2048M)
    --tap-ip        IP address for TAP device on host
    --vm-ip         IP address for VM (guest)

OPTIONAL FOR CREATE ACTION:
    --tap-device    TAP device name on host (auto-generated if not specified)
    --mmds-tap      MMDS TAP device name (auto-generated if not specified)

OPTIONAL FOR DESTROY ACTION:
    --tap-device    TAP device name to remove (required if not using auto-discovery)
    --mmds-tap      MMDS TAP device name to remove (required if VM was created with metadata)

OPTIONAL PARAMETERS (CREATE ONLY):
    --cpus          Number of vCPUs (can be set in .env as CPUS)
    --memory        Memory in MiB (can be set in .env as MEMORY)
    --hostname      Hostname for the VM (defaults to VM name if not specified)
    --foreground    Run Firecracker in foreground for debugging (skips supervisor)
    --force-rootfs  Force overwrite existing rootfs file if it exists
    --help, -h      Show this help message

EXAMPLE USAGE:
    # List available images and kernels
    ./firecracker_vm_manager.py images
    ./firecracker_vm_manager.py kernels

    # Create a VM with auto-generated TAP device (simplest form)
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with specific TAP device
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-device tap5 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with metadata (MMDS TAP auto-generated)
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --metadata '{"app":"web"}'

    # Create a VM with custom resources and specific devices
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 2G --tap-device tap0 --mmds-tap tap1 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --cpus 2 --memory 512

    # Create a VM in foreground mode for debugging
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --foreground

    # Force overwrite existing rootfs file
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --force-rootfs

    # Destroy a VM (with auto-cleanup warning)
    ./firecracker_vm_manager.py destroy --name myvm
    
    # Destroy a VM with specific device cleanup
    ./firecracker_vm_manager.py destroy --name myvm --tap-device tap0 --mmds-tap tap1

    # Stop a VM without removing TAP devices
    ./firecracker_vm_manager.py stop --name myvm

    # Start a previously created VM from cached configuration
    ./firecracker_vm_manager.py start --name myvm

    # Restart a VM (stop then start)
    ./firecracker_vm_manager.py restart --name myvm

    # List all VMs
    ./firecracker_vm_manager.py list

PREREQUISITES:
    - Root/sudo access for network configuration and supervisor management
    - Supervisor daemon running
    - resize2fs utility for rootfs resizing
    - Python dependencies: pip install requests requests-unixsocket
"""
    print(help_text)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Manage Firecracker VMs", add_help=False)
    parser.add_argument("action", nargs="?", choices=["create", "destroy", "stop", "start", "restart", "list", "kernels", "images"], help="Action to perform")
    parser.add_argument("--name", help="Name of the VM")
    parser.add_argument("--socket", help="Path to Firecracker API socket (default: /tmp/<vm_name>.sock)")
    parser.add_argument("--kernel", help="Kernel filename (must exist in KERNEL_PATH directory, can be set in .env as KERNEL)")
    parser.add_argument("--image", help="Image filename (must exist in IMAGES_PATH directory, can be set in .env as IMAGE)")
    parser.add_argument("--rootfs-size", help="Size to resize rootfs to (can be set in .env as ROOTFS_SIZE)")
    parser.add_argument("--cpus", type=int, help="Number of vCPUs (can be set in .env as CPUS)")
    parser.add_argument("--memory", type=int, help="Memory in MiB (can be set in .env as MEMORY)")
    parser.add_argument("--tap-device", help="TAP device name on host")
    parser.add_argument("--tap-ip", help="IP address for TAP device on host")
    parser.add_argument("--vm-ip", help="IP address for VM (guest)")
    parser.add_argument("--metadata", help="JSON metadata for MMDS (provide JSON string or file path starting with @)")
    parser.add_argument("--mmds-tap", help="TAP device name for MMDS interface (enables MMDS with network config)")
    parser.add_argument("--hostname", help="Hostname for the VM (defaults to VM name if not specified)")
    parser.add_argument("--foreground", action="store_true", help="Run Firecracker in foreground for debugging")
    parser.add_argument("--force-rootfs", action="store_true", help="Force overwrite existing rootfs file if it exists")
    parser.add_argument("--force-destroy", action="store_true", help="Force destroy without confirmation prompt")
    parser.add_argument("--help", "-h", action="store_true", help="Show help message")

    args = parser.parse_args()

    # Show help if requested or no action specified
    if args.help or not args.action:
        show_help_and_exit()

    # Load configuration from .env file first
    temp_config_manager = ConfigManager()
    env_config = temp_config_manager.load_env_config()
    
    # Set default paths under /var/lib/firecracker if not configured
    base_path = "/var/lib/firecracker"
    if 'KERNEL_PATH' not in env_config or not env_config['KERNEL_PATH']:
        env_config['KERNEL_PATH'] = f"{base_path}/kernels"
    if 'IMAGES_PATH' not in env_config or not env_config['IMAGES_PATH']:
        env_config['IMAGES_PATH'] = f"{base_path}/images"
    if 'ROOTFS_PATH' not in env_config or not env_config['ROOTFS_PATH']:
        env_config['ROOTFS_PATH'] = f"{base_path}/rootfs"
    
    # Ensure all required directories exist
    required_dirs = [
        env_config['KERNEL_PATH'],
        env_config['IMAGES_PATH'], 
        env_config['ROOTFS_PATH']
    ]
    
    for dir_path in required_dirs:
        try:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create directory {dir_path}: {e}", file=sys.stderr)
    
    # Initialize managers with appropriate cache directory
    cache_dir = f"{base_path}/cache"
    config_manager = ConfigManager(cache_dir)
    filesystem_manager = FilesystemManager()
    network_manager = NetworkManager()

    # Check for basic required parameters (except for list, kernels, and images actions)
    if not args.name and args.action not in ["list", "kernels", "images"]:
        print("Error: --name is required for create, destroy, stop, start, and restart actions", file=sys.stderr)
        show_help_and_exit()
    
    # Set socket path prefix from .env if available, default to /tmp
    socket_path_prefix = env_config.get('SOCKET_PATH_PREFIX', '/tmp')
    
    # Create socket directory if it doesn't exist
    socket_dir = Path(socket_path_prefix)
    if not socket_dir.exists():
        try:
            socket_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created socket directory: {socket_path_prefix}")
        except Exception as e:
            print(f"Warning: Could not create socket directory {socket_path_prefix}: {e}", file=sys.stderr)
    
    # Set default socket path if not provided (not needed for list, kernels, or images actions)
    if not args.socket and args.action not in ["list", "kernels", "images"]:
        args.socket = str(Path(socket_path_prefix) / f"{args.name}.sock")
    
    # Set kernel from .env if not provided via command line
    if not args.kernel and 'KERNEL' in env_config and env_config['KERNEL']:
        args.kernel = env_config['KERNEL']
    
    # Set image from .env if not provided via command line
    if not args.image and 'IMAGE' in env_config and env_config['IMAGE']:
        args.image = env_config['IMAGE']
    
    # Set rootfs size from .env if not provided via command line
    if not args.rootfs_size and 'ROOTFS_SIZE' in env_config:
        args.rootfs_size = env_config['ROOTFS_SIZE']
    
    # Set CPU count from .env if available
    if not args.cpus and 'CPUS' in env_config:
        try:
            args.cpus = int(env_config['CPUS'])
        except ValueError:
            print(f"Warning: Invalid CPUS value in .env file: {env_config['CPUS']}", file=sys.stderr)
    
    # Set memory from .env if available
    if not args.memory and 'MEMORY' in env_config:
        try:
            args.memory = int(env_config['MEMORY'])
        except ValueError:
            print(f"Warning: Invalid MEMORY value in .env file: {env_config['MEMORY']}", file=sys.stderr)

    if args.action == "kernels":
        # List available kernels
        success = filesystem_manager.list_available_kernels(env_config.get('KERNEL_PATH'))
        if not success:
            sys.exit(1)
        return

    elif args.action == "images":
        # List available images
        success = filesystem_manager.list_available_images(env_config.get('IMAGES_PATH'))
        if not success:
            sys.exit(1)
        return

    elif args.action == "list":
        # List all VMs (both running and stopped)
        vm_discovery = VMDiscovery(socket_path_prefix, config_manager)
        all_vms = vm_discovery.discover_all_vms()
        vm_discovery.format_vm_table(all_vms)
        return  # No need to check success for list action

    elif args.action == "create":
        # Check for create-specific required parameters
        create_required = {
            "kernel": args.kernel,
            "image": args.image,
            "rootfs-size": args.rootfs_size,
            "tap-ip": args.tap_ip,
            "vm-ip": args.vm_ip,
            "cpus": args.cpus,
            "memory": args.memory
        }
        
        missing_params = [param for param, value in create_required.items() if not value]
        
        if missing_params:
            error_msg = f"Error: Missing required parameter(s) for create action: {', '.join(['--' + p for p in missing_params])}"
            env_hints = []
            if 'kernel' in missing_params:
                env_hints.append("KERNEL_PATH=<path>")
            if 'image' in missing_params:
                env_hints.append("IMAGE=<filename>")
            if 'rootfs-size' in missing_params:
                env_hints.append("ROOTFS_SIZE=<size>")
            if 'cpus' in missing_params:
                env_hints.append("CPUS=<number>")
            if 'memory' in missing_params:
                env_hints.append("MEMORY=<mb>")
            
            if env_hints:
                error_msg += f"\nNote: These can be set in .env file: {', '.join(env_hints)}"
            
            print(error_msg, file=sys.stderr)
            show_help_and_exit()

        # Resolve kernel path (support both filenames and full paths)
        resolved_kernel_path = filesystem_manager.resolve_kernel_path(args.kernel, env_config.get('KERNEL_PATH'))
        if not resolved_kernel_path:
            sys.exit(1)  # Error message already printed by resolve_kernel_path

        # Build rootfs from image
        rootfs_path = filesystem_manager.build_rootfs(
            vm_name=args.name,
            image_filename=args.image,
            images_path_env=env_config.get('IMAGES_PATH'),
            rootfs_path_env=env_config.get('ROOTFS_PATH'),
            rootfs_size=args.rootfs_size,
            force_overwrite=args.force_rootfs
        )
        if not rootfs_path:
            sys.exit(1)  # Error message already printed by build_rootfs

        # Auto-generate TAP device name if not specified
        if not args.tap_device:
            args.tap_device = network_manager.find_next_available_tap_device()
            print(f"Auto-generated TAP device: {args.tap_device}")
        else:
            # Validate explicitly provided TAP device
            if not network_manager.validate_tap_device_available(args.tap_device):
                print(f"Error: TAP device '{args.tap_device}' already exists on the system", file=sys.stderr)
                sys.exit(1)
            # Mark explicitly provided device as allocated to prevent conflicts
            network_manager.allocated_tap_devices.add(args.tap_device)

        # Auto-generate MMDS TAP device name if not specified (always needed for network_config)
        if not args.mmds_tap:
            args.mmds_tap = network_manager.find_next_available_tap_device()
            print(f"Auto-generated MMDS TAP device: {args.mmds_tap}")
        else:
            # Validate explicitly provided MMDS TAP device
            if not network_manager.validate_tap_device_available(args.mmds_tap):
                print(f"Error: MMDS TAP device '{args.mmds_tap}' already exists on the system", file=sys.stderr)
                sys.exit(1)
            # Mark explicitly provided device as allocated to prevent conflicts
            network_manager.allocated_tap_devices.add(args.mmds_tap)

        # Set hostname to VM name if not specified
        hostname = args.hostname if args.hostname else args.name
        
        # Parse metadata (always include network_config since we always have MMDS TAP)
        # When MMDS TAP is available, always create metadata (at minimum with network_config)
        metadata = config_manager.parse_metadata(args.metadata, args.tap_ip, args.vm_ip, hostname)
        if metadata is None:
            sys.exit(1)  # Error message already printed by parse_metadata

        # Create VM lifecycle manager and create the VM
        vm_lifecycle = VMLifecycle(args.socket, socket_path_prefix, config_manager)
        # Share the network manager instance to preserve allocated TAP devices
        vm_lifecycle.network_manager = network_manager
        
        success = vm_lifecycle.create_vm(
            vm_name=args.name,
            kernel_path=resolved_kernel_path,
            rootfs_path=rootfs_path,
            tap_device=args.tap_device,
            tap_ip=args.tap_ip,
            vm_ip=args.vm_ip,
            cpus=args.cpus,
            memory=args.memory,
            metadata=metadata,
            mmds_tap=args.mmds_tap,
            foreground=args.foreground,
            hostname=hostname,
            base_image=args.image
        )

    elif args.action in ["destroy", "stop", "start", "restart"]:
        # Create VM lifecycle manager for lifecycle operations
        vm_lifecycle = VMLifecycle(args.socket, socket_path_prefix, config_manager)
        
        if args.action == "destroy":
            success = vm_lifecycle.destroy_vm(
                vm_name=args.name,
                force_destroy=args.force_destroy
            )
        elif args.action == "stop":
            success = vm_lifecycle.stop_vm(vm_name=args.name)
        elif args.action == "start":
            success = vm_lifecycle.start_vm(vm_name=args.name)
        elif args.action == "restart":
            success = vm_lifecycle.restart_vm(vm_name=args.name)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()