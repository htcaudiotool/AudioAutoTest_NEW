from com.dtmilano.android.viewclient import ViewClient
import os
import subprocess
import time
import threading

# Add the libs to the search path
import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from libs import ROOT_DIR
from libs.adbutils import Adb
from libs.audiofunction import AudioFunction, ToneDetector, DetectionStateChangeListenerThread
from libs.logger import Logger
from libs.aatapp import AATApp

TAG = "example.py"
OUT_FREQ = 440

def log(msg):
    Logger.log(TAG, msg)

def run():
    AudioFunction.init()
    Logger.init(Logger.Mode.STDOUT)
    Adb.init()

    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity

    device, serialno = ViewClient.connectToDeviceOrExit()
    vc = ViewClient(device, serialno, autodump=False)

    if not device.isScreenOn():
        device.wake()

    vc.dump()

    import StringIO as sio
    so = sio.StringIO()
    vc.traverse(stream=so)
    if "lockscreen" in so.getvalue():
        device.unlock()

    # keymap reference:
    #   https://github.com/dtmilano/AndroidViewClient/blob/master/src/com/dtmilano/android/adb/androidkeymap.py
    device.press("HOME")
    time.sleep(1)
    device.startActivity(component=component)
    time.sleep(1)

    playback_task_run(device)
    record_task_run(device, serialno)

    AudioFunction.finalize()
    Logger.finalize()

def playback_task_run(device):
    log("dev_playback_start(nonoffload)")
    AATApp.playback_nonoffload(device)

    th = DetectionStateChangeListenerThread()
    th.start()

    log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))

    # Waiting for the event of tone detected, blocking with a 5 secs timeout
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not detected, abort the function...")
        AATApp.playback_stop(device)
        return

    time.sleep(1)

    # The thread just stops the playback and then continues
    def dev_stop_then_play():
        log("thread stops the playback")
        AATApp.playback_stop(device)
        time.sleep(4)
        log("thread starts the playback")
        AATApp.playback_nonoffload(device)
        log("thread returns")

    threading.Thread(target=dev_stop_then_play).start()
    log("Waiting for {} Hz pure tone detected".format(OUT_FREQ))

    # Waiting the event that the tone is detected again after the tone is missing
    elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
    log("elapsed: {} ms".format(elapsed))

    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    log("dev_playback_stop(nonoffload)")
    AATApp.playback_stop(device)


def record_task_run(device, serialno):
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

    def stop_then_play():
        log("thread stops the playback")
        AudioFunction.stop_audio()
        time.sleep(4)
        log("thread starts the playback")
        AudioFunction.play_sound(out_freq=OUT_FREQ)
        log("thread returns")

    threading.Thread(target=stop_then_play).start()
    log("Waiting for {} Hz pure tone detected".format(OUT_FREQ))
    elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
    log("elapsed: {} ms".format(elapsed))

    time.sleep(1)

    log("Trying to wait a timeout event")
    elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.FALLING_EDGE, timeout=10)
    log("elapsed: {} ms".format(elapsed))

    log("dev_record_stop")
    AATApp.record_stop(device)

    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    AudioFunction.stop_audio()


if __name__ == "__main__":
    run()
