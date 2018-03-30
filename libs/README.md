# Libs Documentation
## audiothread.py

### Examples
#### Simplest way
```python
from audiothread import *

th = AudioCommandThread()
th.start()
```
#### Initialize with the specified work queue
```python
from audiothread import *
import queue

cmd_q = queue.Queue()
th = AudioCommandThread(cmd_q=cmd_q)
th.start()
```
#### Playing pure tone with specific frequency
```python
cmd = TonePlayCommand(config=AudioConfig(fs=16000, ch=1), out_freq=440)
th.push(cmd)
```
#### Detecting the frequency with its corresponding amplitude
```python
def result_cb(detected_tone, detected_amp_db):
    if detected_amp_db > 0:
        print("detected: ", int(detected_tone), " Hz", end="\r", flush=True)

cmd = ToneDetectCommand(config=AudioConfig(fs=16000, cb=result_cb), framemillis=100, nfft=4096)
th.push(cmd)
```
#### Stoping the action
```python
cmd.stop()
```
#### Stoping the thread
```python
th.join()
```
**Note that the `cmd` will be "dirty" after calling `cmd.stop()` and hence it will not be executed when it is pushed again, except for calling `cmd.reset()`**
```python
th.push(cmd)
# blablabla
cmd.stop()
# If you need to execute the same command again
cmd.reset()
th.push(cmd)
```