# Remotely flashing OpenWrt over Ruckus stock FW

## Currently supported models
- Ruckus ZF7363

## High-level overview
1. Open an SSH connection to the Ruckus AP
2. Open a busybox root shell using the hidden `!v54!` command
3. Mount a tmpfs partition to `/mnt` (that is not size-limited like the one mounted by default at `/tmp`)
4. Download the OpenWrt image and the statically compiled `fw_printenv` binary to `/mnt` using (legacy) scp
5. Link the `fw_printenv` binary to `fw_setenv` so that the u-boot environment can be modified
6. Erase the firmware partition using `mtd_debug erase`
7. Flash the OpenWrt image using `mtd_debug write`
8. Set the u-boot environment variable `bootcmd` to `bootm 0xbf040000` using `fw_setenv` so that OpenWrt is booted
9. Reboot the device
