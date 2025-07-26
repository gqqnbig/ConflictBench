import logging
import os
import pathlib
import subprocess
import sys

from git import Repo

import dataset
import optionUtils

logger = logging.getLogger('diff_logger')
logger.setLevel(logging.INFO)


def normalizeFile(filePath, normalizedFile):
	with open(filePath, 'r', encoding='utf-8') as f:
		lines = f.readlines()

	before_imports = []
	imports = []

	i = 0
	while i < len(lines):
		line = lines[i]
		if line.startswith('import '):
			break
		before_imports.append(line)
		i += 1

	while i < len(lines):
		line = lines[i]
		if len(line.strip()) > 0 and line.startswith('import ') is False:
			break
		imports.append(line)
		i += 1

	after_imports = lines[i:]

	# Sort import lines alphabetically
	imports.sort()

	# Combine all parts
	normalized_content = before_imports + imports + after_imports

	with open(normalizedFile, 'w', encoding='utf-8') as f:
		f.writelines(normalized_content)


def ProcessExample(baseFolderActual, baseFolderExpected, subjectRepo: dataset.SubjectRepo):
	folderExpected = os.path.join(baseFolderExpected, subjectRepo.repoName)
	mergedFile = subjectRepo.getMergedFile(baseFolderExpected)
	fileExpected = os.path.join(folderExpected, mergedFile)
	if os.path.exists(fileExpected) is False:
		raise Exception("File " + fileExpected + " doesn't exist")

	folderActual = os.path.join(baseFolderActual, subjectRepo.repoName)
	fileActual = os.path.join(folderActual, mergedFile)
	if os.path.exists(fileActual) is False:
		logger.info("File name error: File " + fileActual + " doesn't exist")
		return

	if fileActual.endswith('.java'):
		p = fileActual.rfind('.')
		normalized = fileActual[0:p] + '-normalized' + fileActual[p:]
		# if os.path.exists(normalized) is False:
		normalizeFile(fileActual, normalized)
		fileActual = normalized

	if fileExpected.endswith('.java'):
		p = fileExpected.rfind('.')
		normalized = fileExpected[0:p] + '-normalized' + fileExpected[p:]
		# if os.path.exists(normalized) is False:
		normalizeFile(fileExpected, normalized)
		fileExpected = normalized

	cmd = f'git diff --no-index --ignore-all-space  -- {fileActual} {fileExpected}'
	try:
		proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
		stdout, stderr = proc.communicate()
		if len(stdout) > 0:
			logger.info(f'Merged file does not fully matched actual file. Diff size is {len(stdout)}. Command is {cmd}')
		else:
			logger.info('Fully matched')
	except:
		logger.error(f'Failed to run {cmd}')


if __name__ == '__main__':
	if '--help' in sys.argv:
		print('''
{0}

--help	show this help.
--log-file file	
specify the path of a log file. If this option is missing, log is not written to disk.


'''.format(sys.argv[0]) + optionUtils.getHelp())
		exit(0)

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

	baseFolderExpected = os.path.join(opt.path_prefix, 'Resource/workspace')
	baseFolderActual = os.path.join(opt.path_prefix, 'Resource/workspace/result/summer')

	for i in opt.evaluationRange:
		logger.info(f"Start verifying project {i} {opt.dataset[i].repoName}")
		ProcessExample(baseFolderActual, baseFolderExpected, opt.dataset[i])
