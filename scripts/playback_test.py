import os
import subprocess
import time
import datetime
import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from com.dtmilano.android.viewclient import ViewClient
from com.dtmilano.android.viewclient import UiScrollable
from libs import ROOT_DIR, STDNUL
from libs.adbutils import Adb
from libs.audiofunction import AudioFunction, ToneDetector, DetectionStateChangeListenerThread
from libs.logger import Logger
from libs.aatapp import AATApp
from libs.trials import Trial, TrialHelper

TAG = "playback_test.py"

DEVICE_MUSIC_DIR = "sdcard/Music/"
OUT_FREQ = 440
BATCH_SIZE = 1
PARTIAL_RAMDUMP_ENABLED = False

FILE_NAMES = [
    "440Hz.wav",
    "440Hz.mp3",
    "1100_3100_tone.wav",
    "1100_3100_tone.mp3",
    "1150_3150_tone.wav",
    "1150_3150_tone.mp3",
    "1k_Stereo_48k_16bits_aac.aac",
    "1k_Stereo_48k_16bits_wav.wav",
    "1k_Stereo_96k_24bits_flac.flac"
]

REPORT_DIR = "report"

# ... modified push file by self
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
            device.unlock()
    except:
        pass


def run(num_iter=1):
    # initail componet
    AudioFunction.init()
    Logger.init(Logger.Mode.BOTH_FILE_AND_STDOUT)
    Adb.init()

    os.system("mkdir -p {}/{} > {}".format(ROOT_DIR, REPORT_DIR, STDNUL))  # windows need modified
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
        #trials_batch += playback_task_run(device, num_iter=min([num_iter, BATCH_SIZE]))
        #trials_batch += playback_format_task_run(device, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += playback_GoogleMusic_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))

        map(lambda trial: trial.put_extra(name="batch_id", value=batch_count), trials_batch)
        trials += trials_batch
        with open("{}/{}/{}".format(ROOT_DIR, REPORT_DIR, filename), "w") as f:
            f.write(TrialHelper.to_json(trials))

        num_iter -= BATCH_SIZE
        batch_count += 1

    AudioFunction.finalize()
    Logger.finalize()

def playback_task_run(device, num_iter=1):
    log("playback_task_run++")

    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity     
    
    trials = []
    
    device.startActivity(component=component)
    
    th = DetectionStateChangeListenerThread()
    th.start()

    funcs = {
        "nonoffload": AATApp.playback_nonoffload,
        "offload"   : AATApp.playback_offload
    }
    
    formats = {
        "440Hz": 440
    }

    # force stop app string
    cmd = " ".join(["am", "force-stop", package])
    
    for i in range(num_iter):
        log("-------- playback_task #{} --------".format(i+1))
        for name, func in funcs.items():
            log("dev_playback_{}_start".format(name))
            
            for file, freq in formats.items():
                if name == "nonoffload":
                    log(file + ".wav")
                    filename = file + ".wav"
                else:
                    log(file + ".mp3")
                    filename = file + ".mp3"
                
                trial = Trial(taskname="playback_{}_{}".format(name, file))
                trial.put_extra(name="iter_id", value=i+1)
            
                log("playback_file_{}".format(file))
                
                log("ToneDetector.start_listen(target_freq={})".format(freq))
                ToneDetector.start_listen(target_freq=freq, cb=lambda event: th.tone_detected_event_cb(event))  
                
                time.sleep(1)
                th.reset()
                log("reset DetectionStateChangeListener")
                
                func(device, filename)

                log("-> playback start function:")
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="start play fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback start function: pass")
                    trial.put_extra(name="playback start", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                
                time.sleep(0.5)

                
                log("-> playback pause function:")
                th.reset()
                
                AATApp.playback_pause_resume(device)
                #time.sleep(1)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="pause fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback pause function: pass")
                    trial.put_extra(name="playback pause", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback pause", value="pop")
                    
                time.sleep(1)

                log("-> playback resume function:")
                th.reset()
                AATApp.playback_pause_resume(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="resume fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback resume: pass")
                    trial.put_extra(name="playback resume", value="pass")

                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback resume", value="pop")
                    
                time.sleep(1)

                log("-> playback seek function:")
                th.reset()
                AATApp.playback_seek(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="seek fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback seek: pass")
                    trial.put_extra(name="playback seek", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback seek", value="pop")
                    
                time.sleep(2)

                log("-> playback forward function:")
                th.reset()
                AATApp.playback_forward(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="forward fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback forward function: pass")
                    trial.put_extra(name="playback forward", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback forward", value="pop")
                    
                time.sleep(2)

                th.reset()
                AATApp.playback_stop(device)
                log("dev_playback_stop")

                elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5)
                
                trial.put_extra(name="elapsed", value=elapsed)
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback stop", value="pop")
                
                trials.append(trial)

    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()
    device.shell(cmd)
    
    log("playback_task_run--")
    return trials

def playback_format_task_run(device, num_iter=1):
    log("playback_format_task_run++")

    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity     
    
    trials = []
    
    device.startActivity(component=component)
    
    th = DetectionStateChangeListenerThread()
    th.start()

    funcs = {
        "nonoffload": AATApp.playback_nonoffload
    }
    
    formats = {
        "1k_Stereo_48k_16bits_aac.aac": 1000,
        "1k_Stereo_48k_16bits_wav.wav": 1000,
        "1k_Stereo_96k_24bits_flac.flac": 1000
    }

    # force stop app string
    cmd = " ".join(["am", "force-stop", package])
    
    for i in range(num_iter):
        log("-------- playback_format_task #{} --------".format(i+1))
        for name, func in funcs.items():
            log("dev_playback_{}_start".format(name))
            
            for file, freq in formats.items():
                
                trial = Trial(taskname="playback_{}_{}".format(name, file))
                trial.put_extra(name="iter_id", value=i+1)
            
                log("playback_file_{}".format(file))
                
                log("ToneDetector.start_listen(target_freq={})".format(freq))
                ToneDetector.start_listen(target_freq=freq, cb=lambda event: th.tone_detected_event_cb(event))  
                
                time.sleep(1)
                th.reset()
                log("reset DetectionStateChangeListener")
                
                func(device, file)

                log("-> playback start function:")
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="start play fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback start function: pass")
                    trial.put_extra(name="playback start", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                    
                time.sleep(0.5)

                log("-> playback pause function:")
                th.reset()
                
                AATApp.playback_pause_resume(device)
                #time.sleep(1)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="pause fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback pause function: pass")
                    trial.put_extra(name="playback pause", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                    
                time.sleep(1)

                log("-> playback resume function:")
                th.reset()
                AATApp.playback_pause_resume(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="resume fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback resume: pass")
                    trial.put_extra(name="playback resume", value="pass")

                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                    
                time.sleep(1)

                log("-> playback seek function:")
                th.reset()
                AATApp.playback_seek(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="seek fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback seek: pass")
                    trial.put_extra(name="playback seek", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                    
                time.sleep(2)

                log("-> playback forward function:")
                th.reset()
                AATApp.playback_forward(device)
                if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
                    log("the tone was not detected, abort the iteration this time...")
                    AATApp.playback_stop(device)
                    trial.invalidate(errormsg="forward fail")
                    trials.append(trial)
                    continue
                else:
                    log("-> playback forward function: pass")
                    trial.put_extra(name="playback forward", value="pass")
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                time.sleep(2)

                th.reset()
                AATApp.playback_stop(device)
                log("dev_playback_stop")

                elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5)
                
                trial.put_extra(name="elapsed", value=elapsed)
                
                pop = AudioFunction.get_pop()
                if pop:
                    log("pop detect")
                    trial.put_extra(name="playback start", value="pop")
                    
                trials.append(trial)

    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()
    device.shell(cmd)
    
    log("playback_task_run--")
    return trials

def playback_GoogleMusic_run(device, serialno, num_iter=1):
    # Google Music
    # play
    # pause
    # resume
    # seek
    # forward
    log("GoogleMusic playback++")
    
    packageGM = "com.google.android.music"
    activityGM = "com.android.music.activitymanagement.TopLevelActivity"
    componentGM = packageGM + "/" + activityGM
    
    cmd = " ".join(["am", "force-stop", packageGM])
    
    freq = 440
    
    trials = []
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    for i in range(num_iter):
        trial = Trial(taskname="GoogleMusic playback")
        trial.put_extra(name="iter_id", value=i+1)

        # start google music
        device.wake() 
        time.sleep(1)
        device.startActivity(componentGM)
        log("-> GoogleMusic start")

        # into Music list
        log("-> GoogleMusic into Music list")
        vc, key = get_MusicList_id(device, serialno)
        if vc is None:
            log("can't find Music list")
            trial.invalidate(errormsg="can't find Music list")
            trials.append(trial)
            device.shell(cmd)
            continue

        log("find the Music list")
        control_Btn(vc, key)    

        # find 440Hz in list
        log("-> GoogleMusic find 440Hz in list")
        vc = ViewClient(device, serialno)
        view = get_fragment_list_view(device, serialno)
        uis = UiScrollable(view)

        for i in range(3):
            vc, key = get_File_id(device, serialno)
            if key is None:
                log("scroll")
                uis.flingForward()
                continue
            else:
                control_Btn(vc, key)
                break;

        # into art pager interface
        log("-> GoogleMusic into art pager")
        vc, key = get_ArtPager_id(device, serialno)
        if vc is None:
            log("can't find Art Pager")
            trial.invalidate(errormsg="GoogleMusic can't find Art Pager")
            trials.append(trial)
            device.shell(cmd)
            continue

        log("find the Art Pager")
        control_Btn(vc, key)  

        log("ToneDetector.start_listen(target_freq={})".format(freq))
        ToneDetector.start_listen(target_freq=freq, cb=lambda event: th.tone_detected_event_cb(event))

        th.reset()

        # the music already start, so detect it...
        log("-> GoogleMusic start function:")
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")

            trial.invalidate(errormsg="GoogleMusic start play fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GoogleMusic start function: pass")
            trial.put_extra(name="GoogleMusic start", value="pass")    

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
                    
        # pause
        log("-> GoogleMusic pause function:")
        vc, key = get_play_pause_id(device, serialno)
        if vc is None:
            log("can't find pause btn")
            trial.invalidate(errormsg="can't find pause btn")
            trials.append(trial)
            device.shell(cmd)
            continue

        log("find the pause btn")
        control_Btn(vc, key)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.FALLING_EDGE, timeout=5) < 0:
            log("the tone was not pause...")

            trial.invalidate(errormsg="GoogleMusic pause fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GoogleMusic pause function: pass")
            trial.put_extra(name="GoogleMusic pause", value="pass")

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
            
        # resume
        log("-> GoogleMusic resume function:")
        vc, key = get_play_pause_id(device, serialno)
        if vc is None:
            log("can't find resume btn")
            trial.invalidate(errormsg="can't find resume btn")
            trials.append(trial)
            device.shell(cmd)
            continue

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
            
        log("find the resume btn")
        control_Btn(vc, key)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not resume...")

            trial.invalidate(errormsg="GoogleMusic resume fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GoogleMusic resume function: pass")
            trial.put_extra(name="GoogleMusic resume", value="pass")

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
        
        time.sleep(1)
        
        # seek
        log("-> GoogleMusic seek function:")
        vc, key = get_progress_id(device, serialno)
        if vc is None:
            log("can't find seek btn")
            trial.invalidate(errormsg="can't find seek btn")
            trials.append(trial)
            device.shell(cmd)
            continue

        log("find the seek btn")
        control_Btn(vc, key)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("seek fail...")

            trial.invalidate(errormsg="GoogleMusic seek fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GoogleMusic seek function: pass")
            trial.put_extra(name="GoogleMusic seek", value="pass")

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
        
        time.sleep(1)
        
        # next
        log("-> GoogleMusic next function:")
        vc, key = get_next_id(device, serialno)
        if vc is None:
            log("can't find next btn")
            trial.invalidate(errormsg="can't find next btn")
            trials.append(trial)
            device.shell(cmd)
            continue

        log("find the next btn")
        control_Btn(vc, key)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("next fail...")

            trial.invalidate(errormsg="GoogleMusic next fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GoogleMusic next function: pass")
            trial.put_extra(name="GoogleMusic next", value="pass")

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
        
        time.sleep(1)
        
        # pause
        log("-> GoogleMusic pause function:")
        vc, key = get_play_pause_id(device, serialno)
        if vc is None:
            log("can't find pause btn")
            trial.invalidate(errormsg="can't find pause btn")
            trials.append(trial)
            device.shell(cmd)
            continue

        log("find the pause btn")
        control_Btn(vc, key)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.FALLING_EDGE, timeout=5) < 0:
            log("pause fail...")

            trial.invalidate(errormsg="GoogleMusic pause fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GoogleMusic pause function: pass")
            trial.put_extra(name="GoogleMusic pause", value="pass")    

        pop = AudioFunction.get_pop()
        if pop:
            log("pop detect")
            trial.put_extra(name="playback start", value="pop")
        
        time.sleep(1)
        
        device.shell(cmd)
        
    time.sleep(2)
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    
    device.shell(cmd)
    th.join()
    
    log("GoogleMusic playback--")
    return trials

def get_MusicList_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=Music") > 0:
            return vc, key
    return None, None

def get_fragment_list_view(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/fragment_list") > 0:
            view = vc.findViewByIdOrRaise(key)
            return view
    return None

def get_File_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=440Hz ") > 0:
            return vc, key
    return None, None

def get_ArtPager_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/art_pager") > 0:
            return vc, key
    return None

def get_progress_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/progress") > 0:
            return vc, key
    return None, None


def get_next_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/next") > 0:
            return vc, key
    return None, None

def get_play_pause_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/play_controls") > 0:
            return vc, key
    return None, None

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
    

if __name__ == "__main__":
    num_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    # ViewClient tries to access the system arguments, then it might cause RuntimeError
    if len(sys.argv) > 1: del sys.argv[1:]
    try:
        run(num_iter=num_iter)
    except Exception as e:
        print(e)
