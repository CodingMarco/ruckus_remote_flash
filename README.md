# Remotely flashing OpenWrt over Ruckus stock FW

## Currently supported models
- Ruckus ZF7363

## High-level overview
1. Open an SSH connection to the Ruckus AP
2. Open a busybox root shell using the hidden `!v54!` command
3. Mount a tmpfs partition to `/mnt` (that is not size-limited like the one mounted by default at `/tmp`)
4. Download the OpenWrt image and the statically compiled `fw_setenv` binary to `/mnt` using (legacy) scp
5. Erase the firmware partition using `mtd_debug erase`
6. Flash the OpenWrt image using `mtd_debug write`
7. Set the u-boot environment variable `bootcmd` to `bootm 0xbf040000` using `fw_setenv` so that OpenWrt is booted
8. Reboot the device
