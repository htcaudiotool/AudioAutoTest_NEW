import os
import subprocess
import time
import datetime
import sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from com.dtmilano.android.viewclient import ViewClient
from libs import ROOT_DIR
from libs.adbutils import Adb
from libs.audiofunction import AudioFunction, ToneDetector, DetectionStateChangeListenerThread
from libs.logger import Logger
from libs.aatapp import AATApp
from libs.trials import Trial, TrialHelper

TAG = "video_test.py"

OUT_FREQ = 1000
BATCH_SIZE = 1
PARTIAL_RAMDUMP_ENABLED = False

REPORT_DIR = "report"

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

    os.system("mkdir -p {}/{} > /dev/null".format(ROOT_DIR, REPORT_DIR))  # windows need modified
    t = datetime.datetime.now()
    filename = "report_{}{:02d}{:02d}_{:02d}{:02d}{:02d}.json".format(t.year, t.month, t.day, t.hour, t.minute, t.second)

    device, serialno = ViewClient.connectToDeviceOrExit(serialno=None)
    wake_device(device, serialno)

    # keymap reference:
    #   https://github.com/dtmilano/AndroidViewClient/blob/master/src/com/dtmilano/android/adb/androidkeymap.py
    device.press("HOME")
    time.sleep(0.5)
    
    time.sleep(1)

    trials = []
    batch_count = 1
    while num_iter > 0:
        log("-------- batch_run #{} --------".format(batch_count))
        trials_batch = []
        trials_batch += video_task_run(device, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += video_GooglePhoto_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))

        map(lambda trial: trial.put_extra(name="batch_id", value=batch_count), trials_batch)
        trials += trials_batch
        with open("{}/{}/{}".format(ROOT_DIR, REPORT_DIR, filename), "w") as f:
            f.write(TrialHelper.to_json(trials))

        num_iter -= BATCH_SIZE
        batch_count += 1

    AudioFunction.finalize()
    Logger.finalize()

def video_task_run(device, num_iter = 1):
    log("video_task_run++")
    
    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity
    
    trials = []
    
    freq = 1000
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
    ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))
    
    # force stop app string
    cmd = " ".join(["am", "force-stop", package])
    
    for i in range(num_iter):
        log("-------- video_task #{} --------".format(i+1))
        
        trial = Trial(taskname="video")
        trial.put_extra(name="iter_id", value=i+1)
                
        log("ToneDetector.start_listen(target_freq={})".format(freq))
        ToneDetector.start_listen(target_freq=freq, cb=lambda event: th.tone_detected_event_cb(event))  
                
        device.startActivity(component = component)
        time.sleep(1)
        
        th.reset()
        log("reset DetectionStateChangeListener")        
        
        # video start
        log("-> video start function:")
        AATApp.video_start(device)
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video start play fail")
            trials.append(trial)
            continue
        else:
            log("-> video start function: pass")
            trial.put_extra(name="video start", value="pass")
            
        th.reset()
        time.sleep(2)
        
        # video seek
        log("-> video seek:")
        AATApp.video_seek(device)
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video seek fail")
            trials.append(trial)
            continue
        else:
            log("-> video seek function: pass")
            trial.put_extra(name="video seek", value="pass")
            
        th.reset()
        time.sleep(2)

        # video rorate
        log("-> video rotate:")
        AATApp.video_rotate(device)
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video rorate fail")
            trials.append(trial)
            continue
        else:
            log("-> video rorate function: pass")
            trial.put_extra(name="video rorate", value="pass")
            
        th.reset()
        time.sleep(1)
        AATApp.video_rotate(device)
        time.sleep(2)
        
        # video pause
        log("-> video pause:")
        AATApp.video_pause_resume(device)
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video pause fail")
            trials.append(trial)
            continue
        else:
            log("-> video pause: pass")
            trial.put_extra(name="video pause", value="pass")
            
        th.reset()
        time.sleep(2)
        
        # video resume
        log("-> video resume:")
        AATApp.video_pause_resume(device)
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video pause fail")
            trials.append(trial)
            continue
        else:
            log("-> video resume: pass")
            trial.put_extra(name="video resume", value="pass")
            
        time.sleep(2)
        
        # video home
        device.press("HOME")        
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video HOME fail")
            trials.append(trial)
            continue
        else:
            log("-> video home: pass")
            trial.put_extra(name="video HOME", value="pass")
            
        time.sleep(2)
        
        # video stop
        log("dev_video_stop")
        AATApp.video_stop(device)
        if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
            log("the tone was not detected, abort the iteration this time...")
            AATApp.video_stop(device)
            trial.invalidate(errormsg="video stop fail")
            trials.append(trial)
            continue
        else:
            log("-> video stop: pass")
            trial.put_extra(name="video stop", value="pass")
            
        device.press("HOME")

    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()
    device.shell(cmd)

    log("video_task_run--")
    return trials

def get_Video_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("content-desc=Video") > 0:
            return vc, key
    return None, None

def get_pause_resume_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/main_container") > 0:
            return vc, key
    return None, None
# play stop
 
def control_Btn(vc, key):
    #vc = ViewClient(device, serialno)
    if key == None:
        log("control Btn -> key is None")
        return False
    btn = vc.findViewByIdOrRaise(key)
    btn.touch()
    return True
    
def video_GooglePhoto_run(device, serialno, num_iter=1):
    log("GooglePhoto video_task_run++")
        
    packageGP = "com.google.android.apps.photos"
    activityGP = ".home.HomeActivity"
    componentGP = packageGP + "/" + activityGP
    
    cmd = " ".join(["am", "force-stop", packageGP])
    
    
    freq = 1000
    
    trials = []
    
    th = DetectionStateChangeListenerThread()
    th.start()
    
    #-------------------------------------------
    for i in range(num_iter):
        log("-------- GooglePhoto video_task #{} --------".format(i+1))
        trial = Trial(taskname="GooglePhoto video")
        trial.put_extra(name="iter_id", value=i+1)
        
        device.wake() 
        time.sleep(1)
        device.startActivity(componentGP)
        time.sleep(1)
    
        th.reset()
        
        # video start
        log("-> GooglePhoto start function:")
        vc, key = get_Video_id(device, serialno)
        control_Btn(vc, key)

        time.sleep(1)
        
        log("ToneDetector.start_listen(target_freq={})".format(OUT_FREQ))
        ToneDetector.start_listen(target_freq=OUT_FREQ, cb=lambda event: th.tone_detected_event_cb(event))

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=8) < 0:
            log("the tone was not detected, abort the iteration this time...")
            trial.invalidate(errormsg="GooglePhoto start play fail")
            trials.append(trial)
            device.shell(cmd)
            continue   
        else:
            log("-> GooglePhoto start function: pass")
            trial.put_extra(name="GooglePhoto start", value="pass") 
        
        # video pause
        log("-> GooglePhoto video pause:")
        vc, key = get_pause_resume_id(device, serialno)
        control_Btn(vc, key)
        control_Btn(vc, key)

        time.sleep(1)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5) < 0:
            log("the tone was not pause...")
            trial.invalidate(errormsg="GooglePhoto pause fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GooglePhoto pause function: pass")
            trial.put_extra(name="GooglePhoto pause", value="pass") 

        time.sleep(1)
        
        # video resume
        log("-> GooglePhoto video resume:")
        vc, key = get_pause_resume_id(device, serialno)
        control_Btn(vc, key)

        if th.wait_for_event(DetectionStateChangeListenerThread.Event.ACTIVE, timeout=5) < 0:
            log("the tone was not resume...")
            trial.invalidate(errormsg="GooglePhoto resume fail")
            trials.append(trial)
            device.shell(cmd)
            continue 
        else:
            log("-> GooglePhoto start function: pass")
            trial.put_extra(name="GooglePhoto start", value="pass") 
        time.sleep(2)

        # video HOME press
        log("-> GooglePhoto video home:")
        device.press("HOME")

        elapsed = th.wait_for_event(DetectionStateChangeListenerThread.Event.INACTIVE, timeout=5)
        if elapsed < 0:
            log("the tone was not stop...")
            trial.invalidate(errormsg="GooglePhoto HOME fail")
            trials.append(trial)
            device.shell(cmd)
            continue
        else:
            log("-> GooglePhoto HOME function: pass")
            trial.put_extra(name="GooglePhoto HOME", value="pass") 

        time.sleep(1)
        device.press("BACK")    
        device.shell(cmd)
        
        
    time.sleep(2)
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    device.shell(cmd)
    th.join()
    
    log("GooglePhoto video_task_run--")
    return trials

if __name__ == "__main__":
    num_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    # ViewClient tries to access the system arguments, then it might cause RuntimeError
    if len(sys.argv) > 1: del sys.argv[1:]
    try:
        run(num_iter=num_iter)
    except Exception as e:
        print(e)
