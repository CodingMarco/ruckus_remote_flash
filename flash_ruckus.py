import time
import logging
import argparse
import paramiko
import tempfile
import threading
import http_server
from custom_logging import CustomFormatter
from pathlib import Path

PROMPT_BUSYBOX_ROOT = "# "
FIRMWARE_PARTITION_OFFSET = 0x40000
WHOLE_FLASH_DEVICE = "/dev/mtd0"


class RuckusFlasher:
    def __init__(self, ip, host_ip, http_port, username, password, firmware):
        self.ap_ip = ip
        self.host_ip = host_ip
        self.http_port = http_port
        self.username = username
        self.password = password
        self.firmware = Path(firmware)
        self.client = None
        self.shell = None
        self.logger = self.setup_logging()
        self.server_thread = None

    def setup_logging(self):
        logger = logging.getLogger("flash_ruckus")
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(CustomFormatter())
        logger.addHandler(ch)
        return logger

    def connect(self):
        """Establish the SSH connection and obtain a BusyBox root shell."""
        self.logger.info(f"Connecting to {self.ap_ip} as {self.username}...")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            self.ap_ip,
            username=self.username,
            password=self.password,
            allow_agent=False,
            look_for_keys=False,
        )
        self.shell = self.client.invoke_shell()
        self.logger.info("SSH connection established.")

    def acquire_root_shell(self):
        self.respond_to_prompt("Please login: ", f"{self.username}\n")
        self.respond_to_prompt("password : ", f"{self.password}\n")

        self.respond_to_prompt("rkscli: ", "Ruckus\n")
        self.shell.send('";/bin/sh;"\n')

        self.respond_to_prompt("rkscli: ", "!v54!\n")
        self.respond_to_prompt("What's your chow: ", "\n")
        self.wait_for_prompt(PROMPT_BUSYBOX_ROOT)
        self.logger.info("BusyBox root shell acquired.")

    def disconnect(self):
        """Close the shell and SSH connection."""
        if self.shell:
            self.shell.close()
        if self.client:
            self.client.close()
        self.logger.info("Disconnected from AP.")

    def read_shell(self):
        """Read data from the SSH shell."""
        while not self.shell.recv_ready():
            time.sleep(0.1)
        return self.shell.recv(4096).decode()

    def wait_for_prompt(self, prompt):
        """Wait until the given prompt appears in the shell output."""
        buffer = ""
        while True:
            output = self.read_shell()
            self.logger.debug(output)
            buffer += output
            if prompt in output:
                break
        return buffer

    def respond_to_prompt(self, prompt, response):
        """Wait for a prompt and then send the given response."""
        self.wait_for_prompt(prompt)
        self.shell.send(response)

    def send_command_wait(self, command):
        """Send a command and wait for the BusyBox root prompt."""
        if not command.endswith("\n"):
            command += "\n"
        self.shell.send(command)
        output = self.wait_for_prompt(PROMPT_BUSYBOX_ROOT)
        # Clean up the output: remove carriage returns, echoed command, and the prompt
        cleaned_output = (
            output.replace("\r\n", "\n")
            .replace(PROMPT_BUSYBOX_ROOT, "")
            .replace(command, "")
            .strip()
        )
        return cleaned_output

    def is_mnt_mounted(self):
        """
        Check if /mnt is already mounted by reading /proc/mounts.
        Returns True if mounted, False otherwise.
        """
        mounts_output = self.send_command_wait("cat /proc/mounts")
        self.logger.debug("Output of /proc/mounts:\n" + mounts_output)
        for line in mounts_output.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "/mnt":
                return True
        return False

    def mount_tmpfs_if_needed(self):
        """
        Mount a tmpfs partition to /mnt if it is not already mounted.
        """
        if self.is_mnt_mounted():
            self.logger.info("/mnt is already mounted. Skipping tmpfs mount.")
            return
        self.logger.info("Mounting tmpfs partition to /mnt.")
        mount_output = self.send_command_wait("mount -t tmpfs tmpfs /mnt")
        self.logger.debug("Output from mount command:\n" + mount_output)

    def copy_files_to_ap(self):
        script_dir = Path(__file__).resolve().parent
        fwprintenv_path = script_dir / "fw_printenv"

        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy the firmware file to the temporary directory
            firmware_path = Path(temp_dir) / self.firmware.name
            firmware_path.write_bytes(self.firmware.read_bytes())
            # Copy the fw_printenv script to the temporary directory
            fwprintenv_path_temp = Path(temp_dir) / "fw_printenv"
            fwprintenv_path_temp.write_bytes(fwprintenv_path.read_bytes())

            self.server_thread = threading.Thread(
                target=lambda: http_server.run(temp_dir, self.http_port), daemon=True
            )
            self.server_thread.start()
            httpd = http_server.server_queue.get()

            self.logger.info(f"Serving files from {temp_dir} on port {self.http_port}.")
            self.logger.info("Copying files to AP...")

            self.send_command_wait(
                f"wget http://{self.host_ip}:{self.http_port}/{self.firmware.name} -O /mnt/{self.firmware.name}"
            )
            self.send_command_wait(
                f"wget http://{self.host_ip}:{self.http_port}/fw_printenv -O /mnt/fw_printenv"
            )
            self.send_command_wait("chmod +x /mnt/fw_printenv")

            # The fw_printenv binary can also write u-boot environment variables
            # if the binary is named fw_setenv. So we create a symlink to it.
            self.send_command_wait("ln -s /mnt/fw_printenv /mnt/fw_setenv")

            self.logger.info("Files copied to AP successfully.")
            self.logger.info("Stopping HTTP server.")

            httpd.server_close()
            self.logger.info("HTTP server stopped.")

    def erase_firmware_partition(self):
        self.logger.info("Erasing firmware partition...")
        firmware_size = self.firmware.stat().st_size
        self.send_command_wait(
            " ".join(
                [
                    "mtd_debug",
                    "erase",
                    WHOLE_FLASH_DEVICE,
                    str(FIRMWARE_PARTITION_OFFSET),
                    str(firmware_size),
                ]
            )
        )
        self.logger.info("Firmware partition erased.")

    def flash_firmware(self):
        self.logger.info("Flashing firmware...")
        firmware_size = self.firmware.stat().st_size
        self.send_command_wait(
            " ".join(
                [
                    "mtd_debug",
                    "write",
                    WHOLE_FLASH_DEVICE,
                    str(FIRMWARE_PARTITION_OFFSET),
                    str(firmware_size),
                    "/mnt/" + self.firmware.name,
                ]
            )
        )
        self.send_command_wait("sync")
        self.logger.info("Firmware flashed successfully.")

    def set_openwrt_bootaddr(self):
        self.logger.info("Setting OpenWRT boot address...")
        # Address construction:
        # Memory-mapped flash offset = 0xbf000000
        # Firmware partition offset = 0x40000
        self.send_command_wait('fw_setenv bootcmd "bootm 0xbf040000"')
        self.logger.info("OpenWRT boot address set.")

    def run(self):
        """
        Execute the sequence:
         1. Connect and acquire a root shell.
         2. Mount tmpfs on /mnt if needed.
         3. (Additional steps can be added here.)
        """
        try:
            self.connect()
            self.acquire_root_shell()
            self.mount_tmpfs_if_needed()
            self.copy_files_to_ap()
            self.erase_firmware_partition()
            self.set_openwrt_bootaddr()
            self.flash_firmware()
            self.logger.info("Firmware flashing completed successfully.")
        except Exception as e:
            self.logger.error(f"An error occurred: {e}")
            self.logger.debug("Traceback:", exc_info=True)
        finally:
            self.disconnect()


def parse_args():
    parser = argparse.ArgumentParser(description="Flash Ruckus AP")
    parser.add_argument(
        "--ip", type=str, default="192.168.0.1", help="IP Address of the AP"
    )
    parser.add_argument(
        "--host-ip",
        type=str,
        default="192.168.0.10",
        help="(static) IP Address of the host",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=8000,
        help="Port for the HTTP server to serve files",
    )
    parser.add_argument(
        "--username", type=str, default="super", help="Username of the AP"
    )
    parser.add_argument(
        "--password", type=str, default="sp-admin", help="Password of the AP"
    )
    parser.add_argument(
        "--firmware",
        type=str,
        default="openwrt-sysupgrade.bin",
        help="Firmware file to flash",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    flasher = RuckusFlasher(
        args.ip,
        args.host_ip,
        args.http_port,
        args.username,
        args.password,
        args.firmware,
    )
    flasher.run()
