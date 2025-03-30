import time
import logging
import argparse
import paramiko
from custom_logging import CustomFormatter

PROMPT_BUSYBOX_ROOT = "# "


class RuckusFlasher:
    def __init__(self, ip, username, password, firmware):
        self.ip = ip
        self.username = username
        self.password = password
        self.firmware = firmware
        self.client = None
        self.shell = None
        self.logger = self.setup_logging()

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
        self.logger.info(f"Connecting to {self.ip} as {self.username}...")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            self.ip,
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
        finally:
            self.disconnect()


def parse_args():
    parser = argparse.ArgumentParser(description="Flash Ruckus AP")
    parser.add_argument(
        "--ip", type=str, default="192.168.0.1", help="IP Address of the AP"
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
    flasher = RuckusFlasher(args.ip, args.username, args.password, args.firmware)
    flasher.run()
