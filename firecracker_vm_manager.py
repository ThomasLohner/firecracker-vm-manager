#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from lib.config_manager import ConfigManager
from lib.filesystem_manager import FilesystemManager
from lib.network_manager import NetworkManager
from lib.vm_discovery import VMDiscovery
from lib.vm_lifecycle import VMLifecycle

# Version information
__version__ = "1.1.0"


def show_help_and_exit():
    """Show help message with examples and exit"""
    help_text = f"""
Firecracker VM Manager v{__version__} - Create and destroy Firecracker VMs

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
    --socket        Path to Firecracker API socket file (default: /var/run/firecracker/<vm_name>.sock)
    --config        Path to configuration file (default: /etc/firecracker.env)

REQUIRED FOR CREATE ACTION:
    --kernel        Kernel filename (must exist in KERNEL_PATH directory, can be set in config as KERNEL)
    --image         Image filename (must exist in IMAGES_PATH directory, can be set in config as IMAGE)
    --rootfs-size   Size to resize rootfs to (e.g., 1G, 512M, 2048M, can be set in config as ROOTFS_SIZE)
    --tap-ip        IP address for TAP device on host
    --vm-ip         IP address for VM (guest)

OPTIONAL FOR CREATE ACTION:
    --tap-device    TAP device name on host (auto-generated if not specified)
    --mmds-tap      MMDS TAP device name (auto-generated if not specified)

OPTIONAL FOR DESTROY ACTION:
    --tap-device    TAP device name to remove (required if not using auto-discovery)
    --mmds-tap      MMDS TAP device name to remove (required if VM was created with metadata)

OPTIONAL PARAMETERS (CREATE ONLY):
    --cpus          Number of vCPUs (can be set in config as CPUS)
    --memory        Memory in MiB (can be set in config as MEMORY)
    --hostname      Hostname for the VM (defaults to VM name if not specified)
    --foreground    Run Firecracker in foreground for debugging (skips supervisor)
    --force-rootfs  Force overwrite existing rootfs file if it exists
    --help, -h      Show this help message
    --version, -v   Show version information

EXAMPLE USAGE:
    # List available images and kernels
    ./firecracker_vm_manager.py images
    ./firecracker_vm_manager.py kernels

    # Create a VM with auto-generated TAP device (simplest form)
    ./firecracker_vm_manager.py create --name myvm --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with specific TAP device
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-device tap5 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with metadata (MMDS TAP auto-generated)
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux-6.1.141 --image alpine.ext4 --rootfs-size 1G --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --metadata '{{"app":"web"}}'

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
    parser.add_argument("--version", "-v", action="version", version=f"Firecracker VM Manager {__version__}")
    parser.add_argument("--name", help="Name of the VM")
    parser.add_argument("--socket", help="Path to Firecracker API socket (default: /var/run/firecracker/<vm_name>.sock)")
    parser.add_argument("--kernel", help="Kernel filename (must exist in KERNEL_PATH directory, can be set in config as KERNEL)")
    parser.add_argument("--image", help="Image filename (must exist in IMAGES_PATH directory, can be set in config as IMAGE)")
    parser.add_argument("--rootfs-size", help="Size to resize rootfs to (can be set in config as ROOTFS_SIZE)")
    parser.add_argument("--cpus", type=int, help="Number of vCPUs (can be set in config as CPUS)")
    parser.add_argument("--memory", type=int, help="Memory in MiB (can be set in config as MEMORY)")
    parser.add_argument("--tap-device", help="TAP device name on host")
    parser.add_argument("--tap-ip", help="IP address for TAP device on host")
    parser.add_argument("--vm-ip", help="IP address for VM (guest)")
    parser.add_argument("--metadata", help="JSON metadata for MMDS (provide JSON string or file path starting with @)")
    parser.add_argument("--mmds-tap", help="TAP device name for MMDS interface (enables MMDS with network config)")
    parser.add_argument("--hostname", help="Hostname for the VM (defaults to VM name if not specified)")
    parser.add_argument("--foreground", action="store_true", help="Run Firecracker in foreground for debugging")
    parser.add_argument("--force-rootfs", action="store_true", help="Force overwrite existing rootfs file if it exists")
    parser.add_argument("--force-destroy", action="store_true", help="Force destroy without confirmation prompt")
    parser.add_argument("--networkdriver", choices=["internal", "external"], default="internal", help="Network driver mode: 'internal' (default) manages TAP devices, 'external' uses existing TAP devices")
    parser.add_argument("--config", help="Path to configuration file (default: /etc/firecracker.env)")
    parser.add_argument("--help", "-h", action="store_true", help="Show help message")

    args = parser.parse_args()

    # Show help if requested or no action specified
    if args.help or not args.action:
        show_help_and_exit()

    # Initialize configuration manager with config file
    config_manager = ConfigManager(config_file=args.config)
    
    # Perform all preflight checks and environment setup
    if not config_manager.setup_environment(args):
        print("Error: Environment setup failed", file=sys.stderr)
        sys.exit(1)
    
    # Initialize other managers
    filesystem_manager = FilesystemManager(config_manager)
    network_manager = NetworkManager()

    # Validate action parameters
    success, error_msg = config_manager.validate_action_parameters(args.action, args)
    if not success:
        print(error_msg, file=sys.stderr)
        show_help_and_exit()

    if args.action == "kernels":
        # List available kernels
        success = filesystem_manager.list_available_kernels()
        if not success:
            sys.exit(1)
        return

    elif args.action == "images":
        # List available images
        success = filesystem_manager.list_available_images()
        if not success:
            sys.exit(1)
        return

    elif args.action == "list":
        # List all VMs (both running and stopped)
        vm_discovery = VMDiscovery(config_manager)
        all_vms = vm_discovery.discover_all_vms()
        vm_discovery.format_vm_table(all_vms)
        return  # No need to check success for list action

    elif args.action == "create":
        # Validate create-specific parameters
        success, error_msg = config_manager.validate_create_parameters(args)
        if not success:
            print(error_msg, file=sys.stderr)
            show_help_and_exit()

        # Validate external network driver requirements
        success, error_msg = config_manager.validate_external_network_parameters(args)
        if not success:
            print(error_msg, file=sys.stderr)
            show_help_and_exit()

        # Resolve kernel path (support both filenames and full paths)
        resolved_kernel_path = filesystem_manager.resolve_kernel_path(args.kernel)
        if not resolved_kernel_path:
            sys.exit(1)  # Error message already printed by resolve_kernel_path

        # Prepare network devices based on networkdriver mode
        # Do this BEFORE creating rootfs to avoid zombie rootfs files
        result = network_manager.prepare_network_devices(args)
        if not result[0]:  # Check if tap_device was allocated successfully
            sys.exit(1)  # Error messages already printed by prepare_network_devices

        # Build rootfs from image (only after network validation passes)
        rootfs_path = filesystem_manager.build_rootfs(
            vm_name=args.name,
            image_filename=args.image,
            rootfs_size=args.rootfs_size,
            force_overwrite=args.force_rootfs
        )
        if not rootfs_path:
            sys.exit(1)  # Error message already printed by build_rootfs

        # Set hostname to VM name if not specified
        hostname = args.hostname if args.hostname else args.name
        
        # Parse metadata (always include network_config since we always have MMDS TAP)
        # When MMDS TAP is available, always create metadata (at minimum with network_config)
        metadata = config_manager.parse_metadata(args.metadata, args.tap_ip, args.vm_ip, hostname)
        if metadata is None:
            sys.exit(1)  # Error message already printed by parse_metadata

        # Create VM lifecycle manager and create the VM
        vm_lifecycle = VMLifecycle(args.socket, config_manager)
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
            base_image=args.image,
            networkdriver=args.networkdriver
        )

    elif args.action in ["destroy", "stop", "start", "restart"]:
        # Create VM lifecycle manager for lifecycle operations
        vm_lifecycle = VMLifecycle(args.socket, config_manager)
        
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