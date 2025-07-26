#!/usr/bin/env python3

import argparse
import json
import os
import requests
import requests_unixsocket
import subprocess
import sys
from pathlib import Path

def load_env_config():
    """Load configuration from .env file"""
    config = {}
    env_file = Path(".env")
    
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            config[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Could not read .env file: {e}", file=sys.stderr)
    
    return config


def parse_metadata(metadata_arg, tap_ip, vm_ip):
    """Parse metadata from command line argument and add network config"""
    metadata = {}
    
    # Parse user-provided metadata
    if metadata_arg:
        if metadata_arg.startswith('@'):
            # Read from file
            file_path = metadata_arg[1:]
            try:
                with open(file_path, 'r') as f:
                    user_metadata = json.load(f)
                metadata.update(user_metadata)
            except FileNotFoundError:
                print(f"Error: Metadata file not found: {file_path}", file=sys.stderr)
                return None
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in metadata file {file_path}: {e}", file=sys.stderr)
                return None
        else:
            # Parse JSON string directly
            try:
                user_metadata = json.loads(metadata_arg)
                metadata.update(user_metadata)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in metadata argument: {e}", file=sys.stderr)
                return None
    
    # Always add network_config object
    metadata['network_config'] = {
            'ip': vm_ip,
            'gateway': tap_ip
        }
    
    return metadata


class FirecrackerVMManager:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.session = requests_unixsocket.Session()
        self.base_url = f"http+unix://{self.socket_path.replace('/', '%2F')}"

    def _make_request(self, method, endpoint, data=None):
        """Make HTTP request to Firecracker API"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method == "PUT":
                response = self.session.put(url, json=data)
            elif method == "GET":
                response = self.session.get(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code not in [200, 204]:
                print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
                return False
            return True
        except Exception as e:
            print(f"Request failed: {e}", file=sys.stderr)
            return False

    def check_socket_in_use(self):
        """Check if Firecracker process is listening on socket"""
        try:
            response = self.session.get(f"{self.base_url}/")
            return True  # Socket is in use
        except:
            return False  # Socket is not in use or doesn't exist

    def set_boot_source(self, kernel_path, boot_args="console=ttyS0 reboot=k panic=1 pci=off"):
        """Set the boot source for the VM"""
        if not Path(kernel_path).exists():
            print(f"Error: Kernel file {kernel_path} does not exist", file=sys.stderr)
            return False
        
        data = {
            "kernel_image_path": str(Path(kernel_path).absolute()),
            "boot_args": boot_args
        }
        return self._make_request("PUT", "/boot-source", data)

    def set_rootfs(self, rootfs_path):
        """Set the root filesystem drive"""
        if not Path(rootfs_path).exists():
            print(f"Error: Rootfs file {rootfs_path} does not exist", file=sys.stderr)
            return False
        
        data = {
            "drive_id": "rootfs",
            "path_on_host": str(Path(rootfs_path).absolute()),
            "is_root_device": True,
            "is_read_only": False
        }
        return self._make_request("PUT", "/drives/rootfs", data)

    def set_network_interface(self, tap_device):
        """Set network interface configuration"""
        data = {
            "iface_id": "eth0",
            "host_dev_name": tap_device
        }
        
        return self._make_request("PUT", "/network-interfaces/eth0", data)

    def set_mmds_network_interface(self, mmds_tap):
        """Set dedicated MMDS network interface configuration"""
        data = {
            "iface_id": "mmds0",
            "host_dev_name": mmds_tap
        }
        
        return self._make_request("PUT", "/network-interfaces/mmds0", data)

    def set_machine_config(self, vcpu_count, mem_size_mib):
        """Set machine configuration (CPU and memory)"""
        data = {
            "vcpu_count": vcpu_count,
            "mem_size_mib": mem_size_mib
        }
        return self._make_request("PUT", "/machine-config", data)

    def configure_mmds_interface(self, interface_id="mmds0", ipv4_address="169.254.169.254"):
        """Configure MMDS to allow requests from specified network interface"""
        data = {
            "network_interfaces": [interface_id],
            "ipv4_address": ipv4_address
        }
        return self._make_request("PUT", "/mmds/config", data)

    def set_mmds_metadata(self, metadata):
        """Set metadata for the Metadata Service (MMDS)"""
        if not metadata:
            return True  # Skip if no metadata provided
        
        return self._make_request("PUT", "/mmds", metadata)

    def setup_mmds_tap_device(self, mmds_tap):
        """Create MMDS TAP device on host (no IP configuration needed)"""
        try:
            # Check if MMDS TAP device already exists
            result = subprocess.run(
                ["ip", "link", "show", mmds_tap],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                # MMDS TAP device doesn't exist, create it
                print(f"Creating MMDS TAP device: {mmds_tap}")
                subprocess.run(
                    ["sudo", "ip", "tuntap", "add", mmds_tap, "mode", "tap"],
                    check=True
                )
                print(f"✓ MMDS TAP device {mmds_tap} created")
            else:
                print(f"✓ MMDS TAP device {mmds_tap} already exists")
            
            # Bring MMDS TAP device up
            print(f"Bringing up {mmds_tap}")
            subprocess.run(
                ["sudo", "ip", "link", "set", mmds_tap, "up"],
                check=True
            )
            print(f"✓ {mmds_tap} is up")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error setting up MMDS TAP device: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Unexpected error setting up MMDS TAP device: {e}", file=sys.stderr)
            return False

    def setup_tap_device(self, tap_device, tap_ip, vm_ip):
        """Create and configure TAP device on host"""
        try:
            # Check if TAP device already exists
            result = subprocess.run(
                ["ip", "link", "show", tap_device],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                # TAP device doesn't exist, create it
                print(f"Creating TAP device: {tap_device}")
                subprocess.run(
                    ["sudo", "ip", "tuntap", "add", tap_device, "mode", "tap"],
                    check=True
                )
                print(f"✓ TAP device {tap_device} created")
            else:
                print(f"✓ TAP device {tap_device} already exists")
            
            # Check if IP address is already configured
            addr_result = subprocess.run(
                ["ip", "addr", "show", tap_device],
                capture_output=True, text=True
            )
            
            if f"{tap_ip}/32" not in addr_result.stdout:
                # Configure IP address on TAP device
                print(f"Configuring IP {tap_ip}/32 on {tap_device}")
                subprocess.run(
                    ["sudo", "ip", "addr", "add", f"{tap_ip}/32", "dev", tap_device],
                    check=True
                )
                print(f"✓ IP {tap_ip}/32 configured on {tap_device}")
            else:
                print(f"✓ IP {tap_ip}/32 already configured on {tap_device}")
            
            # Bring TAP device up
            print(f"Bringing up {tap_device}")
            subprocess.run(
                ["sudo", "ip", "link", "set", tap_device, "up"],
                check=True
            )
            print(f"✓ {tap_device} is up")
            
            # Check if route already exists
            route_result = subprocess.run(
                ["ip", "route", "show", f"{vm_ip}/32"],
                capture_output=True, text=True
            )
            
            if not route_result.stdout.strip():
                # Add route for VM IP via TAP device
                print(f"Adding route for VM IP {vm_ip} via {tap_device}")
                subprocess.run(
                    ["sudo", "ip", "route", "add", f"{vm_ip}/32", "dev", tap_device],
                    check=True
                )
                print(f"✓ Route for {vm_ip} via {tap_device} added")
            else:
                print(f"✓ Route for {vm_ip} already exists")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error setting up TAP device: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Unexpected error setting up TAP device: {e}", file=sys.stderr)
            return False

    def remove_tap_device(self, tap_device):
        """Remove TAP device (routes are automatically removed)"""
        try:
            # Check if TAP device exists
            result = subprocess.run(
                ["ip", "link", "show", tap_device],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                print(f"Removing TAP device: {tap_device}")
                subprocess.run(
                    ["sudo", "ip", "link", "del", tap_device],
                    check=True
                )
                print(f"✓ TAP device {tap_device} removed (routes automatically removed)")
            else:
                print(f"✓ TAP device {tap_device} doesn't exist")
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error removing TAP device: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Unexpected error removing TAP device: {e}", file=sys.stderr)
            return False

    def create_supervisor_config(self, vm_name, socket_path):
        """Create supervisord configuration for VM"""
        config_content = f"""[program:{vm_name}]
command=/usr/sbin/firecracker --id {vm_name} --api-sock {socket_path}
stdout_logfile=/var/log/{vm_name}.log
stderr_logfile=/var/log/{vm_name}.error.log
autostart=true
"""
        
        config_path = f"/etc/supervisor/conf.d/{vm_name}.conf"
        
        try:
            with open(config_path, 'w') as f:
                f.write(config_content)
            print(f"✓ Supervisor config created: {config_path}")
            return True
        except Exception as e:
            print(f"Error creating supervisor config: {e}", file=sys.stderr)
            return False

    def remove_supervisor_config(self, vm_name):
        """Remove supervisord configuration for VM"""
        config_path = f"/etc/supervisor/conf.d/{vm_name}.conf"
        
        try:
            if os.path.exists(config_path):
                os.remove(config_path)
                print(f"✓ Supervisor config removed: {config_path}")
            else:
                print(f"✓ Supervisor config doesn't exist: {config_path}")
            return True
        except Exception as e:
            print(f"Error removing supervisor config: {e}", file=sys.stderr)
            return False

    def supervisor_reload(self):
        """Reload supervisor configuration"""
        try:
            subprocess.run(["sudo", "supervisorctl", "update"], check=True)
            print("✓ Supervisor configuration reloaded")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error reloading supervisor: {e}", file=sys.stderr)
            return False

    def start_microvm(self):
        """Start the microVM"""
        data = {
            "action_type": "InstanceStart"
        }
        return self._make_request("PUT", "/actions", data)

    def create_vm(self, vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata=None, mmds_tap=None, foreground=False):
        """Create and start a new VM"""
        print(f"Creating VM: {vm_name}...")
        
        # Check if socket is in use
        if self.check_socket_in_use():
            print(f"Error: Socket {self.socket_path} is already in use", file=sys.stderr)
            return False
        
        # If socket file exists but nothing is listening, delete it
        if Path(self.socket_path).exists():
            print(f"Removing stale socket file: {self.socket_path}")
            os.remove(self.socket_path)
        
        if foreground:
            return self.create_vm_foreground(vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
        else:
            return self.create_vm_supervisor(vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
    
    def create_vm_supervisor(self, vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap):
        """Create VM using supervisor"""
        # Create supervisor config
        if not self.create_supervisor_config(vm_name, self.socket_path):
            return False
        
        # Reload supervisor to start Firecracker
        if not self.supervisor_reload():
            return False
        
        # Wait a moment for Firecracker to start
        import time
        time.sleep(1)
        
        # Now configure the VM
        return self.configure_and_start(kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
    
    def create_vm_foreground(self, vm_name, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap):
        """Create VM in foreground mode for debugging"""
        import signal
        
        # Setup TAP device first
        if not self.setup_tap_device(tap_device, tap_ip, vm_ip):
            print("Failed to setup TAP device", file=sys.stderr)
            return False
        
        print(f"Starting Firecracker in foreground mode...")
        print(f"Command: /usr/sbin/firecracker --id {vm_name} --api-sock {self.socket_path}")
        
        # Cleanup function for when process terminates
        def cleanup():
            print("\nCleaning up...")
            # Remove TAP device
            self.remove_tap_device(tap_device)
            # Remove MMDS TAP device if it was used
            if mmds_tap:
                self.remove_tap_device(mmds_tap)
            # Remove socket file
            if Path(self.socket_path).exists():
                os.remove(self.socket_path)
                print(f"✓ Socket file removed: {self.socket_path}")
        
        # Setup signal handlers for cleanup
        def signal_handler(signum, frame):
            cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Start Firecracker process
            firecracker_process = subprocess.Popen([
                "/usr/sbin/firecracker",
                "--id", vm_name,
                "--api-sock", self.socket_path
            ])
            
            # Wait a moment for Firecracker to start
            import time
            time.sleep(1)
            
            # Configure the VM
            config_success = self.configure_and_start(kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap)
            
            if not config_success:
                print("VM configuration failed, terminating Firecracker", file=sys.stderr)
                firecracker_process.terminate()
                cleanup()
                return False
            
            print("\n✓ VM running in foreground mode. Press Ctrl+C to stop and cleanup.")
            
            # Wait for Firecracker process to complete
            firecracker_process.wait()
            
        except KeyboardInterrupt:
            print("\nReceived interrupt signal")
        except Exception as e:
            print(f"Error running Firecracker: {e}", file=sys.stderr)
        finally:
            cleanup()
        
        return True
    
    def destroy_vm(self, vm_name, tap_device, mmds_tap=None):
        """Destroy a VM and clean up resources"""
        print(f"Destroying VM: {vm_name}...")
        
        # Check if socket is in use
        if self.check_socket_in_use():
            print(f"Error: Socket {self.socket_path} is still in use. Stop the VM first.", file=sys.stderr)
            return False
        
        # Remove socket file if it exists
        if Path(self.socket_path).exists():
            print(f"Removing socket file: {self.socket_path}")
            os.remove(self.socket_path)
            print(f"✓ Socket file removed")
        
        # Remove TAP device (routes are automatically removed)
        if not self.remove_tap_device(tap_device):
            return False
        
        # Remove MMDS TAP device if it was used
        if mmds_tap:
            if not self.remove_tap_device(mmds_tap):
                return False
        
        # Remove supervisor config
        if not self.remove_supervisor_config(vm_name):
            return False
        
        # Reload supervisor
        if not self.supervisor_reload():
            return False
        
        print(f"✓ VM {vm_name} destroyed successfully!")
        return True

    def configure_and_start(self, kernel_path, rootfs_path, tap_device, tap_ip, vm_ip, cpus, memory, metadata, mmds_tap):
        """Configure all VM settings and start the microVM"""
        print("Configuring Firecracker VM...")
        
        # Set machine configuration
        if not self.set_machine_config(cpus, memory):
            print("Failed to set machine configuration", file=sys.stderr)
            return False
        print(f"✓ Machine config set: {cpus} vCPUs, {memory} MiB RAM")

        # Set boot source
        if not self.set_boot_source(kernel_path):
            print("Failed to set boot source", file=sys.stderr)
            return False
        print(f"✓ Boot source set: {kernel_path}")

        # Set rootfs
        if not self.set_rootfs(rootfs_path):
            print("Failed to set rootfs", file=sys.stderr)
            return False
        print(f"✓ Rootfs set: {rootfs_path}")

        # Setup TAP device and networking
        if not self.setup_tap_device(tap_device, tap_ip, vm_ip):
            print("Failed to setup TAP device", file=sys.stderr)
            return False

        # Set primary network interface (eth0)
        if not self.set_network_interface(tap_device):
            print("Failed to set network interface", file=sys.stderr)
            return False
        print(f"✓ Primary network interface set: eth0 -> {tap_device}")

        # Configure MMDS if metadata provided
        if metadata and mmds_tap:
            # Setup dedicated MMDS TAP device
            if not self.setup_mmds_tap_device(mmds_tap):
                print("Failed to setup MMDS TAP device", file=sys.stderr)
                return False
            
            # Set dedicated MMDS network interface (mmds0)
            if not self.set_mmds_network_interface(mmds_tap):
                print("Failed to set MMDS network interface", file=sys.stderr)
                return False
            print(f"✓ MMDS network interface set: mmds0 -> {mmds_tap}")
            
            # Configure which interface can access MMDS
            if not self.configure_mmds_interface("mmds0"):
                print("Failed to configure MMDS interface", file=sys.stderr)
                return False
            print("✓ MMDS interface configured")
            # Set the metadata
            if not self.set_mmds_metadata(metadata):
                print("Failed to set MMDS metadata", file=sys.stderr)
                return False
            print("✓ MMDS metadata configured")

        # Start the VM
        if not self.start_microvm():
            print("Failed to start microVM", file=sys.stderr)
            return False
        print("✓ MicroVM started successfully!")
        
        return True


def show_help_and_exit():
    """Show help message with examples and exit"""
    help_text = """
Firecracker VM Manager - Create and destroy Firecracker VMs

USAGE:
    firecracker_vm_manager.py ACTION --name VM_NAME [OPTIONS]

ACTIONS:
    create          Create and start a new VM
    destroy         Destroy an existing VM and clean up resources

REQUIRED PARAMETERS:
    --name          Name of the VM

OPTIONAL PARAMETERS:
    --socket        Path to Firecracker API socket file (default: /tmp/<vm_name>.sock)

REQUIRED FOR CREATE ACTION:
    --kernel        Path to kernel image file
    --rootfs        Path to rootfs device file
    --tap-device    TAP device name on host (e.g., tap0)
    --tap-ip        IP address for TAP device on host
    --vm-ip         IP address for VM (guest)

REQUIRED FOR DESTROY ACTION:
    --tap-device    TAP device name to remove

OPTIONAL FOR DESTROY ACTION:
    --mmds-tap      MMDS TAP device name to remove (use if VM was created with metadata)

OPTIONAL PARAMETERS (CREATE ONLY):
    --cpus          Number of vCPUs (default: 1)
    --memory        Memory in MiB (default: 128)
    --foreground    Run Firecracker in foreground for debugging (skips supervisor)
    --help, -h      Show this help message

EXAMPLE USAGE:
    # Create a VM (socket path defaults to /tmp/myvm.sock)
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux --rootfs rootfs.ext4 --tap-device tap0 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with custom socket path
    ./firecracker_vm_manager.py create --name myvm --socket /tmp/custom.socket --kernel vmlinux --rootfs rootfs.ext4 --tap-device tap0 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2

    # Create a VM with custom resources
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux --rootfs rootfs.ext4 --tap-device tap0 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --cpus 2 --memory 512

    # Create a VM in foreground mode for debugging
    ./firecracker_vm_manager.py create --name myvm --kernel vmlinux --rootfs rootfs.ext4 --tap-device tap0 --tap-ip 172.16.0.1 --vm-ip 172.16.0.2 --foreground

    # Destroy a VM without metadata
    ./firecracker_vm_manager.py destroy --name myvm --tap-device tap0
    
    # Destroy a VM with metadata (include MMDS TAP cleanup)
    ./firecracker_vm_manager.py destroy --name myvm --tap-device tap0 --mmds-tap tap1

PREREQUISITES:
    - Root/sudo access for network configuration and supervisor management
    - Supervisor daemon running
    - Python dependencies: pip install requests requests-unixsocket
"""
    print(help_text)
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Manage Firecracker VMs", add_help=False)
    parser.add_argument("action", nargs="?", choices=["create", "destroy"], help="Action to perform")
    parser.add_argument("--name", help="Name of the VM")
    parser.add_argument("--socket", help="Path to Firecracker API socket (default: /tmp/<vm_name>.sock)")
    parser.add_argument("--kernel", help="Path to kernel image (can be set in .env file as KERNEL_PATH)")
    parser.add_argument("--rootfs", help="Path to rootfs device")
    parser.add_argument("--cpus", type=int, help="Number of vCPUs (can be set in .env as CPUS)")
    parser.add_argument("--memory", type=int, help="Memory in MiB (can be set in .env as MEMORY)")
    parser.add_argument("--tap-device", help="TAP device name on host")
    parser.add_argument("--tap-ip", help="IP address for TAP device on host")
    parser.add_argument("--vm-ip", help="IP address for VM (guest)")
    parser.add_argument("--metadata", help="JSON metadata for MMDS (provide JSON string or file path starting with @)")
    parser.add_argument("--mmds-tap", help="TAP device name for MMDS interface (enables MMDS with network config)")
    parser.add_argument("--foreground", action="store_true", help="Run Firecracker in foreground for debugging")
    parser.add_argument("--help", "-h", action="store_true", help="Show help message")

    args = parser.parse_args()

    # Show help if requested or no action specified
    if args.help or not args.action:
        show_help_and_exit()

    # Load configuration from .env file
    env_config = load_env_config()

    # Check for basic required parameters
    if not args.name:
        print("Error: --name is required for all actions", file=sys.stderr)
        show_help_and_exit()
    
    # Set default socket path if not provided
    if not args.socket:
        args.socket = f"/tmp/{args.name}.sock"
    
    # Set kernel path from .env if not provided via command line
    if not args.kernel and 'KERNEL_PATH' in env_config:
        args.kernel = env_config['KERNEL_PATH']
    
    # Set CPU count from .env if available
    if 'CPUS' in env_config:
        try:
            args.cpus = int(env_config['CPUS'])
        except ValueError:
            print(f"Warning: Invalid CPUS value in .env file: {env_config['CPUS']}", file=sys.stderr)
    
    # Set memory from .env if available
    if 'MEMORY' in env_config:
        try:
            args.memory = int(env_config['MEMORY'])
        except ValueError:
            print(f"Warning: Invalid MEMORY value in .env file: {env_config['MEMORY']}", file=sys.stderr)

    # Create VM manager
    vm_manager = FirecrackerVMManager(args.socket)

    if args.action == "create":
        # Check for create-specific required parameters
        create_required = {
            "kernel": args.kernel,
            "rootfs": args.rootfs,
            "tap-device": args.tap_device,
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
            if 'cpus' in missing_params:
                env_hints.append("CPUS=<number>")
            if 'memory' in missing_params:
                env_hints.append("MEMORY=<mb>")
            
            if env_hints:
                error_msg += f"\nNote: These can be set in .env file: {', '.join(env_hints)}"
            
            print(error_msg, file=sys.stderr)
            show_help_and_exit()

        # Validate metadata and mmds-tap dependency  
        if args.metadata and not args.mmds_tap:
            print("Error: --mmds-tap is required when using --metadata", file=sys.stderr)
            show_help_and_exit()

        # Parse metadata (always include network_config when MMDS is used)
        metadata = None
        if args.mmds_tap:
            # When MMDS TAP is specified, always create metadata (at minimum with network_config)
            metadata = parse_metadata(args.metadata, args.tap_ip, args.vm_ip)
            if metadata is None:
                sys.exit(1)  # Error message already printed by parse_metadata

        success = vm_manager.create_vm(
            vm_name=args.name,
            kernel_path=args.kernel,
            rootfs_path=args.rootfs,
            tap_device=args.tap_device,
            tap_ip=args.tap_ip,
            vm_ip=args.vm_ip,
            cpus=args.cpus,
            memory=args.memory,
            metadata=metadata,
            mmds_tap=args.mmds_tap,
            foreground=args.foreground
        )

    elif args.action == "destroy":
        # Check for destroy-specific required parameters
        destroy_required = {
            "tap-device": args.tap_device
        }
        
        missing_params = [param for param, value in destroy_required.items() if not value]
        
        if missing_params:
            print(f"Error: Missing required parameter(s) for destroy action: {', '.join(['--' + p for p in missing_params])}", file=sys.stderr)
            show_help_and_exit()

        success = vm_manager.destroy_vm(
            vm_name=args.name,
            tap_device=args.tap_device,
            mmds_tap=args.mmds_tap
        )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()