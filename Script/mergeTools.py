import subprocess
import threading

# maximum waiting time to resolve a merge conflict.
MAX_WAITINGTIME_RESOLVE = 3 * 60


def runIntelliMerge(toolPath, left, base, right, output_path, logger):
	cmd = f"java -jar {toolPath} -d {left} {base} {right} -o {output_path}"
	# logger.info('cmd: ' + cmd)

	# I can't call ProcessUtils.runProcess because IntelliMerge uses multithreading, and it misses error handling in threads,
	# so if a thread throws, IntelliMerge does not exit and runs forever.
	proc = subprocess.Popen(
		cmd,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		shell=True,
		text=True,
		bufsize=1  # line-buffered
	)

	stdout_lines = []
	stderr_lines = []
	exception_found = threading.Event()

	def watch_stderr():
		for line in proc.stderr:
			stderr_lines.append(line)
			# print("[STDERR]", line.strip())  # Optional
			if "concurrent.ExecutionException" in line or "at edu.pku.intellimerge.client.IntelliMerge.main(IntelliMerge.java" in line:
				exception_found.set()
				proc.terminate()
				break

	def watch_stdout():
		for line in proc.stdout:
			stdout_lines.append(line)
		# print("[STDOUT]", line.strip())  # Optional

	t1 = threading.Thread(target=watch_stderr, daemon=True)
	t2 = threading.Thread(target=watch_stdout, daemon=True)
	t1.start()
	t2.start()

	try:
		proc.wait(timeout=MAX_WAITINGTIME_RESOLVE)

		if proc.returncode != 0 or exception_found.is_set():
			full_err = ''.join(stderr_lines)
			if len(full_err) > 500:
				full_err = f'Error message has {len(full_err)} characters.'
			raise subprocess.SubprocessError(f"Failed to run '{cmd}': {full_err}")

		return ''.join(stdout_lines)
	except subprocess.TimeoutExpired:
		proc.terminate()
		raise subprocess.SubprocessError(f'{cmd} did not finish in time')
