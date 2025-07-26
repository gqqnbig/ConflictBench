import subprocess


class ProcessException(Exception):
	def __init__(self, message):
		self.message = message


def runProcess(cmd, timeout) -> str:
	"""

	:param cmd:
	:param timeout:
	:return: stdout
	"""
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
	try:
		outs, errs = proc.communicate(timeout=timeout)
		if proc.returncode != 0:
			raise ProcessException("Fail to run '" + cmd + "' in shell: " + errs)
		return outs
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		proc.terminate()
		raise ProcessException(f'{cmd} does not finish in time')
