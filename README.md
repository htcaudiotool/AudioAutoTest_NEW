# AudioAutoTest
## Description
This is a auto-testing framework of audio functions for Android devices.

## Repository
```
AudioAutoTest/
├── apk
│   └── debug
│       ├── audiofunctionsdemo.apk
│       └── output.json
├── audiofiles
│   ├── 440Hz.mp3
│   └── 440Hz.wav
├── install.sh
├── libs
│   ├── __init__.py
│   ├── aatapp.py
│   ├── audiofunction.py
│   ├── audiothread.py
│   ├── logcatlistener.py
│   ├── logger.py
│   ├── trials.py
│   └── README.md
├── README.md
├── requirements.txt
└── scripts
    ├── example.py
    └── ssr_test.py
```

- For checking the detailed information of APIs, please refer to the [documentation](https://github.com/HW-Lee/AudioAutoTest/blob/master/libs/README.md)

## Installation
### Requirements
- pip
- Python 2.7 (3.x is not supported in `ViewClient`)
- virtualenv

#### Create a virtual environment
```
{WORK_DIR}$ mkdir venv
{WORK_DIR}$ virtualenv -p python2 venv/py2
Running virtualenv with interpreter /usr/bin/python2
New python executable in {WORK_DIR}/venv/py2/bin/python2
Also creating executable in {WORK_DIR}/venv/py2/bin/python
Installing setuptools, pip, wheel...done.
{WORK_DIR}$ source venv/py2/bin/activate
(py2) {WORK_DIR}$
```

#### The dependencies should be installed with a command
```
(py2) {WORK_DIR}$ ./install.sh
```

#### Tested the example scripts
```
(py2) {WORK_DIR}$ python scripts/example.py
```

## Trying to write some testing scripts
### scripts/example.py
```python
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
```

```
[2017-11-17 11:56:56.978264] Adb: exec: ['adb', 'start-server']
[2017-11-17 11:57:11.915171] example.py: dev_playback_start(nonoffload)
[2017-11-17 11:57:12.030688] example.py: ToneDetector.start_listen(target_freq=440)
[2017-11-17 11:57:12.531372] DetectionStateChangeListenerThread: tone_detected_event_cb: ('11-17 11:57:12.470539', 'tone detected')
[2017-11-17 11:57:12.531449] DetectionStateChangeListenerThread: get event: ('active', 0)
[2017-11-17 11:57:13.532756] example.py: thread stops the playback
[2017-11-17 11:57:13.532869] example.py: Waiting for 440 Hz pure tone detected
[2017-11-17 11:57:13.997034] DetectionStateChangeListenerThread: tone_detected_event_cb: ('11-17 11:57:13.971802', 'tone missing')
[2017-11-17 11:57:13.997130] DetectionStateChangeListenerThread: get event: ('inactive', 0)
[2017-11-17 11:57:13.997184] DetectionStateChangeListenerThread: get event: ('falling', 1501.263)
[2017-11-17 11:57:17.665619] example.py: thread starts the playback
[2017-11-17 11:57:17.765829] example.py: thread returns
[2017-11-17 11:57:18.229904] DetectionStateChangeListenerThread: tone_detected_event_cb: ('11-17 11:57:18.172813', 'tone detected')
[2017-11-17 11:57:18.233318] DetectionStateChangeListenerThread: get event: ('active', 0)
[2017-11-17 11:57:18.233526] DetectionStateChangeListenerThread: get event: ('rising', 4201.011)
[2017-11-17 11:57:18.233615] example.py: elapsed: 4201.011 ms
[2017-11-17 11:57:18.233664] example.py: ToneDetector.stop_listen()
[2017-11-17 11:57:18.240996] example.py: dev_playback_stop(nonoffload)
[2017-11-17 11:57:18.356569] example.py: dev_record_start
[2017-11-17 11:57:20.522989] example.py: ToneDetector.start_listen(serialno=************, target_freq=440)
[2017-11-17 11:57:20.523152] Adb: exec: ['adb', '-s', '************', 'logcat', '-c']
[2017-11-17 11:57:26.895166] example.py: AudioFunction.play_sound(out_freq=440)
[2017-11-17 11:57:28.661583] DetectionStateChangeListenerThread: tone_detected_event_cb: ('11-17 11:57:25.628', 'tone detected')
[2017-11-17 11:57:29.870512] example.py: thread stops the playback
[2017-11-17 11:57:29.870627] example.py: Waiting for 440 Hz pure tone detected
[2017-11-17 11:57:29.870684] DetectionStateChangeListenerThread: get event: ('active', 0)
[2017-11-17 11:57:30.134398] DetectionStateChangeListenerThread: tone_detected_event_cb: ('11-17 11:57:28.625', 'tone missing')
[2017-11-17 11:57:30.134498] DetectionStateChangeListenerThread: get event: ('inactive', 0)
[2017-11-17 11:57:30.134538] DetectionStateChangeListenerThread: get event: ('falling', 2997.0)
[2017-11-17 11:57:33.902408] example.py: thread starts the playback
[2017-11-17 11:57:33.902488] example.py: thread returns
[2017-11-17 11:57:35.019318] DetectionStateChangeListenerThread: tone_detected_event_cb: ('11-17 11:57:32.562', 'tone detected')
[2017-11-17 11:57:35.050848] DetectionStateChangeListenerThread: get event: ('active', 0)
[2017-11-17 11:57:35.050936] DetectionStateChangeListenerThread: get event: ('rising', 3937.0)
[2017-11-17 11:57:35.050996] example.py: elapsed: 3937.0 ms
[2017-11-17 11:57:36.052280] example.py: Trying to wait a timeout event
[2017-11-17 11:57:46.065985] example.py: elapsed: -1 ms
[2017-11-17 11:57:46.066288] example.py: dev_record_stop
[2017-11-17 11:57:46.197932] example.py: ToneDetector.stop_listen()
```
