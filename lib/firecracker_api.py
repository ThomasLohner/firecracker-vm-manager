#!/usr/bin/env python3

import requests
import requests_unixsocket
import sys
from pathlib import Path


class FirecrackerAPI:
    """Core Firecracker API client for HTTP requests and configuration"""
    
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
    
    def get_vm_config(self):
        """Get VM configuration from Firecracker API"""
        try:
            response = self.session.get(f"{self.base_url}/vm/config")
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception:
            return None
    
    def get_mmds_data(self):
        """Get MMDS data from Firecracker API"""
        try:
            response = self.session.get(f"{self.base_url}/mmds")
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
    
    def set_boot_source(self, kernel_path, boot_args="console=ttyS0 reboot=k panic=1 pci=off"):
        """Set the boot source for the VM"""
        kernel_file = Path(kernel_path)
        if not kernel_file.exists():
            print(f"Error: Kernel file {kernel_path} does not exist", file=sys.stderr)
            return False
        
        data = {
            "kernel_image_path": str(kernel_file.absolute()),
            "boot_args": boot_args
        }
        return self._make_request("PUT", "/boot-source", data)
    
    def set_rootfs(self, rootfs_path):
        """Set the root filesystem drive"""
        rootfs_file = Path(rootfs_path)
        if not rootfs_file.exists():
            print(f"Error: Rootfs file {rootfs_path} does not exist", file=sys.stderr)
            return False
        
        data = {
            "drive_id": "rootfs",
            "path_on_host": str(rootfs_file.absolute()),
            "is_root_device": True,
            "is_read_only": False
        }
        return self._make_request("PUT", "/drives/rootfs", data)
    
    def set_machine_config(self, vcpu_count, mem_size_mib):
        """Set machine configuration (CPU and memory)"""
        data = {
            "vcpu_count": vcpu_count,
            "mem_size_mib": mem_size_mib
        }
        return self._make_request("PUT", "/machine-config", data)
    
    def set_network_interface(self, iface_id, host_dev_name):
        """Set network interface configuration"""
        data = {
            "iface_id": iface_id,
            "host_dev_name": host_dev_name
        }
        return self._make_request("PUT", f"/network-interfaces/{iface_id}", data)
    
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
    
    def start_microvm(self):
        """Start the microVM"""
        data = {
            "action_type": "InstanceStart"
        }
        return self._make_request("PUT", "/actions", data)