#encoding: utf-8
import os
import subprocess
import time
import datetime
import binascii as bs
import numpy as np
import soundfile as sf
import sys
import platform
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

from com.dtmilano.android.viewclient import ViewClient
from scipy.fftpack import fft
from libs import ROOT_DIR
from libs.adbutils import Adb
from libs.audiofunction import AudioFunction, ToneDetector, DetectionStateChangeListenerThread
from libs.logger import Logger
from libs.aatapp import AATApp
from libs.trials import Trial, TrialHelper


file_path = "/sdcard/Music/recordHD0.flac"
file_name = "recordHD0.flac"
voice_path_2 = "/storage/self/primary/My\ Documents/My\ Recordings/VRecordHD.flac"
voice_path_1 = '/storage/self/primary/"My Documents/My Recordings"/VRecordHD.flac'
voice_name = "VRecordHD.flac"

TAG = "record_test.py"

PLATFORM = platform.system()
LINUX = 'Linux'
WINDOWS = 'Windows'
OUT_FREQ = 440
BATCH_SIZE = 1
REPORT_DIR = "report"

		
def log(msg):
    Logger.log(TAG, msg)

def pull_files(serialno, filepath):
    #out, _ = Adb.execute(cmd=["shell", "ls", DEVICE_MUSIC_DIR], serialno=serialno)
	
	#out, _ = subprocess.Popen(["find", ROOT_DIR, "-name", file_to_pushed], stdout=subprocess.PIPE).communicate()
    log("adb -s {} pull {} {} ".format(serialno, filepath, ROOT_DIR))
    if PLATFORM == WINDOWS:
        os.system("adb -s {} pull {} {} ".format(serialno, filepath, ROOT_DIR+"\\scripts\\"))
    elif PLATFORM == LINUX:
        os.system("adb -s {} pull {} {} ".format(serialno, filepath, ROOT_DIR+"/scripts/"))

def delete_file(serialno, name, device_path):
    if PLATFORM == WINDOWS:
        os.system("del {} ".format(ROOT_DIR + "\\scripts\\" + name))
    elif PLATFORM == LINUX:
        os.system("rm {} ".format(ROOT_DIR + "/scripts/" + name))
    os.system("adb -s {} shell rm {} ".format(serialno, device_path))

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

    if PLATFORM == WINDOWS:
        os.system("mkdir {}/{} ".format(ROOT_DIR, REPORT_DIR))
    elif PLATFORM == LINUX:
        os.system("mkdir -p {}/{} ".format(ROOT_DIR, REPORT_DIR))

    t = datetime.datetime.now()
    filename = "report_{}{:02d}{:02d}_{:02d}{:02d}{:02d}.json".format(t.year, t.month, t.day, t.hour, t.minute, t.second)

    device, serialno = ViewClient.connectToDeviceOrExit(serialno=None)
    wake_device(device,serialno)
    
    # keymap reference:
    #   https://github.com/dtmilano/AndroidViewClient/blob/master/src/com/dtmilano/android/adb/androidkeymap.py
    device.press("HOME")
    time.sleep(0.5)

    trials = []
    batch_count = 1
    while num_iter > 0:
        log("-------- batch_run #{} --------".format(batch_count))
        trials_batch = []
        trials_batch += record_task_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))
        #trials_batch += recordHD_task_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))
        trials_batch += record_VoiceRecord_run(device, serialno, num_iter=min([num_iter, BATCH_SIZE]))

        map(lambda trial: trial.put_extra(name="batch_id", value=batch_count), trials_batch)
        trials += trials_batch
        with open("{}/{}/{}".format(ROOT_DIR, REPORT_DIR, filename), "w") as f:
            f.write(TrialHelper.to_json(trials))

        num_iter -= BATCH_SIZE
        batch_count += 1
    
    device.press("HOME")

    AudioFunction.finalize()
    Logger.finalize()

def record_task_run(device, serialno, num_iter=1):
    log("record_task_run++")

    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity

    trials = []   
    cmd = " ".join(["am", "force-stop", package])
    
    device.startActivity(component=component)
    time.sleep(1)

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
            log("-> record function: pass")
            trial.put_extra(name="record", value="pass")

    log("AudioFunction.stop_audio()")
    AudioFunction.stop_audio()

    log("dev_record_stop")
    AATApp.record_stop(device)
    time.sleep(5)
    log("ToneDetector.stop_listen()")
    ToneDetector.stop_listen()
    th.join()

    device.shell(cmd)
    log("record_task_run--")
    return trials

def recordHD_task_run(device, serialno, num_iter=1):
    log("record_HD_task_run++")        
        
    package = "com.htc.audiofunctionsdemo"
    activity = ".activities.MainActivity"
    component = package + "/" + activity
    
    cmd = " ".join(["am", "force-stop", package])

    trials = []
    
    device.startActivity(component=component)
    time.sleep(1)

    log("dev_record_start") 
    
    time.sleep(3)
    for i in range(num_iter):
        log("-------- record_task #{} --------".format(i+1))

        trial = Trial(taskname="recordHD")
        trial.put_extra(name="iter_id", value=i+1)
        
        log("AudioFunction.play_sound(out_freq={})".format(OUT_FREQ))
        AudioFunction.play_sound(out_freq=OUT_FREQ)
        
        # record HD start
        log("-> record HD start")
        AATApp.recordHD_start(device)
        time.sleep(10)

        # stop play
        log("AudioFunction.stop_audio()")
        AudioFunction.stop_audio()
        
        # stop record
        log("-> record HD stop")
        AATApp.record_stop(device)
        time.sleep(3)
        
        # analysis file
        pull_files(serialno, file_path)
        
        ret = judge_record(file_name)
        if ret:
            log("-> record HD function: pass")
            trial.put_extra(name="record HD", value="pass")
        else:
            log("-> record HD function: fail")
            trial.invalidate(errormsg="record HD fail")
            trials.append(trial)
        
        trials.append(trial)
        #delete_file(serialno, file_name, file_path)

    device.shell(cmd)
    log("record_task_run--")
    return trials


def get_stop_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/btnPlayPause") > 0:
            return vc, key
    return None, None

def get_record_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/btnRecordStop") > 0:
            return vc, key
    return None, None

def get_save_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/button1") > 0:
            return vc, key
    return None, None

def get_setting_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=Settings") > 0:
            return vc, key
    return None, None

def get_encode_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=Encoding format") > 0:
            return vc, key
    return None, None

def get_flac_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=High res quality (FLAC)") > 0:
            return vc, key
    return None, None

def get_normal_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("text=Normal quality (AMR_NB)") > 0:
            return vc, key
    return None, None

def get_back_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("content-desc=Back") > 0:
            return vc, key
    return None, None

def get_rename_edit_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("id/textName") > 0:
            return vc, key
    return None, None


def get_menu_id(device, serialno):
    vc = ViewClient(device, serialno)
    view_dict = vc.getViewsById()
    for key, value in view_dict.items():
        strTemp = unicode(value).encode("UTF-8")
        if strTemp.find("content-desc=More options") > 0:
            return vc, key
    return None, None


def control_Edit(vc, key, text):
    #vc = ViewClient(device, serialno)
    if key == None:
        log("control Edit -> key is None")
        return False
    edit = vc.findViewByIdOrRaise(key)
    edit.setText(text)
    return True

def control_Btn(vc, key):
    #vc = ViewClient(device, serialno)
    if key == None:
        log("control Btn -> key is None")
        return False
    btn = vc.findViewByIdOrRaise(key)
    btn.touch()
    return True

def record_VoiceRecord_run(device, serialno, num_iter=1):
    # Google Music
    # play
    # pause
    # resume
    # seek
    # forward
    # offload/non-offload
    log("VoiceReocrd record_task_run++")
    
    packageVR = "com.htc.soundrecorder"
    activityVR = ".SoundRecorderBG"
    componentVR = packageVR + "/" + activityVR
    cmd = " ".join(["am", "force-stop", packageVR])
    
    trials = []
    
    for i in range(num_iter):
        trial = Trial(taskname="VoiceRecord record")
        trial.put_extra(name="iter_id", value=i+1)

        device.wake() 
        log("wake")
        time.sleep(1)
        device.startActivity(componentVR)
        log("startActivity")
    
        time.sleep(1)

        # more option
        vc, key = get_menu_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find more option")
            trial.invalidate(errormsg="can't find more option")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        # settings
        vc, key = get_setting_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find setting")
            trial.invalidate(errormsg="can't find setting")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        # (ask to name check)

        # encoding format
        vc, key = get_encode_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find encode")
            trial.invalidate(errormsg="can't find encode")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        # flac
        vc, key = get_flac_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find .flac format")
            trial.invalidate(errormsg="can't find .flac format")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        # back
        vc, key = get_back_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find back key")
            trial.invalidate(errormsg="can't find back key")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        # start record
        vc, key = get_record_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find start record")
            trial.invalidate(errormsg="can't find start record")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        log("AudioFunction.play_sound(out_freq={})".format(OUT_FREQ))
        AudioFunction.play_sound(out_freq=OUT_FREQ)
        time.sleep(10)

        # stop record
        vc, key = get_stop_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find stop record")
            trial.invalidate(errormsg="can't find stop record")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)

        log("AudioFunction.stop_audio()")
        AudioFunction.stop_audio()
        
        # rename
        vc, key = get_rename_edit_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find rename edit")
            trial.invalidate(errormsg="can't find rename edit")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Edit(vc, key, "VRecordHD")
        time.sleep(1)
        
        #save
        vc, key = get_save_id(device=device, serialno=serialno)
        if vc is None:
            log("can't find save file btn")
            trial.invalidate(errormsg="can't find save file btn")
            trials.append(trial)
            device.shell(cmd)
            continue
        control_Btn(vc, key)
        
        # pull file
        pull_files(serialno, voice_path_1)
        
        # judge_record
        ret = judge_recordV(voice_name, thresh=80)
        if ret:
            log("-> VoiceReocrd record HD function: pass")
            trial.put_extra(name="VoiceReocrd record HD", value="pass")
        else:
            log("-> VoiceReocrd record HD function: fail")
            trial.invalidate(errormsg="VoiceReocrd record HD fail")
            trials.append(trial)
        
        trials.append(trial)
        
        delete_file(serialno, voice_name, voice_path_2)
    
    
    device.shell(cmd)
    log("VoiceReocrd record_task_run--")
    return trials
    
def judge_record(name, nfft=4096, fs=96000, framemillis=50, thresh=80):
    log("name = {}, nfft = {}, fs = {}, fm = {}, th = {}".format(name, nfft, fs, framemillis, thresh))
    
    if PLATFORM == WINDOWS:
        path = ROOT_DIR + "\\scripts\\" + name
    elif PLATFORM == LINUX:
        path = ROOT_DIR + "/scripts/" + name
    
    with open(path, 'rb') as f:
        data, samplerate = sf.read(f)	
    framesize = int(fs * framemillis / 1000)
    
    result_sum = 0
    for i in range(100, 200):
        spectrum = np.abs(fft(data[i*framesize:(i+1)*framesize], nfft))
        spectrum = spectrum[:int(nfft/2.0)]
        max_idx = np.argmax(spectrum)
        unit_freq = 1.0*fs / nfft
        #print "tone", max_idx*unit_freq
        #print "db", 20*np.log10(spectrum[max_idx]) 
        result = target_detected(440, max_idx*unit_freq)
        
        if result:
            result_sum = result_sum + 1
        
    if result_sum > thresh:
        print "record HD sucess {}/100".format(result_sum)
        return True
    else:
        print "record HD fail {}/100".format(result_sum)
        return False
        #print "result = {}, freq = {}".format(result, max_idx*unit_freq)
        
def judge_recordV(name, nfft=4096, fs=96000, framemillis=50, thresh=80):
    log("name = {}, nfft = {}, fs = {}, fm = {}, th = {}".format(name, nfft, fs, framemillis, thresh))

    if PLATFORM == WINDOWS:
        path = ROOT_DIR + "\\scripts\\" + name
    elif PLATFORM == LINUX:
        path = ROOT_DIR + "/scripts/" + name
    
    with open(path, 'rb') as f:
            data, samplerate = sf.read(f)
    framesize = int(fs * framemillis / 1000)
    
    result_sum = 0
    for i in range(100, 200):
        spectrum = np.abs(fft(data[i*framesize:(i+1)*framesize, 0], nfft))
        spectrum = spectrum[:int(nfft/2.0)]
        max_idx = np.argmax(spectrum)
        unit_freq = 1.0*fs / nfft
        #print "tone", max_idx*unit_freq
        #print "db", 20*np.log10(spectrum[max_idx]) 
        result = target_detected(440, max_idx*unit_freq)
        
        if result:
            result_sum = result_sum + 1
        
    if result_sum > thresh:
        print "record HD sucess {}/100".format(result_sum)
        return True
    else:
        print "record HD fail"
        return False
        #print "result = {}, freq = {}".format(result, max_idx*unit_freq)        
def target_detected(target_freq, freq):
        if freq == 0:
            return False

        if target_freq == None:
            return True

        diff_semitone = np.abs(np.log(1.0*freq / target_freq) / np.log(2) * 12)
        return diff_semitone < 2

if __name__ == "__main__":   
    num_iter = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    # ViewClient tries to access the system arguments, then it might cause RuntimeError
    if len(sys.argv) > 1: del sys.argv[1:]
    try:
        run(num_iter)
    except Exception as e:
        print(e)
