import threading
import subprocess
import os
import signal
import platform

try:
    import queue
except ImportError:
    import Queue as queue

class LogcatOutputThread(threading.Thread):
    def __init__(self, serialno):
        super(LogcatOutputThread, self).__init__()
        self.serialno = serialno
        self.daemon = True
        self.msg_q = queue.Queue()
        self.listeners = {}
        self.stoprequest = threading.Event()
        self.proc = None

    def register_event(self, logcat_event):
        self.listeners[logcat_event.pattern] = logcat_event

    def unregister_event(self, logcat_event):
        if logcat_event.pattern in self.listeners.keys():
            del self.listeners[logcat_event.pattern]

    def join(self, timeout=None):
        self.stoprequest.set()
        super(LogcatOutputThread, self).join(timeout)

    def poll(self):
        return self.proc.poll() if self.proc else None

    def run(self):
        if platform.system() == "Linux":
            self.proc = subprocess.Popen(["adb", "-s", self.serialno, "logcat"], stdout=subprocess.PIPE, preexec_fn=os.setsid)
        elif platform.system() == "Windows":
            self.proc = subprocess.Popen(["adb", "-s", self.serialno, "logcat"], stdout=subprocess.PIPE, preexec_fn=None)
        while not self.stoprequest.isSet():
            if self.proc.poll() != None:
                break

            line = self.proc.stdout.readline()
            self._handle_logcat_msg(line)

        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)

    def _handle_logcat_msg(self, msg):
        for pattern in self.listeners.keys():
            if pattern in msg:
                self.listeners[pattern].cb(pattern=pattern, msg=msg)

class LogcatEvent(object):
    def __init__(self, pattern=None, cb=None):
        self.pattern = pattern
        self.cb = cb

class LogcatListener(object):
    WORK_THREADS = {}

    @staticmethod
    def kill_finished_threads():
        while len(LogcatListener.WORK_THREADS.keys()) > 0:
            for serialno, th in LogcatListener.WORK_THREADS.items():
                if th.poll() != None:
                    th.join()
                    if serialno in LogcatListener.WORK_THREADS.keys():
                        del LogcatListener.WORK_THREADS[serialno]

    @staticmethod
    def _find_first_device_serialno():
        out, _ = Adb.execute(cmd="devices")
        return out.splitlines()[1].split("\t")[0] if len(out.splitlines()) > 1 else None

    @staticmethod
    def init(serialno=None):
        if not serialno:
            serialno = LogcatListener._find_first_device_serialno()
        if not serialno:
            return

        if serialno in LogcatListener.WORK_THREADS.keys():
            return

        LogcatListener.WORK_THREADS[serialno] = LogcatOutputThread(serialno)
        LogcatListener.WORK_THREADS[serialno].start()

        if len(LogcatListener.WORK_THREADS.keys()) == 1:
            threading.Thread(target=LogcatListener.kill_finished_threads).start()

    @staticmethod
    def finalize():
        for serialno, th in LogcatListener.WORK_THREADS.items():
            th.join()
            if serialno in LogcatListener.WORK_THREADS.keys():
                del LogcatListener.WORK_THREADS[serialno]

    @staticmethod
    def register_event(logcat_event, serialno=None):
        if not serialno:
            serialno = LogcatListener._find_first_device_serialno()
        if not serialno:
            return

        if isinstance(logcat_event, LogcatEvent):
            if not serialno in LogcatListener.WORK_THREADS.keys():
                return
            LogcatListener.WORK_THREADS[serialno].register_event(logcat_event=logcat_event)

    @staticmethod
    def unregister_event(logcat_event, serialno=None):
        if not serialno:
            serialno = LogcatListener._find_first_device_serialno()
        if not serialno:
            return

        if isinstance(logcat_event, LogcatEvent):
            if not serialno in LogcatListener.WORK_THREADS.keys():
                return
            LogcatListener.WORK_THREADS[serialno].unregister_event(logcat_event=logcat_event)
