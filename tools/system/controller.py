"""tools/system/controller.py — Full system control."""
import os, sys, datetime, subprocess
from config.settings import USER_NAME
from config.logger import get_logger

log = get_logger("system")
IS_WIN = sys.platform == "win32"


class SystemController:

    def volume_up(self) -> str:
        self._volume_change(+0.1)
        return f"Volume increased, {USER_NAME}."

    def volume_down(self) -> str:
        self._volume_change(-0.1)
        return f"Volume decreased, {USER_NAME}."

    def _volume_change(self, delta: float):
        if IS_WIN:
            try:
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                dev = AudioUtilities.GetSpeakers()
                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = cast(iface, POINTER(IAudioEndpointVolume))
                cur = vol.GetMasterVolumeLevelScalar()
                vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, cur + delta)), None)
            except Exception:
                import pyautogui
                for _ in range(5):
                    pyautogui.press("volumeup" if delta > 0 else "volumedown")
        else:
            amt = "10%+" if delta > 0 else "10%-"
            os.system(f"amixer -D pulse sset Master {amt}")

    def mute(self) -> str:
        try:
            if IS_WIN:
                import pyautogui; pyautogui.press("volumemute")
            else:
                os.system("amixer -D pulse sset Master toggle")
        except Exception:
            pass
        return f"Audio toggled, {USER_NAME}."

    def screenshot(self) -> str:
        try:
            import pyautogui
            from pathlib import Path
            folder = Path.home() / "Pictures" / "Jarvis"
            folder.mkdir(parents=True, exist_ok=True)
            fname = folder / f"shot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot().save(str(fname))
            return f"Screenshot saved to {fname}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    def battery_status(self) -> str:
        try:
            import psutil
            b = psutil.sensors_battery()
            if b is None:
                return f"Desktop system - no battery, {USER_NAME}."
            status = "charging" if b.power_plugged else "discharging"
            return f"Battery: {b.percent:.0f}% - {status}"
        except Exception as e:
            return f"Battery check failed: {e}"

    def wifi_status(self) -> str:
        try:
            import psutil
            for name, stat in psutil.net_if_stats().items():
                if stat.isup and name.lower() not in ("lo", "loopback"):
                    addrs = psutil.net_if_addrs().get(name, [])
                    ip = next((a.address for a in addrs if a.family == 2), "N/A")
                    return f"Connected via {name} - IP: {ip}"
            return f"No active network found, {USER_NAME}."
        except Exception as e:
            return f"Network check failed: {e}"

    def cpu_usage(self) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            cores = psutil.cpu_count()
            freq = psutil.cpu_freq()
            freq_str = f" at {freq.current:.0f} MHz" if freq else ""
            return f"CPU: {cpu}% usage across {cores} cores{freq_str}"
        except Exception as e:
            return f"CPU check failed: {e}"

    def ram_usage(self) -> str:
        try:
            import psutil
            vm = psutil.virtual_memory()
            used_gb = vm.used / 1e9
            total_gb = vm.total / 1e9
            return f"RAM: {vm.percent}% used ({used_gb:.1f} GB / {total_gb:.1f} GB)"
        except Exception as e:
            return f"RAM check failed: {e}"

    def list_processes(self) -> str:
        try:
            import psutil
            procs = sorted(psutil.process_iter(['name', 'cpu_percent', 'memory_percent']),
                           key=lambda p: p.info.get('cpu_percent', 0), reverse=True)
            top = procs[:8]
            lines = [f"{p.info['name'][:20]:<22} CPU:{p.info.get('cpu_percent',0):.1f}%  MEM:{p.info.get('memory_percent',0):.1f}%"
                     for p in top if p.info.get('name')]
            return "Top processes:\n" + "\n".join(lines)
        except Exception as e:
            return f"Process list failed: {e}"

    def kill_process(self, name: str) -> str:
        try:
            import psutil
            killed = []
            for proc in psutil.process_iter(['name', 'pid']):
                if name.lower() in proc.info.get('name', '').lower():
                    proc.kill()
                    killed.append(proc.info['name'])
            if killed:
                return f"Killed: {', '.join(killed)}, {USER_NAME}."
            return f"No process matching '{name}' found, {USER_NAME}."
        except Exception as e:
            return f"Kill failed: {e}"

    def lock_screen(self) -> str:
        if IS_WIN: os.system("rundll32.exe user32.dll,LockWorkStation")
        else: os.system("gnome-screensaver-command -l")
        return f"Screen locked, {USER_NAME}."

    def shutdown(self) -> str:
        if IS_WIN: os.system("shutdown /s /t 5")
        else: os.system("shutdown -h +1")
        return f"Shutting down in 5 seconds, {USER_NAME}."

    def restart(self) -> str:
        if IS_WIN: os.system("shutdown /r /t 5")
        else: os.system("reboot")
        return f"Restarting in 5 seconds, {USER_NAME}."

    def get_time(self) -> str:
        return f"It's {datetime.datetime.now().strftime('%I:%M %p')}, {USER_NAME}."

    def get_date(self) -> str:
        return f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}."

    def system_info(self) -> str:
        try:
            import psutil, platform
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            return (
                f"System: {platform.node()} | {platform.system()} {platform.release()}\n"
                f"CPU: {cpu}%  RAM: {ram.percent}%  Disk: {disk.percent}%"
            )
        except Exception as e:
            return f"System info failed: {e}"
