import threading
import sounddevice as sd
import numpy as np
from scipy.fftpack import fft
import soundfile as sf
from libs.popsounddetect import PopSoundDetecter

count = 0
shared_count = {
    "count"      : count
}

try:
    import queue
except ImportError:
    import Queue as queue

class AudioConfig(object):
    def __init__(self, fs, ch=1, dtype="float32", cb=None, pop_cb=None):
        self.fs = fs
        self.ch = ch
        self.dtype = dtype
        self.cb = cb
        self.pop_cb = pop_cb

class AudioCommand(object):
    def __init__(self, config):
        self.config = config

class TonePlayCommand(AudioCommand):
    def __init__(self, config, out_freq):
        super(TonePlayCommand, self).__init__(config)
        self.out_freq = out_freq
        self.is_playing = True

    def stop(self):
        self.is_playing = False

    def reset(self):
        self.is_playing = True

class ToneDetectCommand(AudioCommand):
    def __init__(self, config, framemillis=100, nfft=-1):
        super(ToneDetectCommand, self).__init__(config)
        self.framemillis = framemillis
        self.nfft = nfft
        if self.nfft < 0:
            self.nfft = int(framemillis*self.config.fs/1000)
        self.is_detecting = True

    def stop(self):
        self.is_detecting = False

    def reset(self):
        self.is_detecting = True



class AudioCommandThread(threading.Thread):
    def __init__(self, cmd_q=None):
        super(AudioCommandThread, self).__init__()
        self.cmd_q = cmd_q if cmd_q else queue.Queue()
        self.stoprequest = threading.Event()
        self.current_cmd = None
        
        self.isPop = False

    def join(self, timeout=None):
        if self.current_cmd:
            self.current_cmd.stop()
        self.stoprequest.set()
        super(AudioCommandThread, self).join(timeout)

    def run(self):
        while not self.stoprequest.isSet():
            try:
                cmd = self.cmd_q.get(True, 0.1)
                if isinstance(cmd, AudioCommand):
                    self.current_cmd = cmd
                    self._process_command(cmd)
                    self.current_cmd = None
            except queue.Empty:
                continue

    def push(self, cmd):
        if isinstance(cmd, AudioCommand):
            self.cmd_q.put(cmd)
        else:
            raise ValueError("The command type is not AudioCommand.")

    def _process_command(self, cmd):
        if type(cmd) is TonePlayCommand:
            self._process_playback_command(cmd)
        elif type(cmd) is ToneDetectCommand:
            self._process_detect_command(cmd)
            

    def _process_playback_command(self, cmd):
        phase_offset = 0
        cfg = cmd.config

        # Make the code adaptive to both python 2 and 3
        shared_vars = {
            "cmd"         : cmd,
            "phase_offset": phase_offset
        }

        def playback_cb(outdata, frames, time, status):
            phase_offset = shared_vars["phase_offset"]
            cmd = shared_vars["cmd"]
            cfg = cmd.config

            signal = np.arange(outdata.shape[0])
            signal = signal * 2*np.pi/cfg.fs + phase_offset
            phase_offset += outdata.shape[0] * 2*np.pi/cfg.fs
            signal = 0.99 * np.sin(signal * cmd.out_freq)

            for cidx in range(outdata.shape[1]):
                outdata[:, cidx] = signal

            shared_vars["phase_offset"] = phase_offset
            shared_vars["cmd"] = cmd

        with sd.OutputStream(channels=cfg.ch, callback=playback_cb, samplerate=cfg.fs, dtype="float32"):
            while cmd.is_playing:
                sd.sleep(500)

    def _process_detect_command(self, cmd):
        cfg = cmd.config
        buff = np.array([])
        framesize = int(cfg.fs*cmd.framemillis/1000)
        poptime = 0

        # Make the code adaptive to both python 2 and 3
        shared_vars = {
            "cmd"      : cmd,
            "buff"     : buff,
            "framesize": framesize,
            "poptime"  : poptime
        }

        def record_cb(indata, frames, time, status):
            cmd = shared_vars["cmd"]
            cfg = cmd.config
            buff = shared_vars["buff"]
            framesize = shared_vars["framesize"]
            poptime = shared_vars["poptime"]
            
            if buff.any():
                buff = np.vstack((buff, indata[:, :]))
            else:
                buff = np.array(indata[:, :])

            if buff.size >= framesize:
                #sf.write('./file3/new_file{}.wav'.format(shared_count["count"]), buff[:framesize, 0], 16000)
                #shared_count["count"] = shared_count["count"] + 1

                spectrum = np.abs(fft(buff[:framesize, 0], cmd.nfft))
                spectrum = spectrum[:int(cmd.nfft/2.0)]
                max_idx = np.argmax(spectrum)
                unit_freq = 1.0*cfg.fs / cmd.nfft
                tone = max_idx*unit_freq

                
                isPop = PopSoundDetecter.pop_detect(buff[:framesize, 0], framesize, 3)
                
                if cfg.pop_cb:
                    cfg.pop_cb(isPop)
                
                    
                if cfg.cb:
                    cfg.cb(detected_tone=max_idx*unit_freq, detected_amp_db=20*np.log10(spectrum[max_idx]))

                buff = buff[framesize:, :]

            shared_vars["cmd"] = cmd
            shared_vars["buff"] = buff
            shared_vars["framesize"] = framesize
            

        with sd.InputStream(channels=cfg.ch, callback=record_cb, samplerate=cfg.fs, dtype="float32"):
            while cmd.is_detecting:
                sd.sleep(500)
