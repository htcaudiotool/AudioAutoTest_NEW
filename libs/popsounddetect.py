from audiothread import *
import threading
import numpy as np
import time
import os
import datetime

from libs.logger import Logger
from libs.trials import Trial, TrialHelper

class PopSoundDetecter(object):
    Logger.init()
        
    @staticmethod
    def pop_detect(buff, framesize, threshold):
        i = 0
        oldsum = 0
        limit = (framesize - (framesize % 36))

        while i < limit:
            if i == 0:
                i += 18
                continue
            summ = 0

            for j in range(36):              
                if i + j >= limit:
                    break
                summ = buff[i + j] * buff[i + j] + summ

            if i == 18:
                oldsum = summ

            if np.abs(summ - oldsum) > threshold:
                return True

            oldsum = summ
            i += 18
                
            if i > limit - 36:
                break
                
        return False