# Building a custom kernel
You need to build a custom kernel if you want to:
* have the latest kernel minor version
* add kernel modules like i.e. `nf_tables` that is used by docker

## Clone Firecracker Repository

The official [repo](https://github.com/firecracker-microvm/firecracker/tree/main/resources) contains helper scripts and other ressources.
```bash
git clone https://github.com/firecracker-microvm/firecracker/

cd firecracker/resources

vi guest_configs/microvm-kernel-ci-x86_64-6.1.config

#for ARM: vi guest_configs/microvm-kernel-ci-aarch64-6.1.config

./rebuild.sh kernels 6.1
```
*See `./rebuild.sh help` for more options.*

**Note**: This script will check and install dependencies on the system, like for example docker. However it will try to install Ubuntu's `docker.io`, when you already have Docker running on the host, change the the `apt install`-line to use `docker-ce` instead.


# Sample kernel config for nft support

If you want to runner Docker inside a Firecracker microVM, you'll need a kernel with `nft` support. Here's what you need to add to `microvm-kernel-ci-x86_64-6.1.config` to achieve this:

```ini
CONFIG_NF_TABLES=y
CONFIG_NFT_NUMGEN=y
CONFIG_NFT_CT=y
CONFIG_NFT_FLOW_OFFLOAD=y
CONFIG_NFT_CONNLIMIT=y
CONFIG_NFT_LOG=y
CONFIG_NFT_LIMIT=y
CONFIG_NFT_MASQ=y
CONFIG_NFT_REDIR=y
CONFIG_NFT_NAT=y
CONFIG_NFT_TUNNEL=y
CONFIG_NFT_QUEUE=y
CONFIG_NFT_QUOTA=y
CONFIG_NFT_REJECT=y
CONFIG_NFT_REJECT_INET=y
CONFIG_NFT_COMPAT=y
CONFIG_NFT_HASH=y
CONFIG_NFT_FIB=y
CONFIG_NFT_FIB_INET=y
CONFIG_NFT_XFRM=y
CONFIG_NFT_SOCKET=y
CONFIG_NFT_OSF=y
CONFIG_NFT_TPROXY=y
CONFIG_NFT_SYNPROXY=y
CONFIG_NFT_DUP_NETDEV=y
CONFIG_NFT_FWD_NETDEV=y
CONFIG_NFT_FIB_NETDEV=y
CONFIG_NFT_REJECT_NETDEV=y
CONFIG_NFT_REJECT_IPV4=y
CONFIG_NFT_DUP_IPV4=y
CONFIG_NFT_FIB_IPV4=y
CONFIG_NFT_REJECT_IPV6=y
CONFIG_NFT_DUP_IPV6=y
CONFIG_NFT_FIB_IPV6=y
CONFIG_NFT_BRIDGE_META=y
CONFIG_NFT_BRIDGE_REJECT=y
```
