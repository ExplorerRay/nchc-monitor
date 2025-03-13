import requests
import subprocess
import yaml
import time
from datetime import datetime
import os

MATTERMOST_WEBHOOK_URL = ""

RECORD_FILE = "/home/rayhuang111/monitor_record.yaml"
LOG_FILE = "/home/rayhuang111/monitor.log"

ALERT_COOLDOWN = 3600  # 1 hour in seconds

class BaseMonitor:
    # init monitor, set and create record file and log file
    def __init__(self, job_name):
        self.record_file = RECORD_FILE
        self.log_file = LOG_FILE
        self.job_name = job_name
        # if log file not exists, create it
        if not os.path.exists(LOG_FILE):
            open(LOG_FILE, "a").close()
        # if record file not exists, create it
        if not os.path.exists(RECORD_FILE):
            open(RECORD_FILE, "a").close()

    # log message for debugging this monitor.py
    def log(self, message):
        """Logs the message to a log file."""
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now()}] {message}\n")

    # call webhook to send notification to mattermost
    def send_notification(self, webhookMsg, webhookEmoji):
        """Sends a notification to mattermost."""
        webhookUsername="cron-Monitor"
        webhookColor = "#FF0000" if webhookEmoji=="🔥" else "#4DFF4D"
        self.log(f"Sending notification: {webhookMsg}")
        try:
            payload = {
                "username": webhookUsername,
                "attachments": [
                    {
                        "title": webhookEmoji + webhookMsg,
                        "color": webhookColor,
                    }
                ],
            }
            response = requests.post(MATTERMOST_WEBHOOK_URL, json=payload)
            if response.status_code == 200:
                self.log(f"Notification sent successfully: {webhookMsg}")
            else:
                self.log(f"Failed to send notification: {response.status_code}")
        except Exception as e:
            self.log(f"Error while sending notification: {e}")

    def send_alert(self, message):
        """Sends an alert to mattermost."""
        self.send_notification(f"Alert: {message}", "🔥")

    def send_recover(self, message):
        """Sends a recover notification to mattermost."""
        self.send_notification(f"Recovered: {message}", "✅")

    # 因為 cronjob 不會有上次執行的狀態，所以將狀態寫入 yaml 檔案 (record) 中
    # 用此方法處理 alert cooldown、fail threshold、recovery 等機制
    def load_record(self):
        """Loads monitoring records from YAML."""
        if os.path.exists(self.record_file):
            with open(self.record_file, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def save_record(self, data):
        """Saves monitoring records to YAML."""
        with open(self.record_file, "w") as f:
            yaml.dump(data, f)

    def check_recovery(self, func_name, threshold):
        """Checks if the service has recovered from failure."""
        data = self.load_record()
        key = f"{self.job_name}.{func_name}"
        if data.get(key, {}).get("fail_count", 0) > 0:
            self.log(f"Service recovery detected: {key}")
            if data[key]["fail_count"] >= threshold:
                self.send_recover(f"{key} has recovered.")
            data[key]["fail_count"] = 0  # Reset failure count
            data[key]["last_alert"] = 0  # Reset alert cooldown
            self.save_record(data)

    def check_alert_cooldown(self, func_name):
        """Ensures alerts are sent at least 1 hour apart per function."""
        data = self.load_record()
        key = f"{self.job_name}.{func_name}"
        last_alert_time = data.get(key, {}).get("last_alert", 0)
        return (time.time() - last_alert_time) > ALERT_COOLDOWN

    def update_alert_time(self, func_name):
        """Updates the last alert timestamp."""
        data = self.load_record()
        key = f"{self.job_name}.{func_name}"
        data.setdefault(key, {})["last_alert"] = time.time()
        self.save_record(data)

    def record_failure(self, func_name):
        """Records a failure event in the YAML file."""
        data = self.load_record()
        key = f"{self.job_name}.{func_name}"
        data.setdefault(key, {"fail_count": 0, "last_alert": 0})
        data[key]["fail_count"] += 1
        self.save_record(data)

    def get_failure_count(self, func_name):
        """Returns the failure count of a function."""
        data = self.load_record()
        key = f"{self.job_name}.{func_name}"
        return data.get(key, {}).get("fail_count", 0)

    # 執行 shell command，並檢查 return code
    # command: 要執行的 shell command
    # func_name: 用來記錄錯誤次數的 key
    # fail_threshold: 超過此次數才會發送 alert
    def execute_command(self, command, func_name, fail_threshold=1):
        """Runs shell commands and check return code."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
            self.log(f"Command executed: {command}")
            self.check_recovery(func_name, fail_threshold)
            return result.stdout.strip()
        # if return code is not 0, send alert
        except subprocess.CalledProcessError as e:
            self.log(f"Command failed: {e}")
            self.record_failure(func_name)
            fail_count = self.get_failure_count(func_name)
            if self.check_alert_cooldown(func_name) and fail_count >= fail_threshold:
                self.send_alert(f"Command failed: {e}")
                self.update_alert_time(func_name)
            return None

    # 執行 shell command，並檢查 return code 和執行時間
    # timeout: command 執行時間上限
    def execute_command_with_timeout(self, command, func_name, timeout, fail_threshold=1):
        """Runs shell commands and check return code and execution time."""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True, timeout=timeout)
            self.log(f"Command with timeout executed: {command}")
            self.check_recovery(func_name, fail_threshold)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.log(f"Command failed: {e}")
            self.record_failure(func_name)
            fail_count = self.get_failure_count(func_name)
            if self.check_alert_cooldown(func_name) and fail_count >= fail_threshold:
                self.send_alert(f"Command failed: {e}")
                self.update_alert_time(func_name)
            return None
        except subprocess.TimeoutExpired:
            self.log(f"{command} took longer than {timeout} seconds to execute.")
            self.record_failure(func_name)
            fail_count = self.get_failure_count(func_name)
            if self.check_alert_cooldown(func_name) and fail_count >= fail_threshold:
                self.send_alert(f"Timeout! {command} took longer than {timeout} seconds to execute.")
                self.update_alert_time(func_name)
            return None

class FSMonitor(BaseMonitor):
    def __init__(self):
        super().__init__("FS_Monitor")

    def check_fs_mount_time(self):
        """Checks fs mount situation."""
        cmd = "df -h"
        max_time = 0.25
        self.execute_command_with_timeout(cmd, "check_fs_mount_time", max_time)

    def check_mount_ls_time(self):
        """Checks mount ls situation."""
        mount_points = ["/work1", "/work2", "/project", "/pkg", "/home"]
        max_time = 1
        for mount_point in mount_points:
            cmd = f"ls {mount_point}"
            self.execute_command_with_timeout(cmd, "check_mount_ls_time", max_time)

class SlurmMonitor(BaseMonitor):
    def __init__(self):
        super().__init__("Slurm_Monitor")

    def check_sinfo_time(self):
        """Checks the time to run sinfo."""
        max_time = 1
        return self.execute_command_with_timeout("sinfo", "check_sinfo_time", max_time, 5)

    def check_sacct_time(self):
        """Checks the time to run sacct."""
        max_time = 1
        return self.execute_command_with_timeout("sacct", "check_sacct_time", max_time, 3)

    def check_slurmctld_status(self):
        """Checks the status of slurmctld."""
        ctld_hosts = ["isn01", "isn09"]
        for host in ctld_hosts:
            cmd = f"nc -z {host} 6817"
            self.execute_command(cmd, "check_slurmctld_status")

    def check_slurmdbd_status(self):
        """Checks the status of slurmdbd."""
        dbd_hosts = ["isn01"]
        for host in dbd_hosts:
            cmd = f"nc -z {host} 6819"
            self.execute_command(cmd, "check_slurmdbd_status")

class CPUMonitor(BaseMonitor):
    def __init__(self):
        super().__init__("CPU_Monitor")

    def check_loading(self):
        """Checks the CPU loading."""
        return self.execute_command("uptime", "check_loading")

class MemoryMonitor(BaseMonitor):
    def __init__(self):
        super().__init__("Memory_Monitor")

    def check_memory_usage(self):
        """Checks the memory usage."""
        return self.execute_command("free", "check_memory_usage")


if __name__ == "__main__":
    # ml tools/miniconda3
    # conda activate monit
    FSM = FSMonitor()
    FSM.check_fs_mount_time()
    FSM.check_mount_ls_time()

    SM = SlurmMonitor()
    SM.check_sinfo_time()
    SM.check_slurmctld_status()
    SM.check_sacct_time()
    SM.check_slurmdbd_status()
