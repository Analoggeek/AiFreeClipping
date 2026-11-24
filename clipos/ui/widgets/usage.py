"""Non-blocking live system/app usage; unsupported GPU counters are explicit."""
import os
import shutil
import subprocess
import threading
from PySide6.QtCore import QThread, Signal


class UsageWorker(QThread):
    sample = Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent);self.stop_event=threading.Event()

    def run(self):
        try:import psutil
        except ImportError:
            self.sample.emit('Live usage unavailable (psutil missing)');return
        process=psutil.Process(os.getpid());tracked={};tick=0;gpu='GPU counters unavailable'
        while not self.stop_event.wait(1):
            try:
                cpu=psutil.cpu_percent(interval=None);ram=psutil.virtual_memory()
                procs=[process]+process.children(recursive=True);rss=0;appcpu=0
                for proc in procs:
                    try:
                        current=tracked.setdefault(proc.pid,proc);rss+=current.memory_info().rss;appcpu+=current.cpu_percent(None)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                tracked={p.pid:tracked[p.pid] for p in procs if p.pid in tracked}
                if tick%5==0 and shutil.which('nvidia-smi'):
                    try:
                        result=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        if result.returncode==0:gpu='GPU '+', '.join(x+'%' for x in result.stdout.split())
                    except (OSError,subprocess.TimeoutExpired):pass
                self.sample.emit(f'CPU {cpu:.0f}% · RAM {ram.percent:.0f}% · CLIPOS + tools {appcpu/max(1,psutil.cpu_count() or 1):.0f}% CPU / {rss/2**30:.2f} GB · {gpu}')
                tick+=1
            except (psutil.Error,OSError):pass
