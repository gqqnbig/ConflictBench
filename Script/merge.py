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
logger_path = 'Logger'
output_path = 'Resource/output'
JDime_executable_path = 'MergeTools/JDime/bin/JDime'
IntelliMerge_executable_path = 'MergeTools/IntelliMerge/IntelliMerge-1.0.9-all.jar'
summerPath = None

commandLineError = 1
toolError = 10

# Set constant
# Set the longest waiting time to wait for a task to execute (Unit: minutes)
MAX_WAITINGTIME_MERGE = 5 * 60
MAX_WAITINGTIME_CLONE = 10 * 60
MAX_WAITINGTIME_MERGE_BASE = 1 * 60
MAX_WAITINGTIME_RESET = 5 * 60
# maximum waiting time to resolve a merge conflict.
MAX_WAITINGTIME_RESOLVE = 3 * 60
MAX_WAITINGTIME_DIFF = 5 * 60
MAX_WAITINGTIME_LOG = 5 * 60
MAX_WAITINGTIME_COMPILE = 5 * 60
MAX_WAITINGTIME_TEST = 10 * 60
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


def merge_with_JDime(input_path, output_path, mode, logger):
	proc = None
	try:
		if mode == 0:
			# linebased+structured
			mode_cmd = "linebased,structured"
		elif mode == 1:
			# structured:
			mode_cmd = "structured"
		else:
			raise AbnormalBehaviourError("Undefined mode in JDime")
		proc = subprocess.Popen(os.path.join(path_prefix, JDime_executable_path) +
								" " + "-f --mode " + mode_cmd +
								" --output " + output_path + " " +
								os.path.join(input_path, "left") + " " +
								os.path.join(input_path, "base") + " " +
								os.path.join(input_path, "right"),
								stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
		if proc.returncode == 0:
			# Update logger
			logger.info("Finish JDime")
		else:
			# Failed to run JDime
			logger.info("Fail to run JDime")
			raise AbnormalBehaviourError("Fail to run JDime")
	except subprocess.TimeoutExpired:
		# Terminate the unfinished process
		if proc is not None:
			proc.terminate()
		# Timeout occur
		# Update logger
		logger.error("Fail to run JDime in time")
		raise AbnormalBehaviourError("Fail to run JDime in time")
	finally:
		pass


def merge_with_FSTMerge(toolPath, repoDir, output_path, logger):
	"""

	:param toolPath:
	:param repoDir:
	:param output_path:
	:param logger: for debug info and critical error. Do not raise an exception as well as writing to log.
	:return:
	"""
	# Create merge.config at first
	repoName = pathlib.Path(repoDir).name
	configPath = os.path.normpath(os.path.join(output_path, repoName + ".config"))
	if not os.path.exists(configPath):
		with open(configPath, "w") as f:
			f.write(f"{repoName}-left\n{repoName}-base\n{repoName}-right")

	cmd = f'java -cp {toolPath} merger.FSTGenMerger' + \
		  f' --expression {configPath} --output-directory {output_path} --base-directory {pathlib.Path(repoDir).parent}'

	logger.debug(f'cmd: {cmd}')

	# I can't call ProcessUtils.runProcess because FSTMerge can fail but still return exit code 0.
	proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
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


def merge_with_summer(toolPath, repo, leftSha, rightSha, baseSha, output_path, targetFile1, targetFile2=None):
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
	# Read merge scenario information
	# project_url = example['repo_url']
	# project_name = example['project_name']
	# commit = {}
	# commit['base'] = example['base_hash']
	# commit['left'] = example['left_hash']
	# commit['right'] = example['right_hash']
	# commit['child'] = example['child_hash']
	# file_path = example['conflicting_file']

	os.chdir(os.path.join(path_prefix, workspace))
	repoPath = os.path.join(path_prefix, workspace, subjectRepo.repoName)
	prepare_repo(repoPath, subjectRepo.repoUrl, subjectRepo.mergeCommit)

	resultFolder = os.path.join(path_prefix, workspace, 'result')
	pathlib.Path(resultFolder).mkdir(exist_ok=True)

	toolResultFolder = pathlib.Path(resultFolder, Merger(merger).value)
	toolResultFolder.mkdir(exist_ok=True)
	match merger:
		case Merger.Summer:
			pathlib.Path(os.path.join(resultFolder, 'summer')).mkdir(exist_ok=True)
			# commit['summer_mergeable'] = True
			try:
				merge_with_summer(mergerPath, repoPath,
								  subjectRepo.leftCommit, subjectRepo.rightCommit, subjectRepo.baseCommit,
								  os.path.join(resultFolder, 'summer', subjectRepo.repoName), subjectRepo.conflictingFile, subjectRepo.getMergedFile(os.path.join(path_prefix, workspace)))
				# commit['summer_solution_generation'] = True
				logger.info("summer solution generated")
			except Exception as e:
				# commit['summer_solution_generation'] = False
				pass
		case Merger.FstMerge:
			pathlib.Path(os.path.join(resultFolder, 'FSTMerge')).mkdir(exist_ok=True)
			create4Worktrees(subjectRepo, os.path.join(path_prefix, workspace), repoPath)
			try:
				merge_with_FSTMerge(mergerPath, repoPath, os.path.join(resultFolder, 'FSTMerge'), logger)
				logger.info("FSTMerge solution generated")
			except Exception as e:
				logger.error(e)

		case Merger.AutoMerge:
			mergeResultFolder = toolResultFolder / subjectRepo.repoName
			mergeResultFolder.mkdir(exist_ok=True)
			(base_folder, left_Folder, right_folder, child_folder) = create4Worktrees(subjectRepo, os.path.join(path_prefix, workspace), repoPath)
			try:
				merge_with_AutoMerge(mergerPath, left_Folder, base_folder, right_folder, mergeResultFolder, logger)
			except Exception as e:
				logger.error(e)
				return
		case Merger.IntelliMerge:
			mergeResultFolder = toolResultFolder / subjectRepo.repoName
			mergeResultFolder.mkdir(exist_ok=True)
			(base_folder, left_Folder, right_folder, child_folder) = create4Worktrees(subjectRepo, os.path.join(path_prefix, workspace), repoPath)
			try:
				mergeTools.runIntelliMerge(mergerPath, left_Folder, base_folder, right_folder, mergeResultFolder, logger)
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
	return

	# Run git-merge to get the git-merge version
	# Make a copy and change to left version

	createBranchVersion(project_name, 'git-merge')
	os.chdir(os.path.join(path_prefix, workspace, 'git-merge'))
	# Reset to left version first
	Repo(os.getcwd()).git.reset('--hard', commit['left'])
	# git_reset_commit(commit['left'], logger)
	# Try to merge with right version
	git_merge(commit['right'], logger)
	# Except the conflicting file, remove all other files in git-merge version
	os.chdir(os.path.join(path_prefix, workspace, 'git-merge'))
	for filename in glob.glob("**", recursive=True):
		if filename == file_path:
			logger.info("Found same name file in git-merge version")
		if os.path.isfile(filename) and filename != file_path:
			os.remove(filename)
	logger.info("Complete deletion in git-merge version")
	# Check whether input is java file
	if file_path.endswith('java'):
		java_file_format = True
		logger.info("conflict file is java file")
	else:
		java_file_format = False
		logger.info("conflict file is not java file")
	# Check whether base/left/right versions have the corresponding file to merge
	empty_file = False
	# Check base version
	if not os.path.exists(os.path.join(path_prefix, workspace, "base", file_path)):
		logger.info("Cannot find corresponding file in base version, skip multiple tools")
		empty_file = True
	elif not os.path.isfile(os.path.join(path_prefix, workspace, "base", file_path)):
		logger.error("Wrong conflicting file path in base version, refer to a folder")
		raise Exception("Wrong conflicting file path in base version, refer to a folder")
	# Check left version
	if not os.path.exists(os.path.join(path_prefix, workspace, "left", file_path)):
		logger.info("Cannot find corresponding file in left version, skip multiple tools")
		empty_file = True
	elif not os.path.isfile(os.path.join(path_prefix, workspace, "left", file_path)):
		logger.error("Wrong conflicting file path in left version, refer to a folder")
		raise Exception("Wrong conflicting file path in left version, refer to a folder")
	# Check right version
	if not os.path.exists(os.path.join(path_prefix, workspace, "right", file_path)):
		logger.info("Cannot find corresponding file in right version, skip multiple tools")
		empty_file = True
	elif not os.path.isfile(os.path.join(path_prefix, workspace, "right", file_path)):
		logger.error("Wrong conflicting file path in right version, refer to a folder")
		raise Exception("Wrong conflicting file path in right version, refer to a folder")
	# Create result folder
	pathlib.Path(os.path.join(path_prefix, workspace, 'result')).mkdir(exist_ok=True)

	pathlib.Path(os.path.join(path_prefix, workspace, 'result', 'FSTMerge')).mkdir(exist_ok=True)

	# Move the child version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'child'),
				resultFolder)
	# Move the git-merge version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'git-merge'),
				resultFolder)

	# If empty_file is True or file is not java file
	# skip JDime, IntelliMerge, AutoMerge, only keep FSTMerge
	if empty_file or not java_file_format:
		commit['JDime_mergeable'] = False
		commit['IntelliMerge_mergeable'] = False
		commit['AutoMerge_mergeable'] = False
		commit['FSTMerge_solution_generation'] = True
		commit['JDime_solution_generation'] = False
		commit['IntelliMerge_solution_generation'] = False
		commit['AutoMerge_solution_generation'] = False
	else:
		# Debug code
		# logger.info("Skip processed index " + str(i) + "\tproject " + project_name + " commit " + commit['child'])
		# # Update project_record.txt in each loop
		# with open(os.path.join(path_prefix, data_path, "project_record.txt"), "wb") as fp:
		#     pickle.dump(project_record, fp)
		# continue
		commit['JDime_mergeable'] = True
		commit['IntelliMerge_mergeable'] = True

	pathlib.Path(os.path.join(resultFolder, 'JDime')).mkdir()
	pathlib.Path(os.path.join(resultFolder, 'IntelliMerge')).mkdir()
	logger.info("Complete processing index " + str(i) + "\tproject " + project_name + " commit " + commit['child'])

	# Move the base version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'base'), resultFolder)
	# Move the left version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'left'), resultFolder)
	# Move the right version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'right'), resultFolder)
	# Move the entire result folder into output folder
	# Make sure corresponding folder doesn't exist to ensure the behavior of shutil.move()
	if os.path.exists(os.path.join(path_prefix, output_path, project_name, commit['child'])):
		shutil.rmtree(os.path.join(path_prefix, output_path, project_name, commit['child']))
	shutil.move(resultFolder, os.path.join(path_prefix, output_path, project_name, commit['child']))
	# Add commit info into project_record
	project_record[commit['child']] = commit


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
		workspaceFolder = os.path.join(path_prefix, workspace)
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
