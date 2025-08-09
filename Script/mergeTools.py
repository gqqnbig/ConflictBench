import logging
import os
import pathlib
import subprocess
import threading

import ProcessUtils

# maximum waiting time to resolve a merge conflict.
MAX_WAITINGTIME_RESOLVE = 3 * 60
toolError = 10


def runIntelliMerge(toolPath, left, base, right, output_path, logger):
	cmd = f"java -jar {toolPath} -d {left} {base} {right} -o {output_path}"
	logger.debug('cmd: ' + cmd)

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


def runKDiff3(toolPath, left, base, right, output_path, logger):
	cmd = [r'C:\ProgramData\chocolatey\lib\autohotkey.portable\tools\AutoHotkey.exe', r'D:\ConflictBench\Script\KDiffRunner.ahk',
		   toolPath, base, left, right, output_path]

	ProcessUtils.runProcess(cmd, MAX_WAITINGTIME_RESOLVE)


def runWiggle(toolPath, left, base, right, output_path, logger, repo):
	baseFile = pathlib.Path(base) / repo.conflictingFile
	leftFile = pathlib.Path(left) / repo.conflictingFile
	rightFile = pathlib.Path(right) / repo.conflictingFile
	if baseFile.exists() is False or leftFile.exists() is False or rightFile.exists() is False:
		raise Exception("wiggle can't deal with file renaming.")

	outputFile = pathlib.Path(output_path) / repo.conflictingFile
	outputFile.parent.mkdir(exist_ok=True, parents=True)
	cmd = [toolPath,
		   '--merge', baseFile, leftFile, rightFile,
		   '--output', outputFile]

	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	try:
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
		if proc.returncode != 0:
			errs = errs.decode('utf-8', errors='ignore')
			if len(errs) > 500:
				errs = f'Error message has {len(errs)} characters.'
			cmd = '(quoting skipped) ' + ' '.join([str(c) for c in cmd])
			raise subprocess.SubprocessError("Fail to run '" + cmd + "' in shell: " + errs)
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		proc.terminate()
		raise subprocess.SubprocessError(f'{cmd} does not finish in time')


def runSummer(toolPath, repo, leftSha, rightSha, baseSha, output_path, targetFile1, targetFile2, logger):
	cmd = f'{toolPath} merge -C {repo} -l {leftSha} -r {rightSha} -b {baseSha} --worktree {output_path} --keep -- {targetFile1}'
	if targetFile2 is not None and targetFile2 != targetFile1:
		cmd += ' ' + targetFile2
	try:
		logger.debug(f'cmd: {cmd}')
		stdout = ProcessUtils.runProcess(cmd, MAX_WAITINGTIME_RESOLVE)
		if logger.isEnabledFor(logging.DEBUG):
			logger.debug(stdout.decode('utf-8', errors='ignore'))
	except subprocess.SubprocessError as e:
		logger.error(e)


def runFSTMerge(toolPath, repoDir, containerPath, logger):
	"""

	:param toolPath:
	:param repoDir:
	:param containerPath:
	:param logger: for debug info and critical error. Do not raise an exception as well as writing to log.
	:return:
	"""
	# Create merge.config at first
	repoName = pathlib.Path(repoDir).name
	configPath = os.path.normpath(os.path.join(containerPath, repoName + ".config"))
	if not os.path.exists(configPath):
		with open(configPath, "w") as f:
			f.write(f"{repoName}-left\n{repoName}-base\n{repoName}-right")

	cmd = f'java -cp {toolPath} merger.FSTGenMerger' + \
		  f' --expression {configPath} --output-directory {containerPath} --base-directory {pathlib.Path(repoDir).parent}'

	logger.debug(f'cmd: {cmd}')

    # On POSIX, if cmd is string, shell must be True
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=containerPath, shell=True)
	try:
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
		errs = errs.decode('utf-8', errors='ignore')

		if r'Cannot run program "C:\Programme\cygwin\bin\git.exe"' in errs or \
				'unknown option: --merge-file' in errs:
			logger.error('FSTMerge calls git with incorrect command line options. ' +
						 'featurehouse_20220107.jar included in ConflictBench may only be used on Linux.\n' +
						 'See https://github.com/joliebig/featurehouse/blob/81724157bc638524e72af5bb689cf939e6df8599/fstmerge/merger/LineBasedMerger.java#L93-L96')
			exit(toolError)

		if proc.returncode != 0:
			if len(errs) > 500:
				errs = f'Error message has {len(errs)} characters.'
			raise subprocess.SubprocessError("Fail to run '" + cmd + "' in shell: " + errs)

		if logger.isEnabledFor(logging.DEBUG):
			logger.debug(outs.decode('utf-8', errors='ignore'))
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		proc.terminate()
		raise subprocess.SubprocessError(f'{cmd} does not finish in time')
