# system_stats.py
"""Report live system metrics: CPU, RAM, battery, disk.

Cross-platform via psutil. Returns a short spoken-friendly summary so the
assistant can answer "how's my CPU", "what's my battery", "disk space", etc.
"""
import shutil
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


def _fmt_gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 ** 3):.1f} GB"


def _cpu() -> str:
    pct = psutil.cpu_percent(interval=0.5)
    cores = psutil.cpu_count(logical=True)
    return f"CPU is at {pct:.0f}% across {cores} cores."


def _memory() -> str:
    vm = psutil.virtual_memory()
    return (f"Memory at {vm.percent:.0f}% — "
            f"{_fmt_gb(vm.used)} used of {_fmt_gb(vm.total)}.")


def _battery() -> str:
    batt = getattr(psutil, "sensors_battery", lambda: None)()
    if batt is None:
        return "No battery detected (this looks like a desktop or VM)."
    state = "charging" if batt.power_plugged else "on battery"
    extra = ""
    if not batt.power_plugged and batt.secsleft and batt.secsleft > 0:
        extra = f", about {batt.secsleft // 3600}h {(batt.secsleft % 3600) // 60}m left"
    return f"Battery at {batt.percent:.0f}% ({state}{extra})."


def _disk() -> str:
    usage = shutil.disk_usage(str(Path.home()))
    pct = usage.used / usage.total * 100
    return (f"Disk at {pct:.0f}% — "
            f"{_fmt_gb(usage.free)} free of {_fmt_gb(usage.total)}.")


def system_stats(parameters: dict = None, response=None, player=None,
                 session_memory=None) -> str:
    if not _PSUTIL:
        return "psutil is not installed — cannot read system stats."

    params = parameters or {}
    metric = str(params.get("metric", "all")).lower().strip()

    builders = {
        "cpu": _cpu,
        "memory": _memory,
        "ram": _memory,
        "battery": _battery,
        "disk": _disk,
        "storage": _disk,
    }

    try:
        if metric in builders:
            result = builders[metric]()
        else:  # "all" or anything unrecognised → full summary
            result = " ".join([_cpu(), _memory(), _battery(), _disk()])
    except Exception as e:
        result = f"Could not read system stats: {e}"

    print(f"[SystemStats] {result}")
    if player:
        player.write_log(f"[stats] {metric}")
    return result
