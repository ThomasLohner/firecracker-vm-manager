#!/usr/bin/env python3

import argparse
import sys

from lib.config_manager import ConfigManager
from lib.filesystem_manager import FilesystemManager
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


def format_kernels_table(kernel_files):
    """Format kernel files as a table for CLI display"""
    if not kernel_files:
        print("No kernel files found")
        print("Looking for files matching: vmlinux*, bzImage*, kernel*, Image*")
        return
    
    print()
    print(f"{'Filename':<30} {'Size':<10} {'Modified'}")
    print('-' * 55)
    
    for kernel in kernel_files:
        filename = kernel['filename']
        size = kernel['size']
        modified = kernel['modified']
        print(f"{filename:<30} {size:<10} {modified}")
    
    print()
    print("Usage: ./fcm create --kernel <filename> ...")
    print(f"Example: ./fcm create --kernel {kernel_files[0]['filename']} ...")


def format_images_table(image_files):
    """Format image files as a table for CLI display"""
    if not image_files:
        print("No image files found")
        print("Looking for files matching: *.ext4, *.ext3, *.ext2, *.img, *.qcow2, *.raw")
        return
    
    print()
    print(f"{'Filename':<30} {'Size':<10} {'Modified'}")
    print('-' * 55)
    
    for image in image_files:
        filename = image['filename']
        size = image['size']
        modified = image['modified']
        print(f"{filename:<30} {size:<10} {modified}")
    
    print()
    print("Usage: ./fcm create --image <filename> ...")
    print(f"Example: ./fcm create --image {image_files[0]['filename']} ...")


def format_vms_table(all_vms):
    """Format VM information as a table for CLI display"""
    from pathlib import Path
    
    if not all_vms:
        print("No VMs found.")
        return
    
    # Build table data
    table_data = []
    for vm in all_vms:
        # Extract relevant fields from the VM data structure
        vm_name = vm['name']
        state = vm['state']
        
        # Get configuration from appropriate source
        config = vm.get('config')
        cached_config = vm.get('cached_config', {})
        
        # Determine values based on state
        if state == 'running' and config:
            # Use live API config for running VMs
            machine_config = config.get('machine-config', {})
            cpus = machine_config.get('vcpu_count', 'N/A')
            memory = machine_config.get('mem_size_mib', 'N/A')
            
            # Get kernel name
            boot_source = config.get('boot-source', {})
            kernel_path = boot_source.get('kernel_image_path', 'N/A')
            kernel_name = Path(kernel_path).name if kernel_path != 'N/A' else 'N/A'
            
            # Get rootfs name
            drives = config.get('drives', [])
            rootfs_filename = 'N/A'
            for drive in drives:
                if drive.get('drive_id') == 'rootfs':
                    rootfs_path = drive.get('path_on_host', 'N/A')
                    rootfs_filename = Path(rootfs_path).name if rootfs_path != 'N/A' else 'N/A'
                    break
            
            # Get network info
            network_interfaces = config.get('network-interfaces', [])
            tap_device = 'N/A'
            mmds_tap = 'N/A'
            for iface in network_interfaces:
                if iface.get('iface_id') == 'eth0':
                    tap_device = iface.get('host_dev_name', 'N/A')
                elif iface.get('iface_id') == 'mmds0':
                    mmds_tap = iface.get('host_dev_name', 'N/A')
        else:
            # Use cached config for stopped VMs
            cpus = cached_config.get('cpus', 'N/A')
            memory = cached_config.get('memory', 'N/A')
            kernel_path = cached_config.get('kernel', 'N/A')
            kernel_name = Path(kernel_path).name if kernel_path != 'N/A' else 'N/A'
            rootfs_path = cached_config.get('rootfs', 'N/A')
            rootfs_filename = Path(rootfs_path).name if rootfs_path != 'N/A' else 'N/A'
            tap_device = cached_config.get('tap_device', 'N/A')
            mmds_tap = cached_config.get('mmds_tap', 'N/A')
        
        # Get additional info from VM data
        vm_ip = vm.get('vm_ip', 'N/A')
        tap_ip = vm.get('tap_ip', 'N/A')
        base_image = vm.get('base_image', 'N/A')
        networkdriver = vm.get('networkdriver', 'N/A')
        
        # Format memory
        memory_str = f"{memory} MiB" if memory != 'N/A' else 'N/A'
        
        # Format TAP with IP
        tap_str = f"{tap_device} ({tap_ip})" if tap_device != 'N/A' and tap_ip != 'N/A' else tap_device
        
        table_data.append([
            vm_name, state, vm_ip, str(cpus), memory_str, 
            rootfs_filename, base_image, kernel_name, 
            tap_str, mmds_tap, networkdriver
        ])
    
    # Print table
    headers = ['VM Name', 'State', 'Internal IP', 'CPUs', 'Memory', 'Rootfs', 
               'Base Image', 'Kernel', 'TAP Interface (IP)', 'MMDS TAP', 'Network Driver']
    
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in table_data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    
    # Print header
    header_line = ' | '.join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print('-+-'.join('-' * w for w in widths))
    
    # Print rows
    for row in table_data:
        row_line = ' | '.join(str(cell).ljust(w) for cell, w in zip(row, widths))
        print(row_line)


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
    
    # Validate action parameters
    success, error_msg = config_manager.validate_action_parameters(args.action, args)
    if not success:
        print(error_msg, file=sys.stderr)
        show_help_and_exit()

    if args.action == "kernels":
        # List available kernels
        filesystem_manager = FilesystemManager(config_manager)
        kernel_files = filesystem_manager.get_available_kernels()
        if kernel_files is None:  # Error occurred
            sys.exit(1)
        # Get kernel path for display
        env_config = config_manager.get_env_config()
        kernel_path = env_config.get('KERNEL_PATH', '/var/lib/firecracker/kernels')
        print(f"Available kernels in {kernel_path}:")
        format_kernels_table(kernel_files)
        return

    elif args.action == "images":
        # List available images
        filesystem_manager = FilesystemManager(config_manager)
        image_files = filesystem_manager.get_available_images()
        if image_files is None:  # Error occurred
            sys.exit(1)
        # Get images path for display
        env_config = config_manager.get_env_config()
        images_path = env_config.get('IMAGES_PATH', '/var/lib/firecracker/images')
        print(f"Available images in {images_path}:")
        format_images_table(image_files)
        return

    elif args.action == "list":
        # List all VMs (both running and stopped)
        vm_discovery = VMDiscovery(config_manager)
        all_vms = vm_discovery.discover_all_vms()
        format_vms_table(all_vms)
        return  # No need to check success for list action

    elif args.action == "create":
        # Create VM lifecycle manager and delegate entire creation process
        # Use custom socket path if provided, otherwise use VM name
        vm_lifecycle = VMLifecycle(args.socket if args.socket else args.name, config_manager)
        success = vm_lifecycle.create_vm(args)

    elif args.action == "destroy":
        # Destroy a VM and clean up all resources
        vm_lifecycle = VMLifecycle(args.socket if args.socket else args.name, config_manager)
        success = vm_lifecycle.destroy_vm(
            vm_name=args.name,
            force_destroy=args.force_destroy
        )
    
    elif args.action == "stop":
        # Stop a running VM
        vm_lifecycle = VMLifecycle(args.socket if args.socket else args.name, config_manager)
        success = vm_lifecycle.stop_vm(vm_name=args.name)
    
    elif args.action == "start":
        # Start a stopped VM
        vm_lifecycle = VMLifecycle(args.socket if args.socket else args.name, config_manager)
        success = vm_lifecycle.start_vm(vm_name=args.name)
    
    elif args.action == "restart":
        # Restart a VM (stop then start)
        vm_lifecycle = VMLifecycle(args.socket if args.socket else args.name, config_manager)
        success = vm_lifecycle.restart_vm(vm_name=args.name)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()