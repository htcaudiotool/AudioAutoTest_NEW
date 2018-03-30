from com.dtmilano.android.viewclient import ViewClient
import os
import subprocess
import time
import datetime

import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from libs import ROOT_DIR
from libs.adbutils import Adb
from libs.audiofunction import AudioFunction, ToneDetector, DetectionStateChangeListenerThread
from libs.logger import Logger
from libs.aatapp import AATApp
from libs.trials import Trial, TrialHelper

TAG = "ssr_test.py"

DEVICE_MUSIC_DIR = "sdcard/Music/"
OUT_FREQ = 440
BATCH_SIZE = 5
PARTIAL_RAMDUMP_ENABLED = False

FILE_NAMES = [
    "440Hz.wav",
    "440Hz.mp3"
]

def push_files_if_needed(serialno):
    out, _ = Adb.execute(cmd=["shell", "ls", DEVICE_MUSIC_DIR], serialno=serialno)

    # The command "adb shell ls" might return several lines of strings where each line lists multiple file names
    # Then the result should be handled line by line:
    #           map function for split with spaces and reduce function for concatenate the results of each line
    files = reduce(lambda x, y: x+y, map(lambda s: s.split(), out.splitlines())) if out else []

    for file_to_pushed in FILE_NAMES:
        if file_to_pushed in files:
            continue
        out, _ = subprocess.Popen(["find", ROOT_DIR, "-name", file_to_pushed], stdout=subprocess.PIPE).communicate()
        file_path = out.splitlines()[0] if out else None
        if file_path:
            os.system("adb -s {} push {} {} > /dev/null".format(serialno, file_path, DEVICE_MUSIC_DIR))
        else:
            raise ValueError("Cannot find the file \"{}\", please place it under the project tree.".format(file_to_pushed))

def log(msg):
    Logger.log(TAG, msg)

import StringIO as sio
def wake_device(device, serialno):
    if device.isScreenOn():
        return

    device.wake()
    vc = ViewClient(device, serialno, autodump=False)
    try:
        vc.dump(sleep=0)
        so = sio.StringIO()
        vc.traverse(stream=so)

        if "lockscreen" in so.getvalue():
            device.unlock()
    except:
        pass

def handle_ssr_ui():
    elapsed = SSRDumpListener.wait_for_dialog(timeout=60)
    log("SSR dialog shows: {} (elapsed {} ms)".format(SSRDumpListener.WORK_THREAD.state, elapsed))
    if elapsed > 0:
        SSRDumpListener.dismiss_dialog()
        log("dismiss SSR dialog")

def run(num_iter=1, serialno=None):
    AudioFunction.init()
    Logger.init(Logger.Mode.BOTH_FILE_AND_STDOUT)
    Adb.init()

    os.system("mkdir -p {}/ssr_report > /dev/null".format(ROOT_DIR))
    t = datetime.datetime.now()
    filename = "report_{}{:02d}{:02d}_{:02d}{:02d}{:02d}.json".format(t.year, t.month, t.day, t.hour, t.minute, t.second)

    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity

    device, serialno = ViewClient.connectToDeviceOrExit(serialno=serialno)
    wake_device(device, serialno)
    SSRDumpListener.init(device, serialno)

    # keymap reference:
    #   https://github.com/dtmilano/AndroidViewClient/blob/master/src/com/dtmilano/android/adb/androidkeymap.py
    device.press("HOME")
    time.sleep(1)
    device.startActivity(component=component)
    time.sleep(1)

    trials = []
    batch_count = 1
    while num_iter > 0:
        log("-------- batch_run #{} --------".format(batch_count))
        trials_batch = []
        trials_batch += playback_task_run(device, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += record_task_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += voip_task_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))

        map(lambda trial: trial.put_extra(name="batch_id", value=batch_count), trials_batch)
        trials += trials_batch
        with open("{}/ssr_report/{}".format(ROOT_DIR, filename), "w") as f:
            f.write(TrialHelper.to_json(trials))

        num_iter -= BATCH_SIZE
        batch_count += 1

    AudioFunction.finalize()
    Logger.finalize()
    SSRDumpListener.finalize()


def playback_task_run(device, num_iter=1):
    log("playback_task_run++")

    trials = []

    th = DetectionStateChangeListenerThread()
    th.start()

    log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))

    funcs = {
        "nonoffload": AATApp.playback_nonoffload,
        "offload"   : AATApp.playback_offload
    }

    for i in range(num_iter):
        log("-------- playback_task #{} --------".format(i+1))
        for name, func in funcs.items():
            trial = Trial(taskname="playback_{}".format(name))
            trial.put_extra(name="iter_id", value=i+1)

            log("dev_playback_{}_start".format(name))
            time.sleep(1)
            th.reset()
            log("reset DetectionStateChangeListener")
            
            log("trigger_ssr() for idle")
            AATApp.trigger_ssr(device)
            
            if PARTIAL_RAMDUMP_ENABLED:
                handle_ssr_ui()
            time.sleep(1)
            
            func(device)

            if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                log("the tone was not detected, abort the iteration this time...")
                AATApp.playback_stop(device)
                trial.invalidate(errormsg="early return, possible reason: rx no sound")
                trials.append(trial)
                continue
            else:
                log("--> ssr test playback: active pass")
            time.sleep(1)

            log("trigger_ssr()")
            AATApp.trigger_ssr(device)

            if PARTIAL_RAMDUMP_ENABLED:
                handle_ssr_ui()

            log("Waiting for SSR recovery")
            elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=5)
            log("elapsed: {} ms".format(elapsed))
            
            if elapsed >= 0:
                log("--> ssr test playback: rising pass")

            if PARTIAL_RAMDUMP_ENABLED:
                log("Waiting for the partial ramdump completed")
                handle_ssr_ui()

            if elapsed >= 0 and not PARTIAL_RAMDUMP_ENABLED:
                time.sleep(10 - elapsed/1000.0)

            trial.put_extra(name="elapsed", value=elapsed)
            trials.append(trial)

            log("dev_playback_stop")
            AATApp.playback_stop(device)
            th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5)

    log("-------- playback_task done --------")
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    log("playback_task_run--")
    return trials

def record_task_run(device, serialno, num_iter=1):
    log("record_task_run++")

    trials = []

    log("dev_record_start")
    AATApp.record_start(device)
    time.sleep(2)

    th = DetectionStateChangeListenerThread()
    th.start()

    log("ToneDetector.start_listen(serialno={}, target_freq={})".format(serialno, OUT_FREQ))
    ToneDetector.start_listen(serialno=serialno, target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))
    log("AudioFunction.play_sound(out_freq={})".format(OUT_FREQ))
    AudioFunction.play_sound(out_freq=OUT_FREQ)

    time.sleep(3)
    for i in range(num_iter):
        log("-------- record_task #{} --------".format(i+1))

        trial = Trial(taskname="record")
        trial.put_extra(name="iter_id", value=i+1)

        th.reset()
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            trial.invalidate(errormsg="early return, possible reason: tx no sound")
            trials.append(trial)
            continue
        else:
            log("--> ssr test record: active pass")

        log("trigger_ssr()")
        AATApp.trigger_ssr(device)

        if PARTIAL_RAMDUMP_ENABLED:
            handle_ssr_ui()

        log("Waiting for SSR recovery")
        elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
        log("elapsed: {} ms".format(elapsed))
        
        if elapsed >= 0:
                log("--> ssr test record: rising pass")

        if PARTIAL_RAMDUMP_ENABLED:
            log("Waiting for the partial ramdump completed")
            handle_ssr_ui()

        if elapsed >= 0 and not PARTIAL_RAMDUMP_ENABLED:
            time.sleep(10 - elapsed/1000.0)

        trial.put_extra(name="elapsed", value=elapsed)
        trials.append(trial)

    log("-------- record_task done --------")
    log("AudioFunction.stop_audio()")
    AudioFunction.stop_audio()

    log("dev_record_stop")
    AATApp.record_stop(device)
    time.sleep(5)
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    log("record_task_run--")
    return trials

def voip_task_run(device, serialno, num_iter=1):
    log("voip_task_run++")

    trials = []

    # AATApp.voip_use_speaker(device)
    time.sleep(2)

    th = DetectionStateChangeListenerThread()
    th.start()

    log("ToneDetector.start_listen(target_freq={})".format(serialno, OUT_FREQ))
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))

    AATApp.voip_start(device)
    for i in range(num_iter):
        log("-------- dev_voip_rx_task #{} --------".format(i+1))

        trial = Trial(taskname="voip_rx")
        trial.put_extra(name="iter_id", value=i+1)

        time.sleep(1)
        th.reset()

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            trial.invalidate(errormsg="early return, possible reason: rx no sound")
            trials.append(trial)
            continue
        time.sleep(1)

        log("trigger_ssr()")
        AATApp.trigger_ssr(device)

        if PARTIAL_RAMDUMP_ENABLED:
            handle_ssr_ui()

        log("Waiting for SSR recovery")
        elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
        log("elapsed: {} ms".format(elapsed))

        if PARTIAL_RAMDUMP_ENABLED:
            log("Waiting for the partial ramdump completed")
            handle_ssr_ui()

        if elapsed >= 0 and not PARTIAL_RAMDUMP_ENABLED:
            time.sleep(10 - elapsed/1000.0)

        trial.put_extra(name="elapsed", value=elapsed)
        trials.append(trial)

    log("-------- dev_voip_rx_task done --------")
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    th = DetectionStateChangeListenerThread()
    th.start()

    time.sleep(2)
    AATApp.voip_mute_output(device)
    time.sleep(10)
    log("ToneDetector.start_listen(serialno={}, target_freq={})".format(serialno, None))
    ToneDetector.start_listen(serialno=serialno, target_freq=None, cb=lambda event: th.tone_detected_event_cb(event))

    for i in range(num_iter):
        log("-------- dev_voip_tx_task #{} --------".format(i+1))

        trial = Trial(taskname="voip_tx")
        trial.put_extra(name="iter_id", value=i+1)

        time.sleep(2)

        log("AudioFunction.play_sound(out_freq={})".format(OUT_FREQ))
        AudioFunction.play_sound(out_freq=OUT_FREQ)

        th.reset()
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            trial.invalidate(errormsg="early return, possible reason: tx no sound")
            trials.append(trial)
            continue
        time.sleep(2)

        log("trigger_ssr()")
        AATApp.trigger_ssr(device)

        if PARTIAL_RAMDUMP_ENABLED:
            handle_ssr_ui()

        log("Waiting for SSR recovery")
        elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
        log("elapsed: {} ms".format(elapsed))

        if PARTIAL_RAMDUMP_ENABLED:
            log("Waiting for the partial ramdump completed")
            handle_ssr_ui()

        if elapsed >= 0 and not PARTIAL_RAMDUMP_ENABLED:
            time.sleep(10 - elapsed/1000.0)

        trial.put_extra(name="elapsed", value=elapsed)
        trials.append(trial)

        log("AudioFunction.stop_audio()")
        AudioFunction.stop_audio()

    log("-------- dev_voip_tx_task done --------")
    log("dev_voip_stop")
    AATApp.voip_stop(device)
    time.sleep(5)
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    log("voip_task_run--")
    return trials


import threading, re
class SSRDumpListener(object):
    WORK_THREAD = None
    PERIOD = 0.5
    FILTER = "com.htc.android.ssdtest/com.htc.android.ssdtest.DialogShower"
    MSG_VIEW_ID = "android:id/message"
    BTN_ID = "android:id/button2"
    RAMDUMP_COMPLETED_KEYMSG = "Dump RAM logs completely"

    class SSRDumpListenerThread(threading.Thread):
        class State(object):
            IDLE = "idle"
            BEING_DUMPED = "being dumped"
            DUMPED = "has been dumped"

        def __init__(self, device, serialno):
            super(SSRDumpListener.SSRDumpListenerThread, self).__init__()
            self.daemon = True
            self.stoprequest = threading.Event()
            self.lock = threading.Lock()
            self.device = device
            self.serialno = serialno
            self.vc = ViewClient(device, serialno, autodump=False)
            self.state = SSRDumpListener.SSRDumpListenerThread.State.IDLE

        def join(self, timeout=None):
            self.stoprequest.set()
            super(SSRDumpListener.SSRDumpListenerThread, self).join(timeout)

        def run(self):
            pattern = re.compile("Window{.+?}")
            while not self.stoprequest.isSet():
                try:
                    win_dumpsys, _ = subprocess.Popen( \
                        "adb -s {} shell dumpsys window windows | grep \"Window #\"".format(self.serialno), \
                        shell=True, stdout=subprocess.PIPE).communicate()

                    win_info_strs = map(lambda s: pattern.search(s.strip()).group(0), win_dumpsys.splitlines())
                    win_info_strs = [s[7:-1] for s in win_info_strs if len(s) > 7]
                    self.win_info = dict( [(ss[2], ss[0]) for ss in map(lambda s: s.split(), win_info_strs)] )
                    if SSRDumpListener.FILTER in self.win_info.keys():
                        self.vc.dump(window=self.win_info[SSRDumpListener.FILTER], sleep=0)
                        views = dict( [(v.getId(), v) for v in self.vc.getViewsById().values() if len(v.getId()) > 0] )

                        if SSRDumpListener.MSG_VIEW_ID in views.keys():
                            msg = views[SSRDumpListener.MSG_VIEW_ID].getText()

                            if SSRDumpListener.RAMDUMP_COMPLETED_KEYMSG in msg:
                                self.state = SSRDumpListener.SSRDumpListenerThread.State.DUMPED
                            else:
                                self.state = SSRDumpListener.SSRDumpListenerThread.State.BEING_DUMPED

                    else:
                        self.state = SSRDumpListener.SSRDumpListenerThread.State.IDLE

                except:
                    pass
                time.sleep(SSRDumpListener.PERIOD)

        def dismiss_dialog(self):
            if self.state == SSRDumpListener.SSRDumpListenerThread.State.IDLE:
                return

            self.vc.dump(window=self.win_info[SSRDumpListener.FILTER], sleep=0)
            views = dict( [(v.getId(), v) for v in self.vc.getViewsById().values() if len(v.getId()) > 0] )

            if SSRDumpListener.BTN_ID in views.keys():
                x, y = views[SSRDumpListener.BTN_ID].getCenter()
                self.device.touch(x, y)

            self.state = SSRDumpListener.SSRDumpListenerThread.State.IDLE

    @staticmethod
    def init(device, serialno):
        if not PARTIAL_RAMDUMP_ENABLED:
            return

        SSRDumpListener.WORK_THREAD = SSRDumpListener.SSRDumpListenerThread(device, serialno)
        SSRDumpListener.WORK_THREAD.start()

    @staticmethod
    def wait_for_dialog(timeout=-1):
        if not PARTIAL_RAMDUMP_ENABLED:
            return

        cnt = 0
        while SSRDumpListener.WORK_THREAD.state == SSRDumpListener.SSRDumpListenerThread.State.IDLE:
            cnt += 1
            if timeout > 0 and cnt >= timeout * 10.0:
                return -1
            time.sleep(0.1)

        return cnt * 100.0

    @staticmethod
    def dismiss_dialog():
        if not PARTIAL_RAMDUMP_ENABLED:
            return

        SSRDumpListener.WORK_THREAD.dismiss_dialog()

    @staticmethod
    def finalize():
        if not PARTIAL_RAMDUMP_ENABLED:
            return

        SSRDumpListener.WORK_THREAD.join()

if __name__ == "__main__":
    serialno = str(sys.argv[1]) if len(sys.argv) > 1 else None
    num_iter = int(sys.argv[2]) if len(sys.argv) > 1 else 1
    #num_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    # ViewClient tries to access the system arguments, then it might cause RuntimeError
    if len(sys.argv) > 1: del sys.argv[1:]
    try:
        run(num_iter=num_iter, serialno=serialno)
    except Exception as e:
        print(e)
