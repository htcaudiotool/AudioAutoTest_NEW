import subprocess
from libs.logger import Logger

TAG = "Adb"
def log(msg):
	Logger.log(TAG, msg)

class Adb(object):
	HAS_BEEN_INIT = False

	@staticmethod
	def init():
		Adb._execute("start-server", None)
		Adb.HAS_BEEN_INIT = True

	@staticmethod
	def _check_init():
		if not Adb.HAS_BEEN_INIT:
			Adb.init()

	@staticmethod
	def execute(cmd, serialno=None, tolog=True):
		Adb._check_init()
		return Adb._execute(cmd, serialno, tolog)

	@staticmethod
	def _execute(cmd, serialno, tolog=True):
		if not isinstance(cmd, list):
			cmd = [cmd]

		cmd_prefix = ["adb"]
		if serialno:
			cmd_prefix += ["-s", serialno]
		
		cmd = cmd_prefix + cmd
		if tolog:
			log("exec: {}".format(cmd))
		return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
