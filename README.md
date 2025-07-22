# Firecracker Cheat Sheet

## What is Firecracker?

Firecracker is an open source virtualization technology that is purpose-built for creating and managing secure, multi-tenant container and function-based services that provide serverless operational models. Firecracker runs workloads in lightweight virtual machines, called microVMs, which combine the security and isolation properties provided by hardware virtualization technology with the speed and flexibility of containers.

Web: https://firecracker-microvm.github.io

Code: https://github.com/firecracker-microvm/firecracker/

Docs: https://github.com/firecracker-microvm/firecracker/tree/main/docs

Copy & Paste Getting Started Guide: https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md

## Core Concepts
* Each **process instance** of the firecracker binary represents a vm
* Each process has a dedicated api for this vm, listening on a socket (i.e. */tmp/vm1.sock*)
* Starting the process **does not start the vm**, only the api
* The running process is then configured with boot image, rootFS, network device, cpu & emory quotas etc. via `curl --unix-socket /tmp/vm1.sock ...`
* The api endpoint `InstanceStart` boots the vm
* `reboot` inside the vm shuts it down and exits the firecracker process
* The socket file must be removed by hand
* To immedieatly boot the vm when starting the process use `firecracker --config-file`

## Networking
* Create a dedicated `tap` interface on the host for each vm
* Apply firewall / routing / MASQUERADE rules to this interface
* Start a vm that attaches to this interface
* After **each** boot the guest network interface inside the vm does not have any routing info and no nameserver in `/etc/resolv.conf`

## Start the first VM 🚀
1. Download the binary (see [releases](https://github.com/firecracker-microvm/firecracker/releases) for latest version):
    ```
    wget https://github.com/firecracker-microvm/firecracker/releases/download/v1.12.1/firecracker-v1.12.1-x86_64.tgz
    ```

2. Create `tap` device on host and apply IP config. Run the following as ``root``:
    ```
    ip tuntap add dev tap0 mode tap
    ip addr add 172.16.0.1/30 dev tap0
    ip link set dev tap0 up

    # enable forwarding on host system
    echo 1 > /proc/sys/net/ipv4/ip_forward
    # set up internet access
    sudo iptables -t nat -D POSTROUTING -o <YOUR_EXTERNAL_HOST_IFACE> -j MASQUERADE || true
    sudo iptables -t nat -A POSTROUTING -o <YOUR_EXTERNAL_HOST_IFACE> -j MASQUERADE
    ```
3. Download kernelimage (see [getting-a-rootfs-and-guest-kernel-image](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#getting-a-rootfs-and-guest-kernel-image ) for latest version):
    ```
    cd /root
    wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.12/x86_64/vmlinux-6.1.128
    ```
 
4. Create RootFS (see [getting-a-rootfs-and-guest-kernel-image](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#getting-a-rootfs-and-guest-kernel-image ) for version):
    ```
    cd /root
    # Download & uncompress Ubuntu
    wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.12/x86_64/ubuntu-24.04.squashfs
    
    unsquashfs ubuntu-24.04.squashfs
    # you can make changes to the filesstem in 
    # squashfs-root folder. for example add
    # your ssh key to ./squashfs-root/root/.ssh/authorized_keys

    # Create empty image file for vm
    truncate -s 1g ubuntu-vm1.ext4
    
    # Copy rootfs to image
    mkfs.ext4 -d squashfs-root -F ubuntu-vm1.ext4

    ```
5. Create a config file for the vm called `/root/vm1.conf.json`
    ```
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
6. Finally start the VM
    ```
    firecracker --api-sock /tmp/vm1.sock --config-file vm1.conf.json
    ```
7. In an new terminal window try to connect via ssh
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
    **Remember:** Default route and nameserver will be empty after every reboot!

## Building a new kernel
The official [repo](https://github.com/firecracker-microvm/firecracker/tree/main/resources) contains helper scripts and other ressources.
```
git clone https://github.com/firecracker-microvm/firecracker/

cd firecracker/resources

vi guest_configs/microvm-kernel-ci-x86_64-6.1.config

#for ARM: vi guest_configs/microvm-kernel-ci-aarch64-6.1.config

./rebuild.sh kernels 6.1
```
See `./rebuild.sh help` for more options.