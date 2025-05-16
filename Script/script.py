# Script to run experiments
import glob
import os
import sys
import logging
import shutil
from pathlib import Path
from logging import StreamHandler

from git import Repo
import subprocess

# Set path
workspace = 'Resource/workspace'
logger_path = 'Logger'
output_path = 'Resource/output'
FSTMerge_executable_path = 'MergeTools/FSTMerge/featurehouse_20220107.jar'
JDime_executable_path = 'MergeTools/JDime/bin/JDime'
IntelliMerge_executable_path = 'MergeTools/IntelliMerge/IntelliMerge-1.0.9-all.jar'
AutoMerge_executable_path = 'MergeTools/AutoMerge/AutoMerge.jar'
summerPath = None

# Set constant
# Set the longest waiting time to wait for a task to execute (Unit: minutes)
MAX_WAITINGTIME_MERGE = 5 * 60
MAX_WAITINGTIME_CLONE = 10 * 60
MAX_WAITINGTIME_MERGE_BASE = 1 * 60
MAX_WAITINGTIME_RESET = 5 * 60
# maximum waiting time to resolve a merge conflict.
MAX_WAITINGTIME_RESOLVE = 1 * 60
MAX_WAITINGTIME_DIFF = 5*60
MAX_WAITINGTIME_LOG = 5*60
MAX_WAITINGTIME_COMPILE = 5*60
MAX_WAITINGTIME_TEST = 10*60
Rename_Threshold = "90%"

# Define Exception
class AbnormalBehaviourError(Exception):
    # Any user-defined abnormal behaviour need to terminate the script can be found here
    def __init__(self, message):
        self.message = message

def merge_with_JDime(input_path, output_path, mode, logger):
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
        proc.terminate()
        # Timeout occur
        # Update logger
        logger.error("Fail to run JDime in time")
        raise AbnormalBehaviourError("Fail to run JDime in time")
    finally:
        pass


def runProcess(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
    try:
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
        if proc.returncode != 0:
            # Failed to run JDime
            logger.info("Fail to run '" + cmd + "' in shell: " + errs)
            raise AbnormalBehaviourError("Fail to run '" + cmd + "' in shell: " + errs)
    except subprocess.TimeoutExpired:
        # Terminate the unfinished process
        proc.terminate()
        logger.error(f'{cmd} does not finish in time')
        raise AbnormalBehaviourError(f'{cmd} does not finish in time')


def merge_with_FSTMerge(input_path, output_path, logger):
    # Create merge.config at first
    f = open(os.path.join(input_path, "merge.config"), "w")
    f.write("left\nbase\nright");
    f.close()
    # Run FSTMerge
    runProcess("java -cp " +
               os.path.join(path_prefix, FSTMerge_executable_path) +
               " " + "merger.FSTGenMerger --expression " +
               os.path.join(input_path, "merge.config") + " > " +
               os.path.join(output_path, "result.txt"))
    logger.info("Finish FSTMerge")
    # Move the generated folder into output path
    if os.path.exists(os.path.join(input_path, "merge")) and \
            not os.path.isfile(os.path.join(input_path, "merge")):
        shutil.move(os.path.join(input_path, "merge"),
                    os.path.join(output_path))
    else:
        raise AbnormalBehaviourError("FSTMerge generated folder doesn't exist")


def merge_with_IntelliMerge(input_path, output_path, logger):
    try:
        # Run IntelliMerge
        proc = subprocess.Popen("java -jar " +
                                os.path.join(path_prefix, IntelliMerge_executable_path) +
                                " " + "-d " +
                                os.path.join(input_path, "left") + " " +
                                os.path.join(input_path, "base") + " " +
                                os.path.join(input_path, "right") + " " +
                                "-o " + output_path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
		outs, errs = proc.communicate(timeout=MAX_WAITINGTIME_RESOLVE)
        if proc.returncode == 0:
            # Update logger
            logger.info("Finish IntelliMerge")
        else:
            # Failed to run JDime
            logger.info("Fail to run IntelliMerge")
            raise AbnormalBehaviourError("Fail to run IntelliMerge")
    except subprocess.TimeoutExpired:
        # Terminate the unfinished process
        proc.terminate()
        # Timeout occur
        # Update logger
        logger.error("Fail to run IntelliMerge in time")
        raise AbnormalBehaviourError("Fail to run IntelliMerge in time")
    finally:
        pass


def merge_with_AutoMerge(input_path, output_path):
    runProcess("java -jar " +
               os.path.join(path_prefix, AutoMerge_executable_path) +
               " " + "-o " + output_path + " -m structured -log info -f -S " +
               os.path.join(input_path, "left") + " " +
               os.path.join(input_path, "base") + " " +
               os.path.join(input_path, "right"))


def merge_with_summer(repo, leftSha, rightSha, baseSha, output_path):
	cmd = f'{summerPath} merge -C {repo} -l {leftSha} -r {rightSha} -b {baseSha} --worktree {output_path}'
	runProcess(cmd)


# merge two commits
def git_merge(right_parent, logger):
    # Use git to merge left and right
    # Assuming repository is currently at left version
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
        proc.terminate()
        # Failed to get result of git merge in time
        logger.error("Fail to run git merge in time")
        raise AbnormalBehaviourError("Fail to run git merge in time")
    finally:
        pass

# clean a folder content
def clean_folder(path, clean_logger):
    if os.path.exists(path):
        # destination exist
        if os.path.isdir(path):
            # destination is a directory
            try:
                for filename in os.listdir(path):
                    file_path = os.path.join(path, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                        # os.system("rm -rf " + file_path)
            except shutil.Error:
                clean_logger.error("remove folder error occurred")
                raise AbnormalBehaviourError("Certain error occur")
                exit(1)
            # Debugging code: Be cautious
            # except Exception as e:
            #     clean_logger.error("Unknown error")
            #     print(str(e))
            #     raise AbnormalBehaviourError("Certain error occur")
            #     exit(1)
        else:
            raise AbnormalBehaviourError("Path is a file instead of a folder")
    else:
        # Empty path, skip
        pass
		
		
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


def on_rm_error(func, path, excinfo):
	# path contains the path of the file that couldn't be removed
	# let's just assume that it's read-only and unlink it.
	if type(excinfo) is PermissionError and excinfo.errno == 13:
		os.chmod(path, stat.S_IWRITE)
		os.unlink(path)


def createBranchVersion(project_name, folderName):
	try:
		dst = os.path.join(path_prefix, workspace, folderName)
		shutil.rmtree(dst, onexc=on_rm_error)
		shutil.copytree(os.path.join(path_prefix, workspace, project_name), dst, symlinks=True)
	except shutil.Error as e:
		print(f'Error in creating the {folderName} folder:', file=sys.stderr)
		for arg in e.args[0]:
			print(arg[2], file=sys.stderr)
		exit(1)
	except IOError as e:
		print(f'Error in creating the {folderName} folder: ' + str(e), file=sys.stderr)
		exit(1)


def processExample(example):
	# Read merge scenario information
	project_url = example['repo_url']
	project_name = example['project_name']
	commit = {}
	commit['base'] = example['base_hash']
	commit['left'] = example['left_hash']
	commit['right'] = example['right_hash']
	commit['child'] = example['child_hash']
	file_path = example['conflicting_file']

	os.chdir(os.path.join(path_prefix, workspace))
	prepare_repo(os.path.join(path_prefix, workspace, project_name), project_url, commit['child'])

	resultFolder = os.path.join(path_prefix, workspace, 'result')
	if '--summer' in sys.argv:
		shutil.rmtree(os.path.join(resultFolder, 'summer'), onexc=on_rm_error)
		pathlib.Path(os.path.join(resultFolder, 'summer')).mkdir()
		commit['summer_mergeable'] = True
		try:
			merge_with_summer(os.path.join(path_prefix, workspace, project_name),
							  commit['left'], commit['right'], commit['base'],
							  os.path.join(resultFolder, 'summer'))
			commit['summer_solution_generation'] = True
			logger.info("summer solution generated")
		except:
			commit['summer_solution_generation'] = False

	exit(0)

	createBranchVersion(project_name, 'base')
	os.chdir(os.path.join(path_prefix, workspace, 'base'))
	Repo(os.getcwd()).git.reset('--hard', commit['base'])
	# git_reset_commit(commit['base'], logger)
	# Except the conflicting file, remove all other files in base version
	os.chdir(os.path.join(path_prefix, workspace, 'base'))
	for filename in glob.glob("**", recursive=True):
		if filename == file_path:
			logger.info("Found same name file in base version")
		if os.path.isfile(filename) and filename != file_path:
			os.remove(filename)
	logger.info("Complete deletion in base version")

	createBranchVersion(project_name, 'left')
	os.chdir(os.path.join(path_prefix, workspace, 'left'))
	Repo(os.getcwd()).git.reset('--hard', commit['left'])
	# git_reset_commit(commit['left'], logger)
	# Except the conflicting file, remove all other files in left version
	os.chdir(os.path.join(path_prefix, workspace, 'left'))
	for filename in glob.glob("**", recursive=True):
		if filename == file_path:
			logger.info("Found same name file in left version")
		if os.path.isfile(filename) and filename != file_path:
			os.remove(filename)
	logger.info("Complete deletion in left version")

	createBranchVersion(project_name, 'right')
	os.chdir(os.path.join(path_prefix, workspace, 'right'))
	Repo(os.getcwd()).git.reset('--hard', commit['right'])
	# git_reset_commit(commit['right'], logger)
	# Except the conflicting file, remove all other files in right version
	os.chdir(os.path.join(path_prefix, workspace, 'right'))
	for filename in glob.glob("**", recursive=True):
		if filename == file_path:
			logger.info("Found same name file in right version")
		if os.path.isfile(filename) and filename != file_path:
			os.remove(filename)
	logger.info("Complete deletion in right version")

	createBranchVersion(project_name, 'child')
	os.chdir(os.path.join(path_prefix, workspace, 'child'))
	Repo(os.getcwd()).git.reset('--hard', commit['child'])
	# git_reset_commit(commit['child'], logger)
	# Except the conflicting file, remove all other files in child version
	os.chdir(os.path.join(path_prefix, workspace, 'child'))
	for filename in glob.glob("**", recursive=True):
		if filename == file_path:
			logger.info("Found same name file in child version")
		if os.path.isfile(filename) and filename != file_path:
			os.remove(filename)
	logger.info("Complete deletion in child version")
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
	if os.path.exists(resultFolder):
		# Indicate previous clean up work is not completed
		logger.error("Found existing result folder. Clean up work not finished")
		shutil.rmtree(resultFolder, onexc=on_rm_error)
	pathlib.Path(resultFolder).mkdir()

	# Move the child version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'child'),
				resultFolder)
	# Move the git-merge version into result folder
	shutil.move(os.path.join(path_prefix, workspace, 'git-merge'),
				resultFolder)

	if '--fst-merge' in sys.argv:
		pathlib.Path(os.path.join(resultFolder, 'FSTMerge')).mkdir()
		commit['FSTMerge_mergeable'] = True
		try:
			merge_with_FSTMerge(os.path.join(path_prefix, workspace),
								os.path.join(resultFolder, 'FSTMerge'), logger)
			commit['FSTMerge_solution_generation'] = True
			logger.info("FSTMerge solution generated")
		except AbnormalBehaviourError as e:
			commit['FSTMerge_solution_generation'] = False

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

		if '--auto-merge' in sys.argv:
			pathlib.Path(os.path.join(resultFolder, 'AutoMerge')).mkdir()
			commit['AutoMerge_mergeable'] = True
			try:
				merge_with_AutoMerge(os.path.join(path_prefix, workspace),
									 os.path.join(resultFolder, 'AutoMerge'))
				commit['AutoMerge_solution_generation'] = True
				logger.info("AutoMerge solution generated")
			except AbnormalBehaviourError as e:
				commit['AutoMerge_solution_generation'] = False

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
logger.setLevel(logging.INFO)

if __name__ == '__main__':
	if '--help' in sys.argv:
		print('''
{0}

--help	show this help.
--log-file	specify the path of a log file. If this option is missing, log is not written to disk.
--path-prefix	the directory of ConflictBench. If this option is missing, the path is the parent of parent folder of {0}, which is {1}.
--total_list	the path to the file containing all examples. If this option is missing, the path is derived from --path-prefix.

--summer=`path`	run the summer tool located at `path`.
--summer	run the summer tool. The summer executable is expected to be found in the PATH environment variable.		
'''.format(sys.argv[0], pathlib.Path(__file__).parent.parent.resolve()))
		exit(0)

	try:
		i = sys.argv.index('--path-prefix')
		path_prefix = sys.argv[i + 1]
	except:
		path_prefix = pathlib.Path(__file__).parent.parent.resolve()

	runSummer = False
	for opt in sys.argv:
		if opt.startswith('--summer='):
			summerPath = opt[len('--summer='):]
			if not os.path.isfile(summerPath):
				print(f'The path to the summer executable "{summerPath}" is not valid.', file=sys.stderr)
				exit(1)
			runSummer = True
			break
	if summerPath is None:
		summerPath = 'summer'
	if runSummer is False:
		runSummer = '--summer' in sys.argv

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

	try:
		i = sys.argv.index('--total_list')
		totalListPath = sys.argv[i + 1]
	except:
		totalListPath = os.path.join(path_prefix, 'Data', "total_list.txt")

	if not os.path.isfile(totalListPath):
		print(f'The list of example files is not at {totalListPath}.', file=sys.stderr)
		print('Use option --path-prefix to specify the path prefix.', file=sys.stderr)
		print('Use option --total_list to directly specify the path to total_list.txt.', file=sys.stderr)
		exit(1)

	# Read total_list
	with open(totalListPath, 'r') as f:
		lines = f.readlines()
		total_list = []
		for line in lines:
			parts = line.split('\t')
			# Create a dictionary for each line
			item = {
				'repo_url': parts[0],
				'project_name': parts[1],
				'child_hash': parts[2],  # merge hash
				'left_hash': parts[3],
				'right_hash': parts[4],
				'base_hash': parts[5],
				'conflicting_file': parts[6].strip(),
				# Use strip to remove the newline character at the end of each line
			}
			total_list.append(item)

	for i in range(len(total_list)):
		logger.info("Start processing index " + str(i) + "\tproject " + total_list[i]['project_name'] + " commit " + total_list[i]['child_hash'])
		processExample(total_list[i])
