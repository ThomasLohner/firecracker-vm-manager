#!/usr/bin/env python3
"""
Firecracker VM Manager Test Library
Consolidated test functions and utilities for testing FCM
"""

import subprocess
import json
import time
import signal
import sys
import os
from pathlib import Path
from datetime import datetime


class FCMTestLibrary:
    """Complete test library for Firecracker VM Manager"""
    
    def __init__(self):
        # Test configuration
        self.vm_base_name = "dev-test-vm"
        self.vm_ip_base = "10.254.254."
        self.tap_ip_base = "192.254.254."
        self.vm_ip_start = 250
        self.tap_ip_start = 250
        self.test_image = "alpine-v1.0.ext4"
        self.test_kernel = "vmlinux-6.1.141"
        # Use parent directory's fcm.sh
        self.fcm_cmd = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fcm.sh")
        
        # Load configuration to get directories
        self.config = self.load_config()
        
        # Set directories from config or use defaults
        self.socket_path_prefix = self.config.get('SOCKET_PATH_PREFIX', '/var/run/firecracker')
        self.kernel_path = self.config.get('KERNEL_PATH', '/var/lib/firecracker/kernels')
        self.images_path = self.config.get('IMAGES_PATH', '/var/lib/firecracker/images')
        self.rootfs_path = self.config.get('ROOTFS_PATH', '/var/lib/firecracker/rootfs')
        self.cache_dir = '/var/lib/firecracker/cache'  # Always fixed
        
        # Taboo list - never touch these resources
        self.taboo_list = {
            'vms': [],
            'tap_devices': [],
            'firecracker_pids': [],
            'supervisor_configs': [],
            'rootfs_files': []
        }
        
        # Test tracking
        self.test_results = []
        self.test_vms_created = []
        self.start_time = None
        self.verbose = False
        
    def load_config(self):
        """Load configuration from /etc/firecracker.env"""
        config = {}
        config_file = Path("/etc/firecracker.env")
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                # Strip inline comments
                                if '#' in value:
                                    value = value.split('#')[0]
                                config[key.strip()] = value.strip()
            except Exception as e:
                self.log(f"Warning: Could not read config file: {e}")
        
        return config
    
    def log(self, message, level="info"):
        """Log message with optional verbosity control"""
        if level == "error":
            print(f"❌ {message}", file=sys.stderr)
        elif level == "success":
            print(f"✅ {message}")
        elif level == "warning":
            print(f"⚠️  {message}")
        elif self.verbose or level == "info":
            print(f"  {message}")
    
    # ========== Setup and Teardown ==========
    
    def setup(self):
        """Record existing resources to protect"""
        self.log("Setting up test framework...", "info")
        self.log("-" * 60, "info")
        
        # Record existing VMs
        self.log("Recording existing VMs...", "info")
        result = subprocess.run([self.fcm_cmd, "list"], capture_output=True, text=True)
        if "No VMs found" not in result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines[2:]:  # Skip header lines
                if line and '|' in line:
                    parts = line.split('|')
                    if parts:
                        vm_name = parts[0].strip()
                        if vm_name and vm_name != "VM Name":
                            self.taboo_list['vms'].append(vm_name)
                            self.log(f"Found existing VM: {vm_name}")
        
        # Record existing TAP devices
        self.log("Recording existing TAP devices...", "info")
        result = subprocess.run(["ip", "link", "show"], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if ': tap' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    tap_name = parts[1].strip()
                    if tap_name.startswith('tap'):
                        self.taboo_list['tap_devices'].append(tap_name)
                        self.log(f"Found existing TAP device: {tap_name}")
        
        # Record existing Firecracker PIDs
        self.log("Recording existing Firecracker processes...", "info")
        socket_dir = Path(self.socket_path_prefix)
        if socket_dir.exists():
            for sock_file in socket_dir.glob("*.sock"):
                pid = self.get_firecracker_pid_from_socket(str(sock_file))
                if pid:
                    self.taboo_list['firecracker_pids'].append(pid)
                    self.log(f"Found existing Firecracker PID: {pid} ({sock_file.name})")
        
        # Record existing supervisor configs
        self.log("Recording existing supervisor configs...", "info")
        supervisor_dir = Path("/etc/supervisor/conf.d")
        if supervisor_dir.exists():
            for conf_file in supervisor_dir.glob("*.conf"):
                self.taboo_list['supervisor_configs'].append(conf_file.name)
                self.log(f"Found existing supervisor config: {conf_file.name}")
        
        # Record existing rootfs files
        self.log("Recording existing rootfs files...", "info")
        rootfs_dir = Path(self.rootfs_path)
        if rootfs_dir.exists():
            for rootfs_file in rootfs_dir.glob("*.ext4"):
                self.taboo_list['rootfs_files'].append(rootfs_file.name)
                self.log(f"Found existing rootfs file: {rootfs_file.name}")
        
        # Clean up any stale test VMs
        self.log("\nChecking for test VM conflicts...", "info")
        for i in range(1, 6):
            test_vm_name = f"{self.vm_base_name}-{i}"
            if test_vm_name in self.taboo_list['vms']:
                self.log(f"Warning: Test VM {test_vm_name} already exists! Cleaning up...", "warning")
                subprocess.run([self.fcm_cmd, "stop", "--name", test_vm_name], capture_output=True)
                subprocess.run([self.fcm_cmd, "destroy", "--name", test_vm_name, "--force-destroy"], capture_output=True)
        
        # Verify test resources exist
        self.log(f"Verifying test image {self.test_image} exists...", "info")
        result = subprocess.run([self.fcm_cmd, "images"], capture_output=True, text=True)
        if self.test_image not in result.stdout:
            raise Exception(f"Test image {self.test_image} not found! Please ensure it exists.")
        
        self.log(f"Verifying test kernel {self.test_kernel} exists...", "info")
        result = subprocess.run([self.fcm_cmd, "kernels"], capture_output=True, text=True)
        if self.test_kernel not in result.stdout:
            self.log(f"Warning: Test kernel {self.test_kernel} not found. Will use default kernel.", "warning")
            self.test_kernel = None
        
        self.log("\nSetup complete! Ready to run tests.", "success")
        self.log("=" * 60 + "\n", "info")
    
    def teardown(self):
        """Clean up all test resources"""
        self.log("\nRunning cleanup...", "info")
        self.log("-" * 60, "info")
        
        # Destroy all test VMs
        for i in range(1, 6):
            vm_name = f"{self.vm_base_name}-{i}"
            if vm_name not in self.taboo_list['vms']:  # Extra safety check
                self.log(f"Cleaning up {vm_name}...", "info")
                result = subprocess.run(
                    [self.fcm_cmd, "destroy", "--name", vm_name, "--force-destroy"],
                    capture_output=True, text=True
                )
                if "destroyed successfully" in result.stdout:
                    self.log(f"✓ {vm_name} destroyed")
                elif "no cached configuration found" in result.stdout:
                    self.log(f"✓ {vm_name} not found (already clean)")
        
        # Remove any test TAP devices (for external network tests)
        test_taps = ["test-tap0", "test-tap1"]
        for tap in test_taps:
            if tap not in self.taboo_list['tap_devices']:
                result = subprocess.run(
                    ["sudo", "ip", "link", "del", tap],
                    capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    self.log(f"✓ Removed test TAP device: {tap}")
        
        self.log("Cleanup complete!", "success")
    
    def emergency_cleanup(self):
        """Emergency cleanup of test resources"""
        self.log("⚠️  Running emergency cleanup...", "warning")
        for vm_name in self.test_vms_created[:]:
            try:
                self.destroy_vm(vm_name)
                self.log(f"Cleaned up {vm_name}")
            except:
                pass
    
    # ========== VM Management Helpers ==========
    
    def create_vm(self, suffix=1, cpus=None, memory=None, networkdriver="internal",
                  tap_device=None, mmds_tap=None, metadata=None):
        """Helper to create a test VM"""
        vm_name = f"{self.vm_base_name}-{suffix}"
        vm_ip = f"{self.vm_ip_base}{self.vm_ip_start + suffix - 1}"
        tap_ip = f"{self.tap_ip_base}{self.tap_ip_start + suffix - 1}"
        
        cmd = [
            self.fcm_cmd, "create",
            "--name", vm_name,
            "--image", self.test_image,
            "--rootfs-size", "1G",
            "--vm-ip", vm_ip,
            "--tap-ip", tap_ip,
            "--networkdriver", networkdriver
        ]
        
        if self.test_kernel:
            cmd.extend(["--kernel", self.test_kernel])
        if cpus:
            cmd.extend(["--cpus", str(cpus)])
        if memory:
            cmd.extend(["--memory", str(memory)])
        if tap_device:
            cmd.extend(["--tap-device", tap_device])
        if mmds_tap:
            cmd.extend(["--mmds-tap", mmds_tap])
        if metadata:
            cmd.extend(["--metadata", metadata])
        
        self.log(f"Creating VM: {vm_name}")
        self.log(f"VM IP: {vm_ip}, TAP IP: {tap_ip}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to create VM: {result.stderr}")
        
        self.test_vms_created.append(vm_name)
        time.sleep(3)  # Wait for VM to be ready
        
        return vm_name, vm_ip, tap_ip
    
    def destroy_vm(self, vm_name):
        """Helper to destroy a VM"""
        # First stop the VM if it's running
        subprocess.run([self.fcm_cmd, "stop", "--name", vm_name], capture_output=True, text=True)
        
        # Then destroy it
        cmd = [self.fcm_cmd, "destroy", "--name", vm_name, "--force-destroy"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "no cached configuration found" not in result.stderr:
            raise Exception(f"Failed to destroy VM: {result.stderr}")
        if vm_name in self.test_vms_created:
            self.test_vms_created.remove(vm_name)
    
    def stop_vm(self, vm_name):
        """Helper to stop a VM"""
        cmd = [self.fcm_cmd, "stop", "--name", vm_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to stop VM: {result.stderr}")
    
    def start_vm(self, vm_name):
        """Helper to start a VM"""
        cmd = [self.fcm_cmd, "start", "--name", vm_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to start VM: {result.stderr}")
        time.sleep(3)  # Wait for VM to be ready
    
    def restart_vm(self, vm_name):
        """Helper to restart a VM"""
        cmd = [self.fcm_cmd, "restart", "--name", vm_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to restart VM: {result.stderr}")
        time.sleep(3)  # Wait for VM to be ready
    
    def list_vms(self):
        """Get list of VMs"""
        cmd = [self.fcm_cmd, "list"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    
    # ========== Network and Validation Helpers ==========
    
    def ping_vm(self, vm_ip, count=3, timeout=5):
        """Test VM connectivity"""
        cmd = ["ping", "-c", str(count), "-W", str(timeout), vm_ip]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    
    def get_firecracker_pid_from_socket(self, socket_path):
        """Get PID of firecracker process from socket"""
        try:
            cmd = ["lsof", socket_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) > 1:
                        return int(parts[1])
        except:
            pass
        return None
    
    def get_firecracker_pid(self, vm_name):
        """Get PID of firecracker process for a VM"""
        socket_path = f"{self.socket_path_prefix}/{vm_name}.sock"
        return self.get_firecracker_pid_from_socket(socket_path)
    
    def kill_firecracker_process(self, pid):
        """Kill a firecracker process"""
        cmd = ["sudo", "kill", "-9", str(pid)]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    
    def get_tap_devices(self):
        """Get list of current TAP devices"""
        tap_devices = []
        result = subprocess.run(["ip", "link", "show"], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if ': tap' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    tap_name = parts[1].strip()
                    if tap_name.startswith('tap'):
                        tap_devices.append(tap_name)
        return tap_devices
    
    def check_tap_device_exists(self, tap_name):
        """Check if a specific TAP device exists"""
        result = subprocess.run(["ip", "link", "show", tap_name], 
                              capture_output=True, text=True)
        return result.returncode == 0
    
    # ========== API Query and Validation ==========
    
    def query_mmds(self, vm_name):
        """Query MMDS metadata via socket"""
        socket_path = f"{self.socket_path_prefix}/{vm_name}.sock"
        cmd = [
            "curl", "-s",
            "--unix-socket", socket_path,
            "http://localhost/mmds"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return None
        return None
    
    def query_vm_config(self, vm_name):
        """Query VM configuration via API"""
        socket_path = f"{self.socket_path_prefix}/{vm_name}.sock"
        cmd = [
            "curl", "-s",
            "--unix-socket", socket_path,
            "http://localhost/vm/config"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return None
        return None
    
    def verify_vm_config(self, vm_name, expected_cpus=None, expected_memory=None, expected_vm_ip=None):
        """Verify VM configuration matches expectations"""
        # Query API config
        api_config = self.query_vm_config(vm_name)
        if not api_config:
            raise Exception(f"Failed to query VM config for {vm_name}")
        
        # Load cache config
        cache_data = None
        cache_file = Path(f"{self.cache_dir}/{vm_name}.json")
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
        
        # Verify machine config
        machine_config = api_config.get('machine-config', {})
        actual_cpus = machine_config.get('vcpu_count')
        actual_memory = machine_config.get('mem_size_mib')
        
        if expected_cpus and actual_cpus != expected_cpus:
            raise Exception(f"CPU mismatch: expected {expected_cpus}, got {actual_cpus}")
        
        if expected_memory and actual_memory != expected_memory:
            raise Exception(f"Memory mismatch: expected {expected_memory}, got {actual_memory}")
        
        # Verify against cache if it exists
        if cache_data:
            if cache_data.get('cpus') != actual_cpus:
                raise Exception(f"Cache CPU mismatch: cache has {cache_data.get('cpus')}, API has {actual_cpus}")
            if cache_data.get('memory') != actual_memory:
                raise Exception(f"Cache memory mismatch: cache has {cache_data.get('memory')}, API has {actual_memory}")
            
            # Verify network config
            if expected_vm_ip and cache_data.get('vm_ip') != expected_vm_ip:
                raise Exception(f"Cache VM IP mismatch: expected {expected_vm_ip}, cache has {cache_data.get('vm_ip')}")
        
        self.log(f"✓ VM config verified: {actual_cpus} CPUs, {actual_memory} MiB RAM")
        return True
    
    def check_cache_exists(self, vm_name):
        """Check if cache file exists for a VM"""
        cache_file = Path(f"{self.cache_dir}/{vm_name}.json")
        return cache_file.exists()
    
    # ========== Test Implementations ==========
    
    def test_basic_lifecycle(self):
        """Test basic VM lifecycle operations"""
        vm_name, vm_ip, tap_ip = self.create_vm(suffix=1)
        
        # Verify VM is running
        vm_list = self.list_vms()
        assert vm_name in vm_list, f"VM {vm_name} not in list"
        assert "running" in vm_list, "VM not showing as running"
        
        # Test connectivity
        assert self.ping_vm(vm_ip), f"Cannot ping VM at {vm_ip}"
        self.log(f"✓ VM is pingable at {vm_ip}")
        
        # Verify VM config via API
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Stop VM
        self.stop_vm(vm_name)
        time.sleep(2)
        vm_list = self.list_vms()
        assert "stopped" in vm_list or vm_name in vm_list, "VM not showing as stopped"
        self.log("✓ VM stopped successfully")
        
        # Start VM
        self.start_vm(vm_name)
        assert self.ping_vm(vm_ip), f"Cannot ping VM after start at {vm_ip}"
        self.log("✓ VM started and pingable")
        
        # Verify config still matches after restart
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Restart VM
        self.restart_vm(vm_name)
        assert self.ping_vm(vm_ip), f"Cannot ping VM after restart at {vm_ip}"
        self.log("✓ VM restart command works")
        
        # Verify config after restart command
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Destroy VM
        self.destroy_vm(vm_name)
        vm_list = self.list_vms()
        assert vm_name not in vm_list, f"VM {vm_name} still in list after destroy"
        self.log("✓ VM destroyed successfully")
    
    def test_config_overrides(self):
        """Test configuration override functionality"""
        test_configs = [
            (1, None, None, "Test defaults from config", 1, 1024),
            (2, 2, None, "Test CPU override", 2, 1024),
            (3, None, 512, "Test memory override", 1, 512),
            (4, 4, 2048, "Test both overrides", 4, 2048)
        ]
        
        for suffix, cpus, memory, desc, expected_cpus, expected_memory in test_configs:
            self.log(f"Testing: {desc}")
            vm_name, vm_ip, _ = self.create_vm(suffix=suffix, cpus=cpus, memory=memory)
            
            # Verify VM is running and pingable
            assert self.ping_vm(vm_ip), f"Cannot ping VM {vm_name}"
            self.log(f"✓ VM {vm_name} is pingable")
            
            # Verify config via API
            self.verify_vm_config(vm_name, expected_cpus=expected_cpus, expected_memory=expected_memory, expected_vm_ip=vm_ip)
            
            # Check configuration in list output
            vm_list = self.list_vms()
            assert str(expected_cpus) in vm_list, f"CPU count {expected_cpus} not shown in list"
            assert str(expected_memory) in vm_list, f"Memory {expected_memory} not shown in list"
            
            # Clean up
            self.destroy_vm(vm_name)
            self.log(f"✓ Config test {suffix} passed")
    
    def test_concurrent_vms(self):
        """Test multiple concurrent VMs"""
        vms = []
        
        # Create 3 VMs
        for i in range(1, 4):
            vm_name, vm_ip, tap_ip = self.create_vm(suffix=i)
            vms.append((vm_name, vm_ip, tap_ip))
            self.log(f"✓ Created {vm_name}")
        
        # Verify all VMs are pingable and configs are correct
        for vm_name, vm_ip, _ in vms:
            assert self.ping_vm(vm_ip), f"Cannot ping {vm_name} at {vm_ip}"
            self.log(f"✓ {vm_name} is pingable at {vm_ip}")
            
            # Verify config via API
            self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Verify all show in list
        vm_list = self.list_vms()
        for vm_name, _, _ in vms:
            assert vm_name in vm_list, f"{vm_name} not in list"
        self.log("✓ All VMs show in list")
        
        # Clean up all VMs
        for vm_name, _, _ in vms:
            self.destroy_vm(vm_name)
            self.log(f"✓ Destroyed {vm_name}")
    
    def test_internal_driver(self):
        """Test internal network driver behavior"""
        # Get TAP devices before
        taps_before = set(self.get_tap_devices())
        
        # Create VM with internal driver (default)
        vm_name, vm_ip, _ = self.create_vm(suffix=1)
        
        # Get TAP devices after creation
        taps_after = set(self.get_tap_devices())
        new_taps = taps_after - taps_before
        assert len(new_taps) >= 2, "Internal driver should create at least 2 TAP devices"
        self.log(f"✓ Internal driver created TAP devices: {new_taps}")
        
        # Verify connectivity
        assert self.ping_vm(vm_ip), f"Cannot ping VM at {vm_ip}"
        self.log("✓ VM is pingable")
        
        # Verify config
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Destroy VM
        self.destroy_vm(vm_name)
        
        # Verify TAP devices are removed
        taps_final = set(self.get_tap_devices())
        remaining_new_taps = new_taps & taps_final
        assert len(remaining_new_taps) == 0, f"TAP devices not removed: {remaining_new_taps}"
        self.log("✓ TAP devices removed after destroy")
    
    def test_external_driver(self):
        """Test external network driver behavior"""
        # Create external TAP devices
        test_tap = "test-tap0"
        test_mmds_tap = "test-tap1"
        vm_ip = "10.254.254.253"
        tap_ip = "192.254.254.253"
        
        self.log("Creating external TAP devices...")
        
        # Create main TAP device
        subprocess.run(["sudo", "ip", "tuntap", "add", test_tap, "mode", "tap"], check=True)
        subprocess.run(["sudo", "ip", "addr", "add", f"{tap_ip}/32", "dev", test_tap], check=True)
        subprocess.run(["sudo", "ip", "link", "set", test_tap, "up"], check=True)
        subprocess.run(["sudo", "ip", "route", "add", f"{vm_ip}/32", "dev", test_tap], check=True)
        
        # Create MMDS TAP device
        subprocess.run(["sudo", "ip", "tuntap", "add", test_mmds_tap, "mode", "tap"], check=True)
        subprocess.run(["sudo", "ip", "link", "set", test_mmds_tap, "up"], check=True)
        
        self.log("✓ Created external TAP devices")
        
        try:
            # Create VM with external driver
            vm_name = f"{self.vm_base_name}-3"
            cmd = [
                self.fcm_cmd, "create",
                "--name", vm_name,
                "--image", self.test_image,
                "--rootfs-size", "1G",
                "--vm-ip", vm_ip,
                "--tap-ip", tap_ip,
                "--tap-device", test_tap,
                "--mmds-tap", test_mmds_tap,
                "--networkdriver", "external"
            ]
            if self.test_kernel:
                cmd.extend(["--kernel", self.test_kernel])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Failed to create VM with external driver: {result.stderr}")
            
            self.test_vms_created.append(vm_name)
            time.sleep(3)
            
            # Verify connectivity
            assert self.ping_vm(vm_ip), f"Cannot ping VM at {vm_ip}"
            self.log("✓ VM with external driver is pingable")
            
            # Verify config
            self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
            
            # Destroy VM
            self.destroy_vm(vm_name)
            
            # Verify TAP devices still exist (not removed by external driver)
            assert self.check_tap_device_exists(test_tap), f"External TAP {test_tap} was removed (shouldn't be)"
            assert self.check_tap_device_exists(test_mmds_tap), f"External TAP {test_mmds_tap} was removed (shouldn't be)"
            self.log("✓ External TAP devices preserved after destroy")
            
        finally:
            # Clean up test TAP devices
            subprocess.run(["sudo", "ip", "link", "del", test_tap], capture_output=True)
            subprocess.run(["sudo", "ip", "link", "del", test_mmds_tap], capture_output=True)
            self.log("✓ Cleaned up test TAP devices")
    
    def test_kill_recovery(self):
        """Test recovery from killed firecracker process"""
        vm_name, vm_ip, _ = self.create_vm(suffix=1)
        
        # Get firecracker PID
        pid = self.get_firecracker_pid(vm_name)
        assert pid is not None, f"Could not find PID for {vm_name}"
        self.log(f"Found Firecracker PID: {pid}")
        
        # Kill the process
        assert self.kill_firecracker_process(pid), "Failed to kill firecracker process"
        self.log("✓ Killed Firecracker process")
        time.sleep(2)
        
        # VM should no longer be pingable
        assert not self.ping_vm(vm_ip, count=1, timeout=2), "VM still pingable after kill"
        self.log("✓ VM is not pingable after kill")
        
        # Stop VM to clean up socket
        self.stop_vm(vm_name)
        self.log("✓ Stopped VM to clean up socket")
        
        # Start VM from cache
        self.start_vm(vm_name)
        self.log("✓ Started VM from cache")
        
        # Verify VM is pingable again
        assert self.ping_vm(vm_ip), "VM not pingable after recovery"
        self.log("✓ VM recovered and pingable")
        
        # Verify config after recovery
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Clean up
        self.destroy_vm(vm_name)
    
    def test_mmds(self):
        """Test MMDS metadata functionality"""
        metadata = '{"test": "data", "version": "1.0"}'
        vm_name, vm_ip, _ = self.create_vm(suffix=1, metadata=metadata)
        
        # Verify VM is pingable
        assert self.ping_vm(vm_ip), f"Cannot ping VM at {vm_ip}"
        self.log("✓ VM is pingable")
        
        # Query MMDS
        time.sleep(2)  # Give MMDS time to initialize
        mmds_data = self.query_mmds(vm_name)
        assert mmds_data is not None, "Failed to query MMDS"
        self.log("✓ MMDS query successful")
        
        # Verify our metadata is present
        assert "test" in mmds_data, "Test metadata not found"
        assert mmds_data["test"] == "data", "Test metadata value incorrect"
        self.log("✓ Custom metadata present")
        
        # Verify network_config was added automatically
        assert "network_config" in mmds_data, "network_config not found"
        assert mmds_data["network_config"]["ip"] == vm_ip, "VM IP not in network_config"
        self.log("✓ network_config automatically added")
        
        # Clean up
        self.destroy_vm(vm_name)
    
    def test_cache_persistence(self):
        """Test cache persistence functionality"""
        vm_name, vm_ip, _ = self.create_vm(suffix=1)
        
        # Verify cache file exists
        assert self.check_cache_exists(vm_name), f"Cache file not created for {vm_name}"
        self.log("✓ Cache file created")
        
        # Verify VM is pingable
        assert self.ping_vm(vm_ip), f"Cannot ping VM at {vm_ip}"
        self.log("✓ VM is pingable")
        
        # Verify initial config
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Stop VM
        self.stop_vm(vm_name)
        assert self.check_cache_exists(vm_name), "Cache file removed after stop"
        self.log("✓ Cache file persists after stop")
        
        # Start VM (should use cached config)
        self.start_vm(vm_name)
        assert self.ping_vm(vm_ip), "VM not pingable after start from cache"
        self.log("✓ VM started from cache and pingable")
        
        # Verify config matches after cache start
        self.verify_vm_config(vm_name, expected_cpus=1, expected_memory=1024, expected_vm_ip=vm_ip)
        
        # Destroy VM
        self.destroy_vm(vm_name)
        assert not self.check_cache_exists(vm_name), "Cache file not removed after destroy"
        self.log("✓ Cache file removed after destroy")
    
    def test_tap_allocation(self):
        """Test TAP device allocation and reuse"""
        taps_initial = set(self.get_tap_devices())
        
        # Create VM 1
        vm1_name, vm1_ip, _ = self.create_vm(suffix=1)
        taps_vm1 = set(self.get_tap_devices()) - taps_initial
        self.log(f"VM1 got TAP devices: {taps_vm1}")
        
        # Verify VM1 connectivity
        assert self.ping_vm(vm1_ip), f"Cannot ping VM1 at {vm1_ip}"
        self.log("✓ VM1 is pingable")
        
        # Create VM 2
        vm2_name, vm2_ip, _ = self.create_vm(suffix=2)
        taps_vm2 = set(self.get_tap_devices()) - taps_initial - taps_vm1
        self.log(f"VM2 got TAP devices: {taps_vm2}")
        
        # Verify VM2 connectivity
        assert self.ping_vm(vm2_ip), f"Cannot ping VM2 at {vm2_ip}"
        self.log("✓ VM2 is pingable")
        
        # Verify no overlap
        assert len(taps_vm1 & taps_vm2) == 0, "TAP devices overlap between VMs"
        self.log("✓ No TAP device conflicts")
        
        # Destroy VM1
        self.destroy_vm(vm1_name)
        
        # Create VM3 (should reuse VM1's TAP devices)
        vm3_name, vm3_ip, _ = self.create_vm(suffix=3)
        taps_vm3 = set(self.get_tap_devices()) - taps_vm2 - taps_initial
        
        # Verify VM3 connectivity
        assert self.ping_vm(vm3_ip), f"Cannot ping VM3 at {vm3_ip}"
        self.log("✓ VM3 is pingable")
        
        # Check if VM3 reused VM1's TAP range
        self.log(f"VM3 got TAP devices: {taps_vm3}")
        self.log("✓ TAP allocation working correctly")
        
        # Clean up
        self.destroy_vm(vm2_name)
        self.destroy_vm(vm3_name)
    
    def test_error_handling(self):
        """Test error handling"""
        # Test 1: Create with non-existent image
        self.log("Testing non-existent image...")
        cmd = [
            self.fcm_cmd, "create",
            "--name", f"{self.vm_base_name}-1",
            "--image", "non-existent.ext4",
            "--rootfs-size", "1G",
            "--vm-ip", "10.254.254.250",
            "--tap-ip", "192.254.254.250"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0, "Should fail with non-existent image"
        self.log("✓ Non-existent image error handled")
        
        # Test 2: Create duplicate VM
        self.log("Testing duplicate VM creation...")
        vm_name, _, _ = self.create_vm(suffix=1)
        
        cmd = [
            self.fcm_cmd, "create",
            "--name", vm_name,  # Same name
            "--image", self.test_image,
            "--rootfs-size", "1G",
            "--vm-ip", "10.254.254.251",
            "--tap-ip", "192.254.254.251"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0, "Should fail with duplicate VM name"
        self.log("✓ Duplicate VM error handled")
        
        # Clean up
        self.destroy_vm(vm_name)
        
        # Test 3: Stop non-existent VM
        self.log("Testing stop non-existent VM...")
        result = subprocess.run(
            [self.fcm_cmd, "stop", "--name", "non-existent-vm"],
            capture_output=True, text=True
        )
        assert result.returncode != 0, "Should fail stopping non-existent VM"
        self.log("✓ Stop non-existent VM error handled")
    
    def test_list_command(self):
        """Test list command output"""
        # Create multiple VMs with different configs
        vms = []
        vms.append(self.create_vm(suffix=1, cpus=1, memory=512))
        vms.append(self.create_vm(suffix=2, cpus=2, memory=1024))
        
        # Get list output
        vm_list = self.list_vms()
        
        # Verify all VMs appear and are pingable
        for vm_name, vm_ip, tap_ip in vms:
            assert vm_name in vm_list, f"{vm_name} not in list"
            assert vm_ip in vm_list, f"IP {vm_ip} not in list"
            assert self.ping_vm(vm_ip), f"Cannot ping {vm_name} at {vm_ip}"
            self.log(f"✓ {vm_name} appears in list and is pingable")
        
        # Verify columns are present
        assert "State" in vm_list, "State column missing"
        assert "CPUs" in vm_list, "CPUs column missing"
        assert "Memory" in vm_list, "Memory column missing"
        assert "TAP Interface" in vm_list, "TAP Interface column missing"
        self.log("✓ All expected columns present")
        
        # Clean up
        for vm_name, _, _ in vms:
            self.destroy_vm(vm_name)
    
    # ========== Test Execution ==========
    
    def run_test(self, test_name, test_func):
        """Execute a test with error handling"""
        print(f"\n🧪 Running test: {test_name}")
        print("-" * 40)
        
        start_time = time.time()
        try:
            test_func()
            duration = time.time() - start_time
            self.test_results.append((test_name, "PASS", None, duration))
            self.log(f"{test_name} PASSED ({duration:.2f}s)", "success")
            return True
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append((test_name, "FAIL", str(e), duration))
            self.log(f"{test_name} FAILED: {e} ({duration:.2f}s)", "error")
            # Try to clean up after failed test
            self.emergency_cleanup()
            return False
    
    def generate_report(self):
        """Generate test report"""
        print("\n" + "=" * 60)
        print("TEST REPORT")
        print("=" * 60)
        
        passed = sum(1 for _, status, _, _ in self.test_results if status == "PASS")
        failed = sum(1 for _, status, _, _ in self.test_results if status == "FAIL")
        total_time = sum(duration for _, _, _, duration in self.test_results)
        
        print(f"Total Tests: {len(self.test_results)}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Total Time: {total_time:.2f}s")
        
        if failed > 0:
            print("\n❌ Failed Tests:")
            for name, status, error, duration in self.test_results:
                if status == "FAIL":
                    print(f"  - {name} ({duration:.2f}s)")
                    print(f"    Error: {error}")
        
        print("\n📊 Test Details:")
        for name, status, _, duration in self.test_results:
            icon = "✅" if status == "PASS" else "❌"
            print(f"  {icon} {name}: {duration:.2f}s")
        
        return failed == 0