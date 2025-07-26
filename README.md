# Firecracker VM Manager (fcm)

A comprehensive Python script for managing Firecracker microVMs with automatic supervisord integration and network configuration.

## AI disclaimer
>This Tool was built with Claude AI. Using **AI Tools** makes our life easy. However, as a developer it's super important to still understand how things work under hood. Please read this quick summary to understand the core concepts of Firecracker. If you already know Firecracker you can skip to [firecracker_vm_manager.md](firecracker_vm_manager.md)

## What is Firecracker?

Firecracker is an open source virtualization technology that is purpose-built for creating and managing secure, multi-tenant container and function-based services that provide serverless operational models. Firecracker runs workloads in lightweight virtual machines, called microVMs, which combine the security and isolation properties provided by hardware virtualization technology with the speed and flexibility of containers.

*Useful Links:*
>Web: https://firecracker-microvm.github.io\
  Code: https://github.com/firecracker-microvm/firecracker/\
  Docs: https://github.com/firecracker-microvm/firecracker/tree/main/docs\
  Copy & Paste Getting Started Guide: https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md

## Core Concepts
* Each **process instance** of the firecracker binary represents a vm
* Each **vm** has a dedicated api listening on a socket (i.e. */tmp/vm1.sock*)
* Starting the firecracker process **does not start the vm**
* The **running** process is configured with *boot image, rootFS, network device, cpu & memory* etc. via `curl --unix-socket /tmp/vm1.sock ...`
* The api endpoint `InstanceStart` boots the vm
* `reboot` inside the vm shuts it down and exits the firecracker process
* The socket file must be removed by hand after firecracker proccess exits
* To immedieatly boot the vm when starting the process use `firecracker --config-file`

## Networking
* Create a dedicated `tap` interface on the host for each vm
* Apply *firewall / routing / MASQUERADE* rules to this interface
* Start a vm that attaches to this interface
* After **each** boot the guest network interface inside the vm does not have any routing info and no nameserver in `/etc/resolv.conf`

## Launch your first VM 🚀

### 1. Download the binary
(see [releases](https://github.com/firecracker-microvm/firecracker/releases) for latest version)
```bash
wget https://github.com/firecracker-microvm/firecracker/releases/download/v1.12.1/firecracker-v1.12.1-x86_64.tgz

tar xfvz firecracker-v1.12.1-x86_64.tgz

cp release-v1.12.1-x86_64/firecracker-v1.12.1-x86_64 /usr/sbin/firecracker

cp release-v1.12.1-x86_64/jailer-v1.12.1-x86_64 /usr/sbin/jailer

rm -rf release-v1.12.1-x86_64 firecracker-v1.12.1-x86_64.tgz
```

### 2. Create `tap` device on host and apply IP config
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

### 3. Download kernelimage
(see [getting-a-rootfs-and-guest-kernel-image](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#getting-a-rootfs-and-guest-kernel-image ) for latest version)
```bash
cd /root
wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.12/x86_64/vmlinux-6.1.128
```

### 4. Create RootFS
(see [getting-a-rootfs-and-guest-kernel-image](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#getting-a-rootfs-and-guest-kernel-image ) for latest version)
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

### 5. Create a config file for the vm called
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
*Note: There is a script called `fcnet-setup.sh` preconfigured in the Ubuntu Image that will calculate and setup the vm's internal IP based on the configuered MAC address. If you build custom images you need to mimic this behavoir or you can inject metadata into a vm using [mmds](https://github.com/firecracker-microvm/firecracker/blob/main/docs/mmds/mmds-user-guide.md).*

### 6. Finally start the VM
```
firecracker --api-sock /tmp/vm1.sock --config-file vm1.conf.json
```

### 7. In an new terminal window try to connect via ssh
```
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
*Note: Default routes and nameservers will be empty after every reboot.*

## Start using fircracker_vm_manager.py
Congrats! Now you're ready to head Head over to [firecracker_vm_manager.md](firecracker_vm_manager.md) and have FCM do all the heavy lifting for you.

## Advanced Topics
* [Build Custom Kernel](Build_custom_kernel.md)
* [Build Custom rootFS (Images)](Build_custom_rootfs.md)
