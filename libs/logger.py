import threading
import datetime
import shutil
import os

from libs import ROOT_DIR

try:
    import queue
    import io as sio
except ImportError:
    import Queue as queue
    import StringIO as sio

class LoggerThread(threading.Thread):
    MAX_SIZE = 10000
    BUF_SIZE = 10
    LOG_DIR = ROOT_DIR + "/log/"

    def __init__(self, max_size=MAX_SIZE, buf_size=BUF_SIZE, log_dir=LOG_DIR):
        super(LoggerThread, self).__init__()
        self.daemon = True
        self.msg_q = queue.Queue()
        self.stoprequest = threading.Event()
        self.msg_stream = sio.StringIO()
        self.max_size = max_size
        self.buf_size = buf_size
        self.current_size = 0
        self.log_dir = log_dir
        self._to_stdout = False
        self._to_file = False

        if len(self.log_dir) < 1 and self.log_dir[-1] != "/":
            self.log_dir += "/"
        self._update_timestamp()

    def to_file(self):
        self._to_file = True

    def to_stdout(self):
        self._to_stdout = True

    def _update_timestamp(self):
        self.log_timestamp = datetime.datetime.now()

    def _dump(self):
        if not self._to_file:
            return

        t = self.log_timestamp
        
        filename = "{}{:02d}{:02d}_{:02d}{:02d}{:02d}.log".format(t.year, t.month, t.day, t.hour, t.minute, t.second)
        with open(self.log_dir + filename, "a") as f:
            self.msg_stream.seek(0)
            shutil.copyfileobj(self.msg_stream, f)

        self.msg_stream.truncate(0)

    def push(self, msg):
        self.msg_q.put(msg)

    def join(self, timeout=None):
        self.stoprequest.set()
        super(LoggerThread, self).join(timeout)

    def run(self):
        os.system("mkdir -p {}".format(self.log_dir))
        while not self.stoprequest.isSet():
            try:
                msg = self.msg_q.get(True, 0.1)
                logtext = "[{}] {}\n".format(datetime.datetime.now(), msg)
                self.msg_stream.write(logtext)

                if self._to_stdout:
                    import sys
                    sys.stdout.write(logtext)
                    sys.stdout.flush()

                self.current_size += 1
                if self.current_size % self.buf_size == 0:
                    self._dump()

                if self.current_size >= self.max_size:
                    self._dump()
                    self.current_size = 0
                    self._update_timestamp()

            except queue.Empty:
                continue

        if self.current_size > 0:
            self._dump()
            self.current_size = 0

class Logger(object):
    WORK_THREAD = LoggerThread()
    HAS_BEEN_INIT = False

    class Mode(object):
        STDOUT = 1
        FILE = 2
        BOTH_FILE_AND_STDOUT = STDOUT | FILE

    @staticmethod
    def init(mode=Mode.BOTH_FILE_AND_STDOUT):
        if Logger.HAS_BEEN_INIT:
            return

        if mode & Logger.Mode.STDOUT > 0:
            Logger.WORK_THREAD.to_stdout()
        if mode & Logger.Mode.FILE > 0:
            Logger.WORK_THREAD.to_file()

        Logger.WORK_THREAD.start()
        Logger.HAS_BEEN_INIT = True

    @staticmethod
    def finalize():
        if not Logger.HAS_BEEN_INIT:
            return

        Logger.WORK_THREAD.join()
        Logger.HAS_BEEN_INIT = False

    @staticmethod
    def log(tag, msg):
        Logger.WORK_THREAD.push("{}: {}".format(tag, msg))
