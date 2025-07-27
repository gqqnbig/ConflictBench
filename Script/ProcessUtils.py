import subprocess


class ProcessException(Exception):
	def __init__(self, message):
		self.message = message


def runProcess(cmd, timeout) -> bytes:
	"""

	:param cmd:
	:param timeout:
	:return: stdout
	"""
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
	try:
		outs, errs = proc.communicate(timeout=timeout)
		if proc.returncode != 0:
			errs = errs.decode('utf-8', errors='ignore')
			if len(errs) > 500:
				errs = f'Error message has {len(errs)} characters.'
			raise ProcessException("Fail to run '" + cmd + "' in shell: " + errs)

		return outs
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		proc.terminate()
		raise ProcessException(f'{cmd} does not finish in time')
