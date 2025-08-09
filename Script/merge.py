#!/usr/bin/env python3

# Script to run experiments
import datetime
import enum
import glob
import os
import sys
import logging
import shutil
import pathlib
import subprocess
import time

from git import Repo

import dataset
import mergeTools
import optionUtils
import ProcessUtils

# Set path
workspace = 'Resource/workspace'
output_path = 'Resource/output'

commandLineError = 1

# Set constant
# Set the longest waiting time to wait for a task to execute (Unit: minutes)
MAX_WAITINGTIME_MERGE = 5 * 60
# maximum waiting time to resolve a merge conflict.
MAX_WAITINGTIME_RESOLVE = 3 * 60
Rename_Threshold = "90%"


# Define Exception
class AbnormalBehaviourError(Exception):
	# Any user-defined abnormal behaviour need to terminate the script can be found here
	def __init__(self, message):
		self.message = message


class Merger(enum.Enum):
	JDime = "JDime"
	FstMerge = "FSTMerge"
	IntelliMerge = "IntelliMerge"
	AutoMerge = "AutoMerge"
	Summer = "Summer"
	KDiff = 'KDiff'
	Wiggle = 'Wiggle'


# def merge_with_JDime(input_path, output_path, mode, logger):
# 	proc = None
# 	try:
# 		if mode == 0:
# 			# linebased+structured
# 			mode_cmd = "linebased,structured"
# 		elif mode == 1:
# 			# structured:
# 			mode_cmd = "structured"
# 		else:
# 			raise AbnormalBehaviourError("Undefined mode in JDime")
# 		proc = subprocess.Popen(os.path.join(path_prefix, JDime_executable_path) +
# 								" " + "-f --mode " + mode_cmd +
# 								" --output " + output_path + " " +
# 								os.path.join(input_path, "left") + " " +
# 								os.path.join(input_path, "base") + " " +
# 								os.path.join(input_path, "right"),
# 								stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
# 		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
# 		if proc.returncode == 0:
# 			# Update logger
# 			logger.info("Finish JDime")
# 		else:
# 			# Failed to run JDime
# 			logger.info("Fail to run JDime")
# 			raise AbnormalBehaviourError("Fail to run JDime")
# 	except subprocess.TimeoutExpired:
# 		# Terminate the unfinished process
# 		if proc is not None:
# 			proc.terminate()
# 		# Timeout occur
# 		# Update logger
# 		logger.error("Fail to run JDime in time")
# 		raise AbnormalBehaviourError("Fail to run JDime in time")
# 	finally:
# 		pass


def merge_with_AutoMerge(toolPath, left, base, right, output_path, logger):
	# I can't use ProcessUtils.runProcess because AutoMerge needs to look up the git library.
	cmd = f"{javaPath} -jar {toolPath} -o {output_path} -m structured -log info -f -S {left} {base} {right}"
	# Place the libgit binary at the same folder as the jar, unless the library is globally installed.
	cwd = pathlib.Path(toolPath).parent
	logger.debug(f'cmd: {cmd}')
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=cwd)
	try:
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
		if proc.returncode != 0:
			errs = errs.decode('utf-8', errors='ignore')
			errs = errs[0:min(500, len(errs))]
			raise subprocess.SubprocessError("Fail to run '" + cmd + "' in shell: " + errs)
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		proc.terminate()
		raise subprocess.SubprocessError(f'{cmd} does not finish in time')


# merge two commits
def git_merge(right_parent, logger):
	# Use git to merge left and right
	# Assuming repository is currently at left version
	proc = None
	try:
		proc = subprocess.Popen("git merge -s recursive -X find-renames=" + Rename_Threshold + ' ' + right_parent,
								stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_MERGE)
		if proc.returncode == 0:
			# Successful merged by git merge
			return True
		else:
			# Git merge failed
			return False
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		if proc is not None:
			proc.terminate()
		# Failed to get result of git merge in time
		logger.error("Fail to run git merge in time")
		raise AbnormalBehaviourError("Fail to run git merge in time")
	finally:
		pass


def createSparseWorktree(mainWorktree, newWorktree, sha, file_path):
	assert os.path.isabs(mainWorktree)
	assert os.path.isabs(newWorktree)

	subprocess.run(['git', 'worktree', 'add', '-f', '--no-checkout',
					newWorktree, sha],
				   cwd=mainWorktree, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

	# In the cone mode, the path must be a folder, not file name.
	# git may throw
	# fatal: 'spring-boot-project/spring-boot-dependencies/pom.xml' is not a directory; to treat it as a directory anyway, rerun with --skip-checks

	# In the no-cone mode, prepending a slash to file_path is recommended by the git binary,
	# but on Windows it may present a bug that the path incorrectly joins with the directory of the git binary.
	# $ git sparse-checkout list
	# C:/Program Files/Git/spring-boot-project/spring-boot-dependencies/pom.xml
	subprocess.run(['git', 'sparse-checkout', 'set', '--no-cone', file_path],
				   cwd=newWorktree, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

	subprocess.run(['git', 'checkout', '-f'], cwd=newWorktree, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def prepare_repo(local_path, project_url, sha):
	if os.path.isdir(local_path) and os.path.isdir(os.path.join(local_path, '.git')):
		repo = Repo(local_path)
	else:
		os.makedirs(local_path, exist_ok=True)
		repo = Repo.init(local_path)
		repo.create_remote('origin', project_url)
		repo.remotes.origin.fetch(sha)

	repo.git.config('core.longpaths', 'true')
	repo.git.checkout(sha, force=True)


def create4Worktrees(subjectRepo, workspace, mainWorktree):
	"""
	From the main worktree, create 4 worktrees: base, left, right, and child (merged).

	:param subjectRepo:
	:param workspace:
	:param mainWorktree:
	:return: (base_folder, left_Folder, right_folder, child_folder)
	"""
	base_folder = os.path.join(workspace, subjectRepo.repoName + '-base')
	createSparseWorktree(mainWorktree, base_folder, subjectRepo.baseCommit, subjectRepo.conflictingFile)
	logger.debug("Prepared base version")

	left_Folder = os.path.join(workspace, subjectRepo.repoName + '-left')
	createSparseWorktree(mainWorktree, left_Folder, subjectRepo.leftCommit, subjectRepo.conflictingFile)
	logger.debug("Prepared left version")

	right_folder = os.path.join(workspace, subjectRepo.repoName + '-right')
	createSparseWorktree(mainWorktree, right_folder, subjectRepo.rightCommit, subjectRepo.conflictingFile)
	logger.debug("Prepared right version")

	child_folder = os.path.join(workspace, subjectRepo.repoName + '-child')
	createSparseWorktree(mainWorktree, child_folder, subjectRepo.mergeCommit, subjectRepo.conflictingFile)
	logger.debug("Prepared child version")
	return (base_folder, left_Folder, right_folder, child_folder)


def processExample(merger: Merger, mergerPath, subjectRepo: dataset.SubjectRepo):
	# os.chdir(os.path.join(path_prefix, workspace))
	repoPath = os.path.join(path_prefix, workspace, subjectRepo.repoName)
	prepare_repo(repoPath, subjectRepo.repoUrl, subjectRepo.mergeCommit)

	resultFolder = os.path.join(path_prefix, workspace, 'result')
	pathlib.Path(resultFolder).mkdir(exist_ok=True)

	toolResultFolder = pathlib.Path(resultFolder, Merger(merger).value)
	toolResultFolder.mkdir(exist_ok=True)
	mergeResultFolder = toolResultFolder / subjectRepo.repoName
	mergeResultFolder.mkdir(exist_ok=True)
	(base_folder, left_Folder, right_folder, child_folder) = create4Worktrees(subjectRepo, os.path.join(path_prefix, workspace), repoPath)
	match merger:
		case Merger.Summer:
			pathlib.Path(os.path.join(resultFolder, 'summer')).mkdir(exist_ok=True)
			try:
				mergeTools.runSummer(mergerPath, repoPath,
									 subjectRepo.leftCommit, subjectRepo.rightCommit, subjectRepo.baseCommit, mergeResultFolder,
									 subjectRepo.conflictingFile, subjectRepo.getMergedFile(os.path.join(path_prefix, workspace)),
									 logger)
				logger.info("summer solution generated")
			except Exception as e:
				logger.error(e)
			# Summer doesn't need file existence check.
			return
		case Merger.FstMerge:
			try:
				mergeTools.runFSTMerge(mergerPath, repoPath, toolResultFolder, logger)
			except Exception as e:
				logger.error(e)
		case Merger.AutoMerge:
			try:
				merge_with_AutoMerge(mergerPath, left_Folder, base_folder, right_folder, mergeResultFolder, logger)
			except Exception as e:
				logger.error(e)
				return
		case Merger.IntelliMerge:
			try:
				mergeTools.runIntelliMerge(mergerPath, left_Folder, base_folder, right_folder, mergeResultFolder, logger)
			except Exception as e:
				logger.error(e)
				return
		case Merger.KDiff:
			try:
				if False is mergeTools.runKDiff3(mergerPath, left_Folder, base_folder, right_folder, mergeResultFolder, logger):
					logger.info('KDiff failed.')
					return
			except Exception as e:
				logger.error(e)
				return
		case Merger.Wiggle:
			try:
				if False is mergeTools.runWiggle(mergerPath, left_Folder, base_folder, right_folder, mergeResultFolder, logger, subjectRepo):
					logger.info('Wiggle failed')
					return
			except Exception as e:
				logger.error(e)
				return

	for item in (toolResultFolder / subjectRepo.repoName).rglob('*'):
		if os.path.isfile(item):
			if item.name.endswith('-normalized.java'):
				continue
			if time.time() - os.path.getmtime(item) <= 10:

				logger.info(f"{Merger(merger).value} solution generated")
			else:
				mtime = datetime.datetime.fromtimestamp(os.path.getmtime(item)).isoformat(timespec='seconds')
				logger.warning(f'File {item} is lastly modified on {mtime}. ' +
							   f'You may want to clean up {toolResultFolder}.')
			return

	logger.info(f'{Merger(merger).value} fails to write any files.')


# create logger to record complete info
# create logger with 'script_logger'
logger = logging.getLogger('textual_conflict_logger')

if __name__ == '__main__':
	if '--help' in sys.argv:
		print('''
{0}: run a merge tool on selected data examples

--help	show this help.
--log-file	specify the path of a log file. If this option is missing, log is not written to disk.
--log-level	info or debug. Default is info.
--path-prefix	the directory of ConflictBench. If this option is missing, the path is the parent of parent folder of {0}, which is {1}.
--total_list	the path to the file containing all examples. If this option is missing, the path is derived from --path-prefix.
--range	n1..n2	run experiments against examples from n1, inclusive to n2, exclusive. n1 starts at 0. If this option is missing, run all examples.

--merger path	
run the merge at the given path. 
{0} automatically checks if the merge is AutoMerge, FSTMerge, IntelliMerge, JDime, KDiff3, or summer.
'''.format(sys.argv[0], pathlib.Path(__file__).parent.parent.resolve()))
		exit(0)

	try:
		i = sys.argv.index('--log-level')
		logLevel = sys.argv[i + 1]
		match logLevel.lower():
			case 'info':
				logger.setLevel(logging.INFO)
			case 'debug':
				logger.setLevel(logging.DEBUG)
			case _:
				print(f'Log level must be info or debug. What you passed is {logLevel}', file=sys.stderr)
				exit(commandLineError)
	except:
		logger.setLevel(logging.INFO)

	try:
		i = sys.argv.index('--path-prefix')
		path_prefix = sys.argv[i + 1]
	except:
		path_prefix = pathlib.Path(__file__).parent.parent.resolve()

	try:
		i = sys.argv.index('--merger')
		mergerPath = sys.argv[i + 1]
		if 'summer' in mergerPath.lower():
			merger = Merger.Summer
		elif 'automerge' in mergerPath.lower():
			merger = Merger.AutoMerge
		elif 'fstmerge' in mergerPath.lower():
			merger = Merger.FstMerge
		elif 'intellimerge' in mergerPath.lower():
			merger = Merger.IntelliMerge
		elif 'jdime' in mergerPath.lower():
			merger = Merger.JDime
		elif 'kdiff' in mergerPath.lower():
			merger = Merger.KDiff
		elif 'wiggle' in mergerPath.lower():
			merger = Merger.Wiggle
		else:
			print(f"Can't recognize the merger from path {mergerPath}. Name a folder or the file to the supported merger.", file=sys.stderr)
			exit(commandLineError)
	except:
		print(f'Option --merger is required.', file=sys.stderr)
		exit(commandLineError)

	formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
	try:
		i = sys.argv.index('--log-file')
		logger_path = sys.argv[i + 1]
		fh = logging.FileHandler(logger_path)
		fh.setLevel(logging.INFO)
		# create formatter and add it to the handlers
		fh.setFormatter(formatter)
		# add the handlers to the logger
		logger.addHandler(fh)
	except:
		pass

	streamHandler = logging.StreamHandler()
	streamHandler.setFormatter(formatter)
	logger.addHandler(streamHandler)

	opt = optionUtils.Options()
	opt.LoadDataset()
	opt.LoadRange()

	if merger == Merger.FstMerge:
		# clean up its temp folders.
		# When FSMerge throws exceptions, it doesn't clean up.
		workspaceFolder = os.path.join(path_prefix, workspace, 'result', 'FSTMerge')
		for entry in os.listdir(workspaceFolder):
			full_path = os.path.join(workspaceFolder, entry)
			# Check if it's a directory and if it matches the substring
			if os.path.isdir(full_path) and 'fstmerge_tmp' in entry:
				try:
					shutil.rmtree(full_path)
				except Exception as e:
					print(f"Failed to delete {full_path}: {e}")

	try:
		i = sys.argv.index('--java')
		javaPath = sys.argv[i + 1]
	except:
		javaPath = 'java'

	# print(ProcessUtils.runProcess('java -version', None).decode('utf-8', errors='ignore'))
	# exit(0)
	for i in opt.evaluationRange:
		logger.info(f"Start processing project {i}, {opt.dataset[i].repoName}. Conflicting file is {pathlib.Path(opt.dataset[i].conflictingFile).name}.")
		processExample(merger, mergerPath, opt.dataset[i])
