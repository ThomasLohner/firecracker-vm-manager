# Building a custom rootFS (image)
You need stuff preinstalled in your VMs? No prolemo, here's an example based on Alpine Linux. We will be using a Docker container to install everything we need and make changes to the files. Then pack everything up into a image file.

## Create empty image file
We will create an empty image file with 1 GB of diskspace. Adjust the size if you need more. Dont' worry too much about wasting diskspace, we will schrink the image later, so we don't watse any diskspace.
```bash
truncate -s 1g alpine.template.ext4

mkfs.ext4 alpine.template.ext4
```

## Start docker container
```bash
mount alpine.template.ext4 /tmp/alpine-rootfs/

docker run --rm -ti -v /tmp/alpine-rootfs/:/my-rootfs alpine:latest
```

## Install packages in Container
Run this insode the container you startet in the prvious step:
```bash
apk add --no-cache openrc util-linux nano curl docker openssh

# Set up a login terminal on the serial console (ttyS0):
ln -s agetty /etc/init.d/agetty.ttyS0
echo ttyS0 > /etc/securetty

# Add everything to boot runlevel
rc-update add agetty.ttyS0 default
rc-update add devfs boot
rc-update add procfs boot
rc-update add sysfs boot
rc-update add sshd boot
rc-update add docker boot

# Then, copy the newly configured system to the rootfs image:
for d in bin etc lib root sbin usr; do tar c "/$d" | tar x -C /my-rootfs; done

# The above command may trigger the following message:
# tar: Removing leading "/" from member names
# However, this is just a warning, so you should be able to
# proceed with the setup process.

for dir in dev proc run sys var; do mkdir /my-rootfs/${dir}; done

# Set a root password or 
# passwd

# Or add your ssh-key to the image
# mkdir /root/.ssh/ && echo "xxx" > /root/.ssh/authorized_keys
```

## Cleanup
We need to unmount the image file and then shrink it to the minimum size
```bash
umount /tmp/alpine-rootfs

# Shrink image to minimal size
e2fsck -f alpine.template.ext4
resize2fs -M alpine.template.ext4
gzip alpine.template.ext4
```

TODO:
``` 
error while staring vm
* Starting networking ...ifquery: could not parse /etc/network/interfaces

NEW:
```
#syntax=docker/dockerfile:1.4

FROM alpine:latest

# Network and ssh setup
COPY <<-'EOF' /usr/local/bin/fcnet_start.sh
	#!/bin/sh

	# Set up mmds interface so we can get metadata
	ip link set dev eth1 name mmds
	ip link set mmds up
	ip route add 169.254.169.254 dev mmds

	# Add a small delay to ensure the interface is ready
	sleep 0.2

	# Fetch network config with error checking
	IP=$(curl -s --max-time 10 http://169.254.169.254/network_config/ip)
	GATEWAY=$(curl -s --max-time 10 http://169.254.169.254/network_config/gateway)

	# Debug: log the values (you can check these in system logs)
	echo "Retrieved IP: '$IP'" >&2
	echo "Retrieved Gateway: '$GATEWAY'" >&2

	# Check if values were retrieved successfully
	if [ -z "$IP" ] || [ -z "$GATEWAY" ]; then
	echo "Failed to retrieve network configuration" >&2
	exit 1
	fi

	# Apply network configuration
	ip addr add "$IP" dev eth0
	ip link set eth0 up
	ip route add "$GATEWAY" dev eth0
	ip route add default via "$GATEWAY" dev eth0
EOF
COPY <<-'EOF' /etc/init.d/fcnet
	#!/usr/sbin/openrc-run

	description="Firecracker net service"
	command="/usr/local/bin/fcnet_start.sh"
	pidfile="/run/$RC_SVCNAME.pid"

	depend() {
	    provide net
	}

	start() {
	    ebegin "Starting fcnet"
	    $command
	    eend $?
	}

	stop() {
	    ebegin "Stopping fcnet"
	    eend 0
	}
EOF

RUN <<-EOF
	# unlock root for ssh login
	passwd -u root
	chmod 0755 /usr/local/bin/*.sh /etc/init.d/fcnet
	apk add --no-cache openrc util-linux nano curl docker openssh
	# Set up a login terminal on the serial console (ttyS0):
	ln -s agetty /etc/init.d/agetty.ttyS0
	echo ttyS0 > /etc/securetty

	# Add everything to boot runlevel
	rc-update add fcnet boot
	rc-update add agetty.ttyS0 default
	rc-update add devfs boot
	rc-update add procfs boot
	rc-update add sysfs boot
	rc-update add sshd boot
	rc-update add docker boot
        mkdir /root/.ssh/authorized_keys
	echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG3P/pMsjM3CsgwKhZRxRskaKC1s8g3Ypt6LR3fuSl0o root@firecracker-srv1.scalecommerce.dev" > /root/.ssh
EOF
```
docker build --no-cache --output type=tar,dest=rootfs.tar .
mkdir rootfs && tar -C rootfs -xf rootfs.tar
truncate -s 1G alpine-v1.0.ext4

