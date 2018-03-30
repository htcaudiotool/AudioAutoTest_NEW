from com.dtmilano.android.viewclient import ViewClient
from com.dtmilano.android.viewclient import UiScrollable
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

from libs.popsounddetectthread import PopSoundDetecter

import matplotlib.pyplot as pl  
import matplotlib 
import numpy as np

TAG = "TestPlayback.py"

DEVICE_MUSIC_DIR = "sdcard/Music/"
OUT_FREQ = 440
BATCH_SIZE = 5
PARTIAL_RAMDUMP_ENABLED = True

FILE_NAMES = [
    "440Hz.wav",
    "440Hz.mp3",
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

def run(num_iter=1):
    # initail componet
    AudioFunction.init()
    Logger.init(Logger.Mode.BOTH_FILE_AND_STDOUT)
    Adb.init()

    os.system("mkdir -p {}/ssr_report > /dev/null".format(ROOT_DIR))
    t = datetime.datetime.now()
    filename = "report_{}{:02d}{:02d}_{:02d}{:02d}{:02d}.json".format(t.year, t.month, t.day, t.hour, t.minute, t.second)

    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity
    
    

    device, serialno = ViewClient.connectToDeviceOrExit(serialno=None)
    wake_device(device, serialno)
    #push_files_if_needed(serialno)
    
    # keymap reference:
    #   https://github.com/dtmilano/AndroidViewClient/blob/master/src/com/dtmilano/android/adb/androidkeymap.py
    
    device.press("HOME")
    #time.sleep(1)
    #push_files_if_needed(serialno)
    time.sleep(1)
    
    #device.startActivity(component=component)
    #time.sleep(1)

    for i in range(1):
        #swith_effect_ui(device, serialno)
        #device.press("HOME")
        playback_task_run(device, num_iter=num_iter)
        #AATApp.playback_nonoffload(device, "pop.wav")
        #time.sleep(5)
        #device.press("HOME")
        #playback_task2_run(device, num_iter=num_iter)
        #device.press("HOME")
        #control_GoogleMusic(device, serialno, num_iter=num_iter)

    AudioFunction.finalize()
    Logger.finalize()

def playback_task_run(device, num_iter=1):
    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity
    
    # force stop app string
    cmd = " ".join(["am", "force-stop", package])
    
    log("playback_task_run++")
    device.startActivity(component=component)
    time.sleep(1)
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    
    funcs = {
        "nonoffload": AATApp.playback_nonoffload,
        #"offload"   : AATApp.playback_offload
    }


    for i in range(num_iter):
        log("-------- playback_task #{} --------".format(i+1))
        for name, func in funcs.items():                
            func(device, "pop.wav")
            time.sleep(1)
            log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
            ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))
            log("dev_playback_{}_start".format(name))
            th.reset()
            log("reset DetectionStateChangeListener")
            
            
            

            log("-> playback start:")
            '''
            if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=1) < 0:
                log("the tone was not detected, abort the iteration this time...")
                AATApp.playback_stop(device)
                continue
            else:
                log("-> playback start: pass")
            '''    
            pop = AudioFunction.get_pop()
            if pop:
                log("pop detect")
            else:
                log("no pop")
            
            time.sleep(4)
            
            pop = AudioFunction.get_pop()
            if pop:
                log("pop detect")
            else:
                log("no pop")
            
            log("dev_playback_stop")
            th.reset()
            AATApp.playback_stop(device)
            time.sleep(2)

            #th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=1)

            log("stoping")

    log("-------- playback_task done --------")
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()
    AATApp.playback_stop(device)
    device.shell(cmd)
    
    log("playback_task_run--")
    return

def playback_task2_run(device, num_iter=1):
    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity
    
    log("playback_task2_run++")
    device.startActivity(component=component)
    
    th = DetectionStateChangeListenerThread()
    th.start()

    log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))
    
    funcs = {
        "nonoffload": AATApp.playback_nonoffload,
    }
    
    formats = {
        "1k_Stereo_48k_16bits_aac.aac": 1000,
        "1k_Stereo_48k_16bits_wav.wav": 1000,
        "1k_Stereo_96k_24bits_flac.flac": 1000
    }
    
    freqss = {
        440, 1100, 1150
    }

    for i in range(num_iter):
        log("-------- playback_task2 #{} --------".format(i+1))
        for name, func in funcs.items():
            log("dev_playback_{}_start".format(name))
            
            for file, freq in formats.items():
                    
                log("ToneDetector.start_listen(target_freq={})".format(freq))
                ToneDetector.start_listen(target_freq=freq, cb=lambda event: th.tone_detected_event_cb(event))  
                
                log("dev_playback_{}_start".format(name))
                time.sleep(2)
                th.reset()
                log("reset DetectionStateChangeListener")
                func(device, file)

                log("-> playback start:")
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    continue
                else:
                    log("-> playback start: pass")
                time.sleep(2)

                '''
                log("-> playback pause:")
                th.reset()
                AATApp.playback_pause_resume(device)
                time.sleep(1)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    continue
                else:
                    log("-> playback pause: pass")
                time.sleep(1)

                log("-> playback resume:")
                th.reset()
                AATApp.playback_pause_resume(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    continue
                else:
                    log("-> playback resume: pass")
                time.sleep(1)
                '''

                log("-> playback seek:")
                th.reset()
                AATApp.playback_seek(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    continue
                else:
                    log("-> playback seek: pass")
                time.sleep(2)

                log("-> playback forward:")
                th.reset()
                AATApp.playback_forward(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    continue
                else:
                    log("-> playback forward: pass")
                time.sleep(2)

                log("dev_playback_stop")
                th.reset()
                AATApp.playback_stop(device)
                log("stoping->>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
                th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=3)

                log("stoping")
                #time.sleep(1)

    log("-------- playback_task2 done --------")
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    log("playback_task2_run--")
    return 

def control_GoogleMusic(device, serialno, num_iter=1):
    # Google Music
    # play
    # pause
    # resume
    # seek
    # forward
    # offload/non-offload
    log("GoogleMusic playback++")
    
    packageGM = "com.google.android.music"
    activityGM = "com.android.music.activitymanagement.TopLevelActivity"
    componentGM = packageGM + "/" + activityGM
    cmd = " ".join(["am", "force-stop", packageGM])
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))
    
    device.wake() 
    log("wake")
    time.sleep(1)
    device.startActivity(componentGM)
    log("startActivity")
    time.sleep(5)
    device.touch(700, 1100)
    log("into tool bar 1")
    time.sleep(2)
    device.touch(700, 2500)   # into tool bar
    log("into tool bar 2")
    time.sleep(2)
    
    #-------------------------------------------
    th.reset()
        
    device.touch(720, 2400)   # play
    log("play1")
    
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not detected...")
        device.shell(cmd)
        return        
	
    time.sleep(2)
    
    device.touch(720, 2400)   # pause
    log("pause")
    
    elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
    if elapsed < 0:
        log("the tone was not pause...")
        device.shell(cmd)
        return
        
    time.sleep(2)
    
    device.touch(720, 2400)   # play
    log("play2")
    
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not resume...")
        device.shell(cmd)
        return 
        
    time.sleep(5)
    
    device.touch(30, 2200)    # seek-1
    log("seek-1")
    
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not seek-1...")
        device.shell(cmd)
        return
        
    time.sleep(5)
    
    device.touch(1000, 2200)  # seek-1
    log("seek-2")
    
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not seek-1...")
        device.shell(cmd)
        return
        
    time.sleep(5)
    
    device.touch(1000, 2400)  # next
    log("next")
    
    if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
        log("the tone was not next...")
        device.shell(cmd)
        return
        
    time.sleep(5)
    
    device.touch(720, 2400)   # stop
    log("stop")
    
    elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)
    if elapsed < 0:
        log("the tone was not stop...")
        device.shell(cmd)
        return
        
    time.sleep(5)
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    
    device.shell(cmd)
    log("complete playback task")
    th.join()
    #th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) 
    #elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.RISING_EDGE, timeout=10)

def get_boomsound_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=HTC BoomSound") > 0:
            return vc, key
    return None, None
    
def control_Btn(vc, key):
    if key == None:
        log("control Btn -> key is None")
        return False
    btn = vc.findViewByIdOrRaise(key)
    btn.touch()
    return True

def swith_effect_ui(device, serialno):
    log("switch effect")
    
    # open setting #cmp=com.android.settings/.Settings
    packageGM = "com.android.settings"
    activityGM = ".Settings"
    componentGM = packageGM + "/" + activityGM
    cmd = " ".join(["am", "force-stop", packageGM])
    
    device.wake() 
    log("wake")
    time.sleep(1)
    device.startActivity(componentGM)
    
    vc = ViewClient(device, serialno)
    vv = vc.findViewByIdOrRaise("id/no_id/1")
    uis = UiScrollable(vv)
    uis.flingBackward()
    uis.flingBackward()
    uis.flingBackward()
    for i in range(3):
        
        vc, key = get_boomsound_id(device, serialno)
        if key is None:
            log("scroll")
            uis.flingForward()
            continue
        else:
            break;
    
    vc, key = get_boomsound_id(device, serialno)
    if vc is not None:
        log("find the boomsound")
        control_Btn(vc, key)
    # get vc
    # get view id/dashboard_container
    # get uiscroll
    # scroll 3 time or find boomsound
    # click boomsound
    # finish
    

if __name__ == "__main__":
    num_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    # ViewClient tries to access the system arguments, then it might cause RuntimeError
    if len(sys.argv) > 1: del sys.argv[1:]
    try:
        run(num_iter=num_iter)
    except Exception as e:
        print(e)
