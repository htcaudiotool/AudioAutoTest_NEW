from com.dtmilano.android.viewclient import ViewClient
import os
import subprocess
import time
import datetime
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
import argparse
import platform
from scipy.fftpack import fft


import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from libs import ROOT_DIR, STDNUL
from libs.adbutils import Adb
#from libs.audiofunction import AudioFunction, ToneDetector, DetectionStateChangeListenerThread
from libs.logger import Logger
from libs.aatapp import AATApp
from libs.trials import Trial, TrialHelper
from libs.logcatlistener import LogcatListener, LogcatEvent

REPORT_DIR = "report"
PLATFORM = platform.system()
LINUX = 'Linux'
WINDOWS = 'Windows'

try:
    import queue
except ImportError:
    import Queue as queue
    
TAG = "phone_call_test.py"

DEVICE_MUSIC_DIR = "sdcard/Music/"
OUT_FREQ = 440
BATCH_SIZE = 5
PARTIAL_RAMDUMP_ENABLED = True

FILE_NAMES = [
    "440Hz.wav",
    "440Hz.mp3"
]

SINK_PORT = [
    "analog-output-headphones",
    "analog-output-lineout",
    "analog-output-speaker"
]

SOURCE_PORT = [
    "analog-input-front-mic",
    "analog-input-rear-mic",
    "analog-input-linein"
]


out_number = {
    "target" : [8, 2, 2, 9, 5, 6],     #DUT
    "test" : [8, 7, 1, 1, 2, 1]        #Remote
}

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
            os.system("adb -s {} push {} {} > {}".format(serialno, file_path, DEVICE_MUSIC_DIR, STDNUL))
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
            log("device unlock")
            device.unlock()
    except:
        pass

def run(num_iter=1, serialno1=None, serialno2=None):
    '''
    # initail componet
    AudioFunction.init()
    Logger.init(Logger.Mode.BOTH_FILE_AND_STDOUT)
    Adb.init()

    os.system("mkdir -p {}/{} > /dev/null".format(ROOT_DIR, REPORT_DIR))  # windows need modified
    t = datetime.datetime.now()
    filename = "report_{}{:02d}{:02d}_{:02d}{:02d}{:02d}.json".format(t.year, t.month, t.day, t.hour, t.minute, t.second)

    device, serialno = ViewClient.connectToDeviceOrExit(serialno=None)
    wake_device(device, serialno)
    # keymap reference:
    #   https://github.com/dtmilano/AndroidViewClient/blob/master/src/com/dtmilano/android/adb/androidkeymap.py
    device.press("HOME")
    time.sleep(0.5)

    trials = []
    batch_count = 1
    while num_iter > 0:
        log("-------- batch_run #{} --------".format(batch_count))
        trials_batch = []
        trials_batch += playback_task_run(device, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += playback_format_task_run(device, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += playback_GoogleMusic_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))

        map(lambda trial: trial.put_extra(name="batch_id", value=batch_count), trials_batch)
        trials += trials_batch
        with open("{}/{}/{}".format(ROOT_DIR, REPORT_DIR, filename), "w") as f:
            f.write(TrialHelper.to_json(trials))

        num_iter -= BATCH_SIZE
        batch_count += 1

    AudioFunction.finalize()
    Logger.finalize()
    '''
    
    # initail componet
    Logger.init(Logger.Mode.BOTH_FILE_AND_STDOUT)
    Adb.init()
    
    if PLATFORM == WINDOWS:
        os.system("mkdir {}/{} ".format(ROOT_DIR, REPORT_DIR))
    elif PLATFORM == LINUX:
        os.system("mkdir -p {}/{} ".format(ROOT_DIR, REPORT_DIR))
    t = datetime.datetime.now()
    filename = "report_{}{:02d}{:02d}_{:02d}{:02d}{:02d}.json".format(t.year, t.month, t.day, t.hour, t.minute, t.second)
    
    trials = []
    
    if serialno1:
        device1, serialno1 = ViewClient.connectToDeviceOrExit(serialno=serialno1)
        target_sn = serialno1
        log(serialno1)

    if serialno2:
        device2, serialno2 = ViewClient.connectToDeviceOrExit(serialno=serialno2)
        test_sn = serialno2
        log(serialno2)
        
    if serialno1 is None or serialno2 is None:
        log("please input 2 phone serialno")
        return 
    
    time.sleep(1)
    wake_device(device1, serialno1)
    time.sleep(1)
    wake_device(device2, serialno2)
    time.sleep(1)
    device1.press("HOME")
    device2.press("HOME")
    time.sleep(1)
    
    original = get_Auto_Mute_Mode()
    #disable_Auto_Mute_Mode()

    batch_count = 1
    while num_iter > 0:
        trials_batch = []
        
        # target control_MO_phone out phone
        log("start target MO")
        ret = control_MO_phone(device1, serialno1, True)
        if ret is False:
            log("can't out phone call")
            control_Stop_Call(device1, serialno1)
            continue
        else:
            log("phone call out: TX test")

        # test   control_MT_phone then recive phone
        ret = control_MT_phone(device2, serialno2)
        if ret is False:
            log("can't answer phone call")
            control_Stop_Call(device1, serialno1)
            continue
        else:
            log("phone call start: TX test")

        if not detect_DQ_start(device1, serialno1):
            log("can't detect DQ log start")
            # add trials for DQ
            continue
    
        log("-------- batch_run #{} --------".format(batch_count))
        # phone call start
        
        trials_batch += phone_call_tx_task()
        time.sleep(2)
        trials_batch += phone_call_rx_task()
        
        control_Stop_Call(device1, serialno1)
        if not detect_DQ_stop(device1, serialno1):
            log("can't detect DQ log stop")
            continue

        map(lambda trial: trial.put_extra(name="batch_id", value=batch_count), trials_batch)
        trials += trials_batch
        with open("{}/{}/{}".format(ROOT_DIR, REPORT_DIR, filename), "w") as f:
            f.write(TrialHelper.to_json(trials))

        num_iter -= BATCH_SIZE
        batch_count += 1

    #######
        
    change_soundcard_setting(0)
    set_Auto_Mute_Mode(original)
    log("-------- set_Auto_Mute_Mode --------")

    Logger.finalize()

def phone_call_tx_task():
    log("phone_call_task_tx_run++")
    
    trials = []
    trial = Trial(taskname="phonecall_task_tx")
    
    change_soundcard_setting(0)
    log("change_soundcard_setting(0)")
    set_Auto_Mute_Mode("Line Out+Speaker")
        
    
    playbackThread = PlaybackThread()
    recordThread = RecordThread()
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event), recordThread = recordThread)
    
    playbackThread.start()
    time.sleep(1)
    recordThread.start()
    
    log("-> phone call tx start:")
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not detected, abort the iteration this time...")
        trial.invalidate(errormsg="tx task fail")
        trials.append(trial)
    else:
        log("-> phone call tx: pass")
        trial.put_extra(name="phone call tx", value="pass")

    recordThread.stopRecord()
    playbackThread.stopPlayback()
    trials.append(trial)

    time.sleep(1)
    
    if playbackThread.isrun:
        playbackThread.join()
        
    if recordThread.isrun:
        recordThread.join()

    ToneDetector.stop_listen()
    th.join()
    
    return trials
    
def phone_call_rx_task():
    log("phone_call_task_rx_run++")
    
    trials = []
    trial = Trial(taskname="phonecall_task_rx")
    
    change_soundcard_setting(1)
    log("change_soundcard_setting(1)")
    disable_Auto_Mute_Mode()

    playbackThread = PlaybackThread()
    recordThread = RecordThread()
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event), recordThread = recordThread)
    
    playbackThread.start()
    time.sleep(1)
    recordThread.start()

    log("-> phone call rx start:")
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not detected, abort the iteration this time...")
        trial.invalidate(errormsg="rx task fail")
        trials.append(trial)
    else:
        log("-> phone call rx: pass")
        trial.put_extra(name="phone call rx", value="pass")
    SINK_PORT
    recordThread.stopRecord()
    playbackThread.stopPlayback()
    trials.append(trial)

    time.sleep(1)
    
    if playbackThread.isrun:
        playbackThread.join()
        
    if recordThread.isrun:
        recordThread.join()
        
    ToneDetector.stop_listen()
    th.join()

    return trials
    
def find_running_sink_soundcard():
    index = 0
    ret = -1
    for i in range(32):
        cmd = "pacmd list-sinks | grep  '* index: {}' > {}".format(i, STDNUL)
        ret = os.system(cmd)
        if ret is 0:
            break
    
    index = i
    return index

def find_running_source_soundcard():
    index = 0
    ret = -1
    for i in range(32):
        cmd = "pacmd list-sources | grep  '* index: {}' > {}".format(i, STDNUL)
        ret = os.system(cmd)
        if ret is 0:
            break
    
    index = i
    return index

def switch_sink_port(sndcard_index, port_name):
    cmd = "pacmd set-sink-port {} {} > {}".format(sndcard_index, port_name, STDNUL)
    print cmd
    os.system(cmd)

def switch_source_port(sndcard_index, port_name):
    cmd = "pacmd set-source-port {} {} > {}".format(sndcard_index, port_name, STDNUL)
    print cmd
    os.system(cmd)

def get_Auto_Mute_Mode():
    out, _ = subprocess.Popen("amixer -c 0 sget 'Auto-Mute Mode' | grep 'Item0:'", shell = True, stdout = subprocess.PIPE).communicate()
    result = out.splitlines()[0].split("\'")[1] if len(out.splitlines()) > 0 else None
    
    return result

def disable_Auto_Mute_Mode():
    os.system("amixer -c 0 sset 'Auto-Mute Mode' Disabled > {}".format(STDNUL)) # 0 is default
    return

def set_Auto_Mute_Mode(state):
    cmd = "amixer -c 0 sset 'Auto-Mute Mode' '{}' > {}".format(state, STDNUL)
    os.system(cmd) # 0 is default
    return

def change_soundcard_setting(port):
    index = find_running_sink_soundcard()
    
    switch_sink_port(index, SINK_PORT[port])
    log( "sink port = {}".format(SINK_PORT[port]))
    
    index = find_running_source_soundcard()
    
    switch_source_port(index, SOURCE_PORT[port])
    log("sorce port = {}".format(SOURCE_PORT[port]))

def get_number_id(vc, number):
    phone_view_dict = vc.getViewsById()
    for key, value in phone_view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/zero") > 0 and number is 0:
            return key
        if strTemp.find("id/one") > 0 and number is 1:
            return key
        if strTemp.find("id/two") > 0 and number is 2:
            return key
        if strTemp.find("id/three") > 0 and number is 3:
            return key
        if strTemp.find("id/four") > 0 and number is 4:
            return key
        if strTemp.find("id/five") > 0 and number is 5:
            return key
        if strTemp.find("id/six") > 0 and number is 6:
            return key
        if strTemp.find("id/seven") > 0 and number is 7:
            return key
        if strTemp.find("id/eight") > 0 and number is 8:
            return key
        if strTemp.find("id/nine") > 0 and number is 9:
            return key

    return None

def get_dial_id(vc):    
    dial_view_dict = vc.getViewsById()
    for key, value in dial_view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/center_button") > 0:
            return key
    return None

def get_answer_id(vc):    
    answer_view_dict = vc.getViewsById()
    for key, value in answer_view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/answer") > 0:
            return key
    return None

def get_end_id(vc):    
    end_view_dict = vc.getViewsById()
    for key, value in end_view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/end_call") > 0:
            return key
    return None

def control_MO_phone(device, serialno, istarget):
    package = "com.htc.contacts"
    activity = ".DialerTabActivity"
    component = package + "/" + activity

    device.press("HOME")
    time.sleep(1)
    device.startActivity(component=component)
    time.sleep(2)
    
    vc = ViewClient(device, serialno)

    if istarget:
        out = out_number["target"]
    else:
        out = out_number["test"]
        
    for i in out:
        print i
        ret = control_Btn(vc, get_number_id(vc, i))
        if ret is False:
            return False
    
    ret = control_Btn(vc, get_dial_id(vc))
    if ret is False:
        return False
    
    return True

def control_MT_phone(device, serialno):
    time.sleep(3)
    timeout = 0
    while timeout < 10:
        timeout += 1
        log("detect phone {}".format(timeout))
        vc = ViewClient(device, serialno)
        answer_id = get_answer_id(vc)
        if answer_id == None:
            time.sleep(1)
            continue
        control_Btn(vc, answer_id)
        return True
    
    return False

def control_Stop_Call(device, serialno):
    vc = ViewClient(device, serialno)
    time.sleep(1)
    end_id = get_end_id(vc)
    
    if end_id == None:
        log("control_Stop_Call fail")
        return False
    
    control_Btn(vc, end_id)
    
    return True

def control_Btn(vc, key):
    if key == None:
        log("control Btn -> key is None")
        return False
    btn = vc.findViewByIdOrRaise(key)
    btn.touch()
    return True

def control_Quick_Call(device):
    device.touch(720, 600)

def detect_DQ_start(device, serialno):
    for i in range(10):
        time.sleep(0.5)
        is_detect = os.system("adb -s {} shell dmesg | grep -i 'diagchar_read:thread_dq_worke' > /dev/null".format(serialno))
        if is_detect == 0:
            return True

    return False

def detect_DQ_stop(device, serialno):
    for i in range(10):
        time.sleep(0.5)
        is_detect = os.system("adb -s {} shell dmesg | grep -i 'process exit thread_dq_worke' > /dev/null".format(serialno))
        if is_detect == 0:
            return True
    
    return False

class ToneDetector(object):
    WORK_THREAD = None

    TIME_STR_FORMAT = "%m-%d %H:%M:%S.%f"

    class Event(object):
        TONE_DETECTED = "tone detected"
        TONE_MISSING = "tone missing"

    @staticmethod
    def start_listen(target_freq, cb, recordThread, serialno=None):
        ToneDetector.WORK_THREAD = ToneDetectorForServerThread(target_freq=target_freq, callback=cb, recordThread = recordThread)
        ToneDetector.WORK_THREAD.start()

    @staticmethod
    def stop_listen():
        ToneDetector.WORK_THREAD.join()
        ToneDetector.WORK_THREAD = None
        
class ToneDetectorThread(threading.Thread):
    def __init__(self, target_freq, callback):
        super(ToneDetectorThread, self).__init__()
        self.daemon = True
        self.stoprequest = threading.Event()
        self.event_counter = 0
        self.target_freq = target_freq
        self.cb = callback

    def join(self, timeout=None):
        self.stoprequest.set()
        super(ToneDetectorThread, self).join(timeout)

    def run(self):
        raise RuntimeError("The base class does not have implemented run() function.")

    def target_detected(self, freq):
        if freq == 0:
            return False

        if self.target_freq == None:
            return True

        diff_semitone = np.abs(np.log(1.0*freq/self.target_freq) / np.log(2) * 12)
        return diff_semitone < 2
    
    def target_detected_amp(self, db):
        print "db = ",db
        if db == 3:
            return False

        if db > 3:
            return True
        
        return False
        
    
class ToneDetectorForServerThread(ToneDetectorThread):
    def __init__(self, target_freq, callback, recordThread):
        super(ToneDetectorForServerThread, self).__init__(target_freq=target_freq, callback=callback)
        self.recordThread = recordThread

    def join(self, timeout=None):
        super(ToneDetectorForServerThread, self).join(timeout)

    def run(self):
        shared_vars = {
            "start_time": None,
            "last_event": None
        }

        def freq_cb(detected_tone, detected_amp_db):
            time_str = datetime.datetime.strftime(datetime.datetime.now(), ToneDetector.TIME_STR_FORMAT)
            freq = detected_tone
            amp = detected_amp_db

            thresh = 3 if self.target_freq else 1
            #if super(ToneDetectorForServerThread, self).target_detected(freq):
            if super(ToneDetectorForServerThread, self).target_detected_amp(amp):
                self.event_counter += 1
                if self.event_counter == 1:
                    shared_vars["start_time"] = time_str
                if self.event_counter == thresh:
                    if not shared_vars["last_event"] or shared_vars["last_event"] != ToneDetector.Event.TONE_DETECTED:
                        self.cb((shared_vars["start_time"], ToneDetector.Event.TONE_DETECTED))
                        shared_vars["last_event"] = ToneDetector.Event.TONE_DETECTED

            else:
                if self.event_counter > thresh:
                    shared_vars["start_time"] = None
                    if not shared_vars["last_event"] or shared_vars["last_event"] != ToneDetector.Event.TONE_MISSING:
                        self.cb((time_str, ToneDetector.Event.TONE_MISSING))
                        shared_vars["last_event"] = ToneDetector.Event.TONE_MISSING
                self.event_counter = 0

        #AudioFunction.start_record(cb=freq_cb)
        self.recordThread.setDetectCallback(cb = freq_cb)

        while not self.stoprequest.isSet():
            time.sleep(0.1)

        self.recordThread.stopRecord()            

class DetectionStateChangeListenerThread(threading.Thread):
    class Event(object):
        ACTIVE = "active"
        INACTIVE = "inactive"
        RISING_EDGE = "rising"
        FALLING_EDGE = "falling"

    def __init__(self):
        super(DetectionStateChangeListenerThread, self).__init__()
        self.daemon = True
        self.stoprequest = threading.Event()
        self.event_q = queue.Queue()
        self.current_event = None
        Logger.init()

    def reset(self):
        # reset function must consider the event handling:
        #   if the current state is not None, the active/inactive event might have been sent
        #   and such event should be sent again because it must be same with the case of None -> active
        #   so the active/inactive event needs to be sent again before setting the current state to None
        active_or_inactive = None
        if self.current_event:
            active_or_inactive = DetectionStateChangeListenerThread.Event.ACTIVE \
                            if self.current_event[1] == ToneDetector.Event.TONE_DETECTED else \
                                 DetectionStateChangeListenerThread.Event.INACTIVE
        self.current_event = None
        with self.event_q.mutex:
            self.event_q.queue.clear()

        if active_or_inactive:
            self.event_q.put((active_or_inactive, 0))

    def tone_detected_event_cb(self, event):
        Logger.log("DetectionStateChangeListenerThread", "tone_detected_event_cb: {}".format(event))
        self._handle_event(event)

    def _handle_event(self, event):
        active_or_inactive = DetectionStateChangeListenerThread.Event.ACTIVE \
                        if event[1] == ToneDetector.Event.TONE_DETECTED else \
                             DetectionStateChangeListenerThread.Event.INACTIVE

        self.event_q.put((active_or_inactive, 0))

        if self.current_event and self.current_event[1] != event[1]:
            rising_or_falling = DetectionStateChangeListenerThread.Event.RISING_EDGE \
                            if event[1] == ToneDetector.Event.TONE_DETECTED else \
                                DetectionStateChangeListenerThread.Event.FALLING_EDGE

            t2 = datetime.datetime.strptime(event[0], ToneDetector.TIME_STR_FORMAT)
            t1 = datetime.datetime.strptime(self.current_event[0], ToneDetector.TIME_STR_FORMAT)
            t_diff = t2 - t1
            self.event_q.put((rising_or_falling, t_diff.total_seconds()*1000.0))

        self.current_event = event

    def wait_for_event(self, event, timeout):
        cnt = 0
        while cnt < timeout*10:
            cnt += 1
            if self.stoprequest.isSet():
                return -1
            try:
                ev = self.event_q.get(timeout=0.1)
                Logger.log("DetectionStateChangeListenerThread", "get event: {}".format(ev))
                if ev[0] == event:
                    return ev[1]
            except queue.Empty:
                pass
        return -1

    def join(self, timeout=None):
        self.stoprequest.set()
        super(DetectionStateChangeListenerThread, self).join(timeout)

    def run(self):
        while self.stoprequest.isSet():
            time.sleep(0.1)

            
class RecordThread(threading.Thread):
    def __init__(self, callback = None):
        super(RecordThread, self).__init__()
        self.stoprequest = threading.Event()
        self.is_detecting = False
        self.nfft = 2048
        self.ch = 1
        self.sr = 16000
        self.fs = 50
        self.cb = callback
        self.isrun = False

    def join(self, timeout=None):
        self.isrun = False
        self.stoprequest.set()
        self.stopRecord()
        super(RecordThread, self).join(timeout)

    def run(self):
        self.is_detecting = True
        self.isrun = True
        while not self.stoprequest.isSet():
            if self.is_detecting is False:
                continue
            self._record()
            
    def stopRecord(self):
        self.is_detecting = False

    def restartRecord(self):
        self.is_detecting = True
    
    def setDetectCallback(self, cb):
        self.cb = cb

    def _record(self):
        buff = np.array([])
        framesize = int(self.sr * self.fs / 1000)

        # Make the code adaptive to both python 2 and 3
        shared_vars = {
            "buff"     : buff,
            "framesize": framesize,
            "callback" : self.cb
        }
        
        def record_cb(indata, frames, time, status):
            buff = shared_vars["buff"]
            framesize = shared_vars["framesize"]
            cb = shared_vars["callback"]

            if buff.any():
                buff = np.vstack((buff, indata[:, :]))
            else:
                buff = np.array(indata[:, :])

            if buff.size >= framesize:
                spectrum = np.abs(fft(buff[:framesize, 0], self.nfft))
                spectrum = spectrum[:int(self.nfft/2.0)]
                max_idx = np.argmax(spectrum)
                unit_freq = 1.0 * self.sr / self.nfft

                if cb:
                    cb(detected_tone = max_idx * unit_freq, detected_amp_db = 20 * np.log10(spectrum[max_idx]))

                buff = buff[framesize:, :]

            shared_vars["buff"] = buff
            shared_vars["framesize"] = framesize

        with sd.InputStream(channels = self.ch, callback = record_cb, samplerate = self.sr, dtype = "float32"):
            while self.is_detecting:
                sd.sleep(500)
                
        
class PlaybackThread(threading.Thread):
    def __init__(self):
        super(PlaybackThread, self).__init__()
        self.stoprequest = threading.Event()
        self.is_playing = False
        self.is_stoping = False
        self.nfft = 2048
        self.ch = 1
        self.sr = 16000
        self.fss = 50
        self.isrun = False
    
    def join(self, timeout=None):
        self.isrun = False
        self.stoprequest.set()
        self.stopPlayback()
        super(PlaybackThread, self).join(timeout)
        
    def run(self):
        self.isrun = True
        self.is_playing = True
        data, fs = sf.read("../audiofiles/madmoo.wav", dtype='float32')
        while not self.stoprequest.isSet():
            if self.is_playing is False:
                if self.is_stoping is False:
                    sd.stop()
                    self.is_stoping = True
                continue
            sd.play(data, fs, blocking = False)
            self.is_stoping = False
            sd.sleep(1000)

        '''
        while not self.stoprequest.isSet():
            if self.is_playing is False:
                continue
            self._playback()
        '''

        time.sleep(1)
        
    def stopPlayback(self):
        self.is_playing = False

    def restartPlayback(self):
        self.is_playing = True
                
    def _playback(self):
        phase_offset = 0

        # Make the code adaptive to both python 2 and 3
        shared_vars = {
            "phase_offset": phase_offset,
            "data": self.data
        }
        
        def playback_cb(outdata, frames, time, status):
            phase_offset = shared_vars["phase_offset"]
            data = shared_vars["data"]
            
            signal = np.arange(outdata.shape[0])
            signal = signal * 2 * np.pi / self.sr + phase_offset
            phase_offset += outdata.shape[0] * 2 * np.pi / self.sr
            signal = 0.99 * np.sin(signal * 440)

            for cidx in range(outdata.shape[1]):
                outdata[:, cidx] = data[cidx]
                #outdata[:, cidx] = signal

            shared_vars["phase_offset"] = phase_offset

        with sd.OutputStream(channels = self.ch, callback = playback_cb, samplerate = self.sr, dtype = "float32"):
            while self.is_playing:
                sd.sleep(500)


if __name__ == "__main__":
    serialno1 = str(sys.argv[1]) if len(sys.argv) > 1 else None
    serialno2 = str(sys.argv[2]) if len(sys.argv) > 1 else None
    num_iter = int(sys.argv[3]) if len(sys.argv) > 1 else 1
    
    # ViewClient tries to access the system arguments, then it might cause RuntimeError
    if len(sys.argv) > 1: del sys.argv[1:]
    try:
        run(num_iter=num_iter, serialno1=serialno1, serialno2=serialno2)
    except Exception as e:
        print(e)
