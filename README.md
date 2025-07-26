# Firecracker VM Manager (fcm)
A comprehensive Python script for managing Firecracker microVMs with automatic `supervisord` integration and network configuration.


## ⚠️ AI Disclaimer
> This tool was built with the help of Claude AI. AI tools make our lives easier—but **understanding what happens under the hood** is crucial if you're a developer.  
>
> Please read the following quick summary to grasp the core ideas behind Firecracker. If you're already familiar, jump straight to [firecracker_vm_manager.md](firecracker_vm_manager.md)


## 📚 Table of Contents

- [What is Firecracker?](#-what-is-firecracker)
- [Core Concepts](#-core-concepts)
- [Networking Basics](#-networking-basics)
- [Launch Your First VM](#launch-your-first-vm-)
  - [1. Download Firecracker Binary](#1-download-firecracker-binary)
  - [2. Create a tap Device on Host](#2-create-a-tap-device-on-host)
  - [3. Download Kernel Image](#3-download-kernel-image)
  - [4. Create Root Filesystem](#4-create-root-filesystem)
  - [5. Create VM Config File](#5-create-vm-config-file)
  - [6. Start the VM](#6-start-the-vm)
  - [7. Connect via SSH](#7-connect-via-ssh)
- [Next Steps: Use firecracker_vm_manager.py](#-next-steps-use-firecracker_vm_managerpy)
- [Advanced Topics](#-advanced-topics)
- [Illustrations](#-illustrations)

## 🔥 What is Firecracker?
Firecracker is an open-source virtualization technology built for running serverless workloads in **microVMs**—lightweight, fast-booting VMs with excellent isolation. It's used by AWS Lambda and other modern systems to blend the performance of containers with the isolation of VMs.

**Useful Links:**
🔗 [Website](https://firecracker-microvm.github.io)
🧑‍💻 [GitHub Repository](https://github.com/firecracker-microvm/firecracker/)
📚 [Docs](https://github.com/firecracker-microvm/firecracker/tree/main/docs)
🚀 [Getting Started Guide](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)

## 🧠 Core Concepts
- Each **Firecracker process** represents a single VM.
- Each VM has a **dedicated API socket**, e.g. `/tmp/vm1.sock`.
- **Starting the Firecracker process does not boot the VM**. You must configure it via the API first.
- VM configuration (kernel, drives, network, etc.) is done via `curl` to the socket.
- You start the VM using the `InstanceStart` API call.
- **Rebooting from inside the VM shuts it down** and exits the Firecracker process.
- You need to manually **remove the socket file** after Firecracker exits.
- To boot automatically, pass a JSON config to `firecracker --config-file`.

## 🌐 Networking Basics
- Create a dedicated `tap` device for each VM.
- Apply routing, firewall, and NAT (`MASQUERADE`) rules on this interface.
- VMs attach to this `tap` device.
- After every boot, the guest VM has:
  - No default route
  - No DNS config (`/etc/resolv.conf` is empty)

## Launch your first VM 🚀

### 1. Download Firecracker Binary
Go to the [Releases](https://github.com/firecracker-microvm/firecracker/releases) and download the latest version.
```bash
wget https://github.com/firecracker-microvm/firecracker/releases/download/v1.12.1/firecracker-v1.12.1-x86_64.tgz

tar xfvz firecracker-v1.12.1-x86_64.tgz

cp release-v1.12.1-x86_64/firecracker-v1.12.1-x86_64 /usr/sbin/firecracker

cp release-v1.12.1-x86_64/jailer-v1.12.1-x86_64 /usr/sbin/jailer

rm -rf release-v1.12.1-x86_64 firecracker-v1.12.1-x86_64.tgz
```

### 2. Create a tap device on host
Run the following commands as `root`:
```bash
ip tuntap add dev tap0 mode tap
ip addr add 172.16.0.1/30 dev tap0
ip link set dev tap0 up

# enable ip forwarding on host system
echo 1 > /proc/sys/net/ipv4/ip_forward

# set up internet access
sudo iptables -t nat -A POSTROUTING -o <YOUR_EXTERNAL_HOST_IFACE> -j MASQUERADE
```

### 3. Download Kernel Image
Use a prebuilt kernel, see [getting-a-rootfs-and-guest-kernel-image](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#getting-a-rootfs-and-guest-kernel-image ) for latest version.
```bash
cd /root
wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.12/x86_64/vmlinux-6.1.128
```

### 4. Create Root Filesystem
Use prebuilt Ubuntu Images for Firecracker, see [getting-a-rootfs-and-guest-kernel-image](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#getting-a-rootfs-and-guest-kernel-image ) for latest version.
```bash
cd /root

# Download & uncompress Ubuntu
wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.12/x86_64/ubuntu-24.04.squashfs

unsquashfs ubuntu-24.04.squashfs
# you can make changes to the filesystem in 
# squashfs-root folder. for example add
# your ssh key to ./squashfs-root/root/.ssh/authorized_keys

# Create empty image file for vm
truncate -s 1g ubuntu-vm1.ext4

# Copy rootfs to image
mkfs.ext4 -d squashfs-root -F ubuntu-vm1.ext4
```

### 5. Create VM config file
`/root/vm1.conf.json`
```json
{
"boot-source": {
    "kernel_image_path": "/root/vmlinux-6.1.128",
    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
    "initrd_path": null
},
"drives": [
    {
    "drive_id": "rootfs",
    "partuuid": null,
    "is_root_device": true,
    "cache_type": "Unsafe",
    "is_read_only": false,
    "path_on_host": "/root/ubuntu-vm1.ext4",
    "io_engine": "Sync",
    "rate_limiter": null,
    "socket": null
    }
],
"machine-config": {
    "vcpu_count": 2,
    "mem_size_mib": 1024,
    "smt": false,
    "track_dirty_pages": false,
    "huge_pages": "None"
},
"cpu-config": null,
"balloon": null,
"network-interfaces": [
    {
    "iface_id": "eth0",
    "host_dev_name": "tap0",
    "guest_mac": "06:00:AC:10:00:02",
    "rx_rate_limiter": null,
    "tx_rate_limiter": null
    }
],
"vsock": null,
"logger": null,
"metrics": null,
"mmds-config": null,
"entropy": null
}
```
*📝 Note: The Ubuntu image includes a script `fcnet-setup.sh` that calculates the internal IP from the MAC address. For custom images, you’ll need to replicate that logic or inject metadata via [MMDS](https://github.com/firecracker-microvm/firecracker/blob/main/docs/mmds/mmds-user-guide.md)..*

### 6. Start the VM
```bash
firecracker --api-sock /tmp/vm1.sock --config-file vm1.conf.json
```

### 7. Connect via ssh
If you have added your ssh key, in a new terminal window connect to the vm:
```bash
# after you added your ssh key to the vm
ssh root@172.16.0.2

# add default route
ip route add default via 172.16.0.1 dev eth0

# add nameserver
echo 'nameserver 8.8.8.8' > /etc/resolv.conf

ping www.google.de -c 3

# shut down vm
reboot
```
*🔁 Note: Default route and DNS must be set after every reboot unless automated via cloud-init or similar.*

## 🧰 Next Steps: Use firecracker_vm_manager.py
Congrats! You’ve booted your first VM manually! 🎉  
Now head over to [firecracker_vm_manager.md](firecracker_vm_manager.md) to automate everything with FCM.

## 🛠️ Advanced Topics
* [Build Custom Kernel](Build_custom_kernel.md)
* [Build Custom rootFS (Images)](Build_custom_rootfs.md)

## 🖼️ Illustrations
### Firecracker VM Lifecycle
```
             +----------------------------+
             |  Start Firecracker Process |
             |  (creates API socket)      |
             +------------+---------------+
                          |
                          v
             +----------------------------+
             |  Configure via API socket  |
             |  - Kernel                  |
             |  - RootFS                  |
             |  - CPU / Memory            |
             |  - Network Interface       |
             +------------+---------------+
                          |
                          v
             +----------------------------+
             |  Call `InstanceStart`      |
             |  (boots microVM)           |
             +------------+---------------+
                          |
                          v
             +----------------------------+
             |  Guest OS boots            |
             |  - `init` starts           |
             |  - No default route        |
             |  - No DNS configured       |
             +------------+---------------+
                          |
                          v
             +----------------------------+
             |  Inside VM: `reboot`       |
             |  Firecracker process exits |
             |  Socket needs cleanup      |
             +----------------------------+
```

## 🌐 Network Setup (tap0 + NAT)
```
                    [ External Network ]
                            |
                            v
                +------------------------+
                |  Host Network Interface|
                |  (eth0, wlan0, etc.)   |
                +-----------+------------+
                            |
                MASQUERADE NAT via iptables
                            |
                            v
+----------------------+        +----------------------+
| Guest VM             |        | Host Machine         |
|----------------------|        |----------------------|
| eth0: 172.16.0.2     |   <->  | tap0: 172.16.0.1     |
| Gateway: 172.16.0.1  |        | IP forwarding ON     |
| DNS: 8.8.8.8         |        |                      |
+----------------------+        +----------------------+
```