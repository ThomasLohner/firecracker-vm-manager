#!/usr/bin/env python3

import signal
import subprocess
import sys
import time
from pathlib import Path

from .firecracker_api import FirecrackerAPI
from .network_manager import NetworkManager
from .config_manager import ConfigManager
from .filesystem_manager import FilesystemManager


class VMLifecycle:
    """Manages VM create, destroy, start, stop, restart operations"""
    
    def __init__(self, vm_name_or_socket_path, config_manager=None):
        """Initialize VMLifecycle
        
        Args:
            vm_name_or_socket_path: Either a VM name or full socket path
            config_manager: ConfigManager instance
        """
        self.config_manager = config_manager or ConfigManager()
        
        # Determine if we got a VM name or full socket path
        if '/' in str(vm_name_or_socket_path):
            # It's a path
            self.socket_path = vm_name_or_socket_path
        else:
            # It's a VM name, get socket path from config_manager
            self.socket_path = self.config_manager.get_vm_socket_path(vm_name_or_socket_path)
        
        self.socket_path_prefix = self.config_manager.get_socket_path_prefix()
        self.api = FirecrackerAPI(self.socket_path)
        self.network_manager = NetworkManager()
        self.filesystem_manager = FilesystemManager(self.config_manager)
    
    def _run_command(self, cmd, check=True, capture_output=True, text=True):
        """Helper method to run subprocess commands with consistent error handling"""
        try:
            return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)
        except subprocess.CalledProcessError as e:
            if capture_output:
                print(f"Command failed: {' '.join(cmd)}\nError: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Unexpected error running command: {' '.join(cmd)}\nError: {e}", file=sys.stderr)
            raise
    
    def create_supervisor_config(self, vm_name, socket_path):
        """Create supervisord configuration for VM"""
        config_content = f"""[program:{vm_name}]
command=/usr/sbin/firecracker --id {vm_name} --api-sock {socket_path}
stdout_logfile=/var/log/{vm_name}.log
stderr_logfile=/var/log/{vm_name}.error.log
autostart=true
"""
        
        config_path = Path(f"/etc/supervisor/conf.d/{vm_name}.conf")
        
        try:
            config_path.write_text(config_content)
            print(f"✓ Supervisor config created: {config_path}")
            return True
        except Exception as e:
            print(f"Error creating supervisor config: {e}", file=sys.stderr)
            return False
    
    def remove_supervisor_config(self, vm_name):
        """Remove supervisord configuration for VM"""
        config_path = Path(f"/etc/supervisor/conf.d/{vm_name}.conf")
        
        try:
            if config_path.exists():
                config_path.unlink()
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
            self._run_command(["sudo", "supervisorctl", "update"])
            print("✓ Supervisor configuration reloaded")
            return True
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Error reloading supervisor: {e}", file=sys.stderr)
            return False
    
    def configure_and_start(self, vm_config):
        """Configure all VM settings and start the microVM
        
        Args:
            vm_config: Dictionary containing VM configuration
        """
        print("Configuring Firecracker VM...")
        
        # Extract configuration values
        cpus = vm_config['cpus']
        memory = vm_config['memory']
        kernel_path = vm_config['kernel_path']
        rootfs_path = vm_config['rootfs_path']
        tap_device = vm_config['tap_device']
        tap_ip = vm_config['tap_ip']
        vm_ip = vm_config['vm_ip']
        networkdriver = vm_config.get('networkdriver', 'internal')
        metadata = vm_config.get('metadata')
        mmds_tap = vm_config.get('mmds_tap')
        
        # Set machine configuration
        if not self.api.set_machine_config(cpus, memory):
            print("Failed to set machine configuration", file=sys.stderr)
            return False
        print(f"✓ Machine config set: {cpus} vCPUs, {memory} MiB RAM")

        # Set boot source
        if not self.api.set_boot_source(kernel_path):
            print("Failed to set boot source", file=sys.stderr)
            return False
        print(f"✓ Boot source set: {kernel_path}")

        # Set rootfs
        if not self.api.set_rootfs(rootfs_path):
            print("Failed to set rootfs", file=sys.stderr)
            return False
        print(f"✓ Rootfs set: {rootfs_path}")

        # Setup TAP device and networking
        if not self.network_manager.setup_tap_device(tap_device, tap_ip, vm_ip, networkdriver):
            print("Failed to setup TAP device", file=sys.stderr)
            return False

        # Set primary network interface (eth0)
        if not self.api.set_network_interface("eth0", tap_device):
            print("Failed to set network interface", file=sys.stderr)
            return False
        print(f"✓ Primary network interface set: eth0 -> {tap_device}")

        # Configure MMDS if metadata provided
        if metadata and mmds_tap:
            # Setup dedicated MMDS TAP device
            if not self.network_manager.setup_mmds_tap_device(mmds_tap, networkdriver):
                print("Failed to setup MMDS TAP device", file=sys.stderr)
                return False
            
            # Set dedicated MMDS network interface (mmds0)
            if not self.api.set_network_interface("mmds0", mmds_tap):
                print("Failed to set MMDS network interface", file=sys.stderr)
                return False
            print(f"✓ MMDS network interface set: mmds0 -> {mmds_tap}")
            
            # Configure which interface can access MMDS
            if not self.api.configure_mmds_interface("mmds0"):
                print("Failed to configure MMDS interface", file=sys.stderr)
                return False
            print("✓ MMDS interface configured")
            # Set the metadata
            if not self.api.set_mmds_metadata(metadata):
                print("Failed to set MMDS metadata", file=sys.stderr)
                return False
            print("✓ MMDS metadata configured")

        # Start the VM
        if not self.api.start_microvm():
            print("Failed to start microVM", file=sys.stderr)
            return False
        print("✓ MicroVM started successfully!")
        
        return True
    
    def create_vm_supervisor(self, vm_config):
        """Create VM using supervisor
        
        Args:
            vm_config: Dictionary containing VM configuration
        """
        vm_name = vm_config['vm_name']
        
        # Create supervisor config
        if not self.create_supervisor_config(vm_name, self.socket_path):
            return False
        
        # Reload supervisor to start Firecracker
        if not self.supervisor_reload():
            return False
        
        # Wait for Firecracker to be ready with retries
        max_retries = 10
        retry_delay = 1
        
        print("Waiting for Firecracker to start...")
        for attempt in range(max_retries):
            time.sleep(retry_delay)
            
            # Check if socket file exists
            socket_file = Path(self.socket_path)
            if not socket_file.exists():
                print(f"Attempt {attempt + 1}/{max_retries}: Socket file not yet created")
                continue
            
            # Check if Firecracker is listening
            if self.api.check_socket_in_use():
                print(f"✓ Firecracker is ready (attempt {attempt + 1})")
                break
            else:
                print(f"Attempt {attempt + 1}/{max_retries}: Firecracker not yet listening")
        else:
            print("Error: Firecracker failed to start within timeout period", file=sys.stderr)
            self._debug_firecracker_startup(vm_name)
            return False
        
        # Now configure the VM
        return self.configure_and_start(vm_config)
    
    def create_vm_foreground(self, vm_config):
        """Create VM in foreground mode for debugging
        
        Args:
            vm_config: Dictionary containing VM configuration
        """
        vm_name = vm_config['vm_name']
        tap_device = vm_config['tap_device']
        mmds_tap = vm_config.get('mmds_tap')
        networkdriver = vm_config.get('networkdriver', 'internal')
        
        print(f"Starting Firecracker in foreground mode...")
        print(f"Command: /usr/sbin/firecracker --id {vm_name} --api-sock {self.socket_path}")
        
        # Cleanup function for when process terminates
        def cleanup():
            print("\nCleaning up...")
            # Remove TAP device
            self.network_manager.remove_tap_device(tap_device, networkdriver)
            # Remove MMDS TAP device if it was used
            if mmds_tap:
                self.network_manager.remove_tap_device(mmds_tap, networkdriver)
            # Remove socket file
            socket_file = Path(self.socket_path)
            if socket_file.exists():
                socket_file.unlink()
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
            time.sleep(1)
            
            # Configure the VM
            config_success = self.configure_and_start(vm_config)
            
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
    
    def create_vm(self, args):
        """Create and start a new VM
        
        Args:
            args: Namespace object with all VM creation parameters from command line
        
        Returns:
            bool: True if VM created successfully, False otherwise
        """
        print(f"Creating VM: {args.name}...")
        
        # Step 1: Validate create-specific parameters
        success, error_msg = self.config_manager.validate_create_parameters(args)
        if not success:
            print(error_msg, file=sys.stderr)
            return False
        
        # Step 2: Validate external network driver requirements if applicable
        success, error_msg = self.config_manager.validate_external_network_parameters(args)
        if not success:
            print(error_msg, file=sys.stderr)
            return False
        
        # Step 3: Prepare network devices BEFORE creating rootfs to avoid zombie rootfs files
        result = self.network_manager.prepare_network_devices(args)
        if not result[0]:  # Check if tap_device was allocated successfully
            return False  # Error messages already printed by prepare_network_devices
        
        # Step 4: Prepare filesystem components (kernel and rootfs)
        kernel_path, rootfs_path = self.filesystem_manager.prepare_filesystem(args)
        if not kernel_path:
            return False  # Error messages already printed by prepare_filesystem
        
        # Step 5: Set hostname to VM name if not specified
        hostname = args.hostname if args.hostname else args.name
        
        # Step 6: Parse metadata (always include network_config since we always have MMDS TAP)
        metadata = self.config_manager.parse_metadata(args.metadata, args.tap_ip, args.vm_ip, hostname)
        if metadata is None:
            return False  # Error message already printed by parse_metadata
        
        # Step 7: Build VM configuration dictionary
        vm_config = {
            'vm_name': args.name,
            'kernel_path': kernel_path,
            'rootfs_path': rootfs_path,
            'tap_device': args.tap_device,
            'tap_ip': args.tap_ip,
            'vm_ip': args.vm_ip,
            'cpus': args.cpus,
            'memory': args.memory,
            'metadata': metadata,
            'mmds_tap': args.mmds_tap,
            'foreground': args.foreground,
            'hostname': hostname,
            'base_image': args.image,
            'networkdriver': args.networkdriver
        }
        
        # Step 8: Continue with the original create_vm logic
        vm_name = vm_config['vm_name']
        
        # Check if socket is in use
        if self.api.check_socket_in_use():
            print(f"Error: Socket {self.socket_path} is already in use", file=sys.stderr)
            return False
        
        # If socket file exists but nothing is listening, delete it
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            print(f"Removing stale socket file: {self.socket_path}")
            socket_file.unlink()
        
        success = False
        if vm_config.get('foreground', False):
            success = self.create_vm_foreground(vm_config)
        else:
            success = self.create_vm_supervisor(vm_config)
        
        # Save VM configuration to cache if creation was successful
        if success:
            if not self.config_manager.save_vm_config(
                vm_name, 
                vm_config['kernel_path'], 
                vm_config['rootfs_path'], 
                vm_config['tap_device'], 
                vm_config.get('mmds_tap'), 
                vm_config['vm_ip'], 
                vm_config['tap_ip'], 
                vm_config['cpus'], 
                vm_config['memory'], 
                vm_config.get('hostname', vm_name), 
                vm_config.get('base_image'), 
                vm_config.get('networkdriver', 'internal')
            ):
                print("Warning: Failed to save VM configuration to cache", file=sys.stderr)
        
        return success
    
    def destroy_vm(self, vm_name, force_destroy=False):
        """Destroy a VM and clean up all resources including rootfs"""
        print(f"Destroying VM: {vm_name}...")
        
        # 1. Check if VM is running and throw error if so
        if self.api.check_socket_in_use():
            print(f"Error: VM '{vm_name}' is currently running. Please stop the VM first using:", file=sys.stderr)
            print(f"  ./fcm stop --name {vm_name}", file=sys.stderr)
            return False
        
        # 2. Load VM config from cache to get TAP devices and rootfs path
        cache_data = self.config_manager.load_vm_config(vm_name)
        if not cache_data:
            print(f"Error: Cannot destroy VM '{vm_name}' - no cached configuration found", file=sys.stderr)
            print("This VM may have been created with an older version or the cache was deleted", file=sys.stderr)
            return False
        
        # Extract configuration from cache
        tap_device = cache_data.get('tap_device')
        mmds_tap = cache_data.get('mmds_tap')
        rootfs_path = cache_data.get('rootfs')
        networkdriver = cache_data.get('networkdriver', 'internal')  # Default to internal for backward compatibility
        
        # 3. Ask for confirmation unless force_destroy is specified
        if not force_destroy:
            print(f"\n⚠️  WARNING: This will permanently delete:")
            if rootfs_path:
                print(f"   - VM rootfs file: {rootfs_path}")
            
            # Only warn about TAP device removal for internal network mode
            if networkdriver == "internal":
                if tap_device:
                    print(f"   - TAP device: {tap_device}")
                if mmds_tap:
                    print(f"   - MMDS TAP device: {mmds_tap}")
            else:
                # For external mode, clarify that TAP devices will NOT be removed
                print(f"   - NOTE: TAP devices will NOT be removed (external network mode)")
            
            print(f"   - Supervisor configuration for '{vm_name}'")
            print(f"   - VM configuration cache")
            
            while True:
                response = input(f"\nAre you sure you want to destroy VM '{vm_name}'? (yes/no): ").strip().lower()
                if response in ['yes', 'y']:
                    break
                elif response in ['no', 'n']:
                    print("VM destruction cancelled.")
                    return False
                else:
                    print("Please enter 'yes' or 'no'")
        
        # 4. Remove socket file if it exists
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            socket_file.unlink()
            print(f"✓ Socket file removed: {self.socket_path}")
        
        # 5. Remove TAP devices using cached config
        if tap_device:
            if not self.network_manager.remove_tap_device(tap_device, networkdriver):
                print(f"Warning: Failed to remove TAP device {tap_device}", file=sys.stderr)
        else:
            print("✓ No main TAP device found in cache")
        
        if mmds_tap:
            if not self.network_manager.remove_tap_device(mmds_tap, networkdriver):
                print(f"Warning: Failed to remove MMDS TAP device {mmds_tap}", file=sys.stderr)
        else:
            print("✓ No MMDS TAP device found in cache")
        
        # 6. Delete rootfs file using cached config
        if rootfs_path:
            rootfs_file = Path(rootfs_path)
            if rootfs_file.exists():
                try:
                    rootfs_file.unlink()
                    print(f"✓ Rootfs file deleted: {rootfs_path}")
                except Exception as e:
                    print(f"Error: Failed to delete rootfs file {rootfs_path}: {e}", file=sys.stderr)
                    return False
            else:
                print(f"✓ Rootfs file doesn't exist: {rootfs_path}")
        else:
            print("✓ No rootfs path found in cache")
        
        # 7. Delete supervisor config
        if not self.remove_supervisor_config(vm_name):
            return False
        
        # Reload supervisor
        if not self.supervisor_reload():
            return False
        
        # 8. Remove VM configuration cache
        if not self.config_manager.remove_vm_config_cache(vm_name):
            print(f"Warning: Failed to remove configuration cache for VM {vm_name}", file=sys.stderr)
        
        print(f"✓ VM '{vm_name}' destroyed successfully!")
        return True
    
    def stop_vm(self, vm_name):
        """Stop a VM without removing TAP devices"""
        print(f"Stopping VM: {vm_name}...")
        
        try:
            # Stop the VM via supervisor
            result = self._run_command(["sudo", "supervisorctl", "stop", vm_name], check=False)
            
            if result.returncode == 0:
                print(f"✓ VM {vm_name} stopped successfully")
                
                # Remove socket file to allow clean restart
                socket_file = Path(self.socket_path)
                if socket_file.exists():
                    socket_file.unlink()
                    print(f"✓ Socket file removed: {self.socket_path}")
                else:
                    print(f"✓ Socket file doesn't exist: {self.socket_path}")
                
                return True
            else:
                print(f"Error: Failed to stop VM {vm_name}", file=sys.stderr)
                print(f"supervisorctl output: {result.stderr}", file=sys.stderr)
                return False
                
        except Exception as e:
            print(f"Error stopping VM: {e}", file=sys.stderr)
            return False
    
    def start_vm(self, vm_name):
        """Start a VM from cached configuration"""
        print(f"Starting VM: {vm_name}...")
        
        # Load VM configuration from cache
        cache_data = self.config_manager.load_vm_config(vm_name)
        if not cache_data:
            return False
        
        # Extract configuration values
        kernel_path = cache_data.get('kernel')
        rootfs_path = cache_data.get('rootfs')
        tap_device = cache_data.get('tap_device')
        mmds_tap = cache_data.get('mmds_tap')
        vm_ip = cache_data.get('vm_ip')
        tap_ip = cache_data.get('tap_ip')
        cpus = cache_data.get('cpus')
        memory = cache_data.get('memory')
        hostname = cache_data.get('hostname', vm_name)
        networkdriver = cache_data.get('networkdriver', 'internal')  # Default to internal for backward compatibility
        
        # Validate that all required values are present
        required_fields = ['kernel', 'rootfs', 'tap_device', 'mmds_tap', 'vm_ip', 'tap_ip', 'cpus', 'memory']
        missing_fields = [field for field in required_fields if not cache_data.get(field)]
        
        if missing_fields:
            print(f"Error: Missing required fields in cached config: {', '.join(missing_fields)}", file=sys.stderr)
            return False
        
        # Check if socket is in use
        if self.api.check_socket_in_use():
            print(f"Error: Socket {self.socket_path} is already in use", file=sys.stderr)
            return False
        
        # If socket file exists but nothing is listening, delete it
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            print(f"Removing stale socket file: {self.socket_path}")
            socket_file.unlink()
        
        # Start Firecracker process via supervisor
        try:
            result = self._run_command(["sudo", "supervisorctl", "start", vm_name], check=False)
            
            if result.returncode != 0:
                print(f"Error: Failed to start Firecracker process for VM {vm_name}", file=sys.stderr)
                print(f"supervisorctl output: {result.stderr}", file=sys.stderr)
                return False
            
            print(f"✓ Firecracker process started for VM {vm_name}")
            
        except Exception as e:
            print(f"Error starting Firecracker process: {e}", file=sys.stderr)
            return False
        
        # Wait a moment for Firecracker to start
        time.sleep(1)
        
        # Create metadata for MMDS
        metadata = self.config_manager.parse_metadata(None, tap_ip, vm_ip, hostname)
        if metadata is None:
            print("Error: Failed to create metadata for MMDS", file=sys.stderr)
            return False
        
        # Build VM configuration dictionary from cached data
        vm_config = {
            'vm_name': vm_name,
            'kernel_path': kernel_path,
            'rootfs_path': rootfs_path,
            'tap_device': tap_device,
            'tap_ip': tap_ip,
            'vm_ip': vm_ip,
            'cpus': cpus,
            'memory': memory,
            'metadata': metadata,
            'mmds_tap': mmds_tap,
            'hostname': hostname,
            'networkdriver': networkdriver
        }
        
        # Configure the VM using cached settings
        success = self.configure_and_start(vm_config)
        
        if success:
            print(f"✓ VM {vm_name} started successfully from cached configuration!")
        else:
            print(f"Error: Failed to configure and start VM {vm_name}", file=sys.stderr)
        
        return success
    
    def restart_vm(self, vm_name):
        """Restart a VM by stopping and then starting it"""
        print(f"Restarting VM: {vm_name}...")
        
        # First stop the VM
        print("Step 1: Stopping VM...")
        if not self.stop_vm(vm_name):
            print(f"Error: Failed to stop VM {vm_name}", file=sys.stderr)
            return False
        
        # Wait a moment between stop and start
        time.sleep(1)
        
        # Then start the VM
        print("Step 2: Starting VM...")
        if not self.start_vm(vm_name):
            print(f"Error: Failed to start VM {vm_name}", file=sys.stderr)
            return False
        
        print(f"✓ VM {vm_name} restarted successfully!")
        return True
    
    def _debug_firecracker_startup(self, vm_name):
        """Debug helper for Firecracker startup issues"""
        # Check supervisor status for debugging
        try:
            result = self._run_command(["sudo", "supervisorctl", "status", vm_name], check=False)
            print(f"Supervisor status: {result.stdout.strip()}", file=sys.stderr)
            if result.stderr.strip():
                print(f"Supervisor stderr: {result.stderr.strip()}", file=sys.stderr)
        except Exception as e:
            print(f"Could not check supervisor status: {e}", file=sys.stderr)
        
        # Check Firecracker logs for debugging
        log_files = [f"/var/log/{vm_name}.log", f"/var/log/{vm_name}.error.log"]
        for log_file in log_files:
            try:
                result = self._run_command(["sudo", "tail", "-20", log_file], check=False)
                if result.returncode == 0 and result.stdout.strip():
                    print(f"\n--- Last 20 lines of {log_file} ---", file=sys.stderr)
                    print(result.stdout, file=sys.stderr)
                elif result.returncode != 0:
                    print(f"Could not read {log_file}: {result.stderr.strip()}", file=sys.stderr)
            except Exception as e:
                print(f"Error reading {log_file}: {e}", file=sys.stderr)