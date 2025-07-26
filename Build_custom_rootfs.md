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