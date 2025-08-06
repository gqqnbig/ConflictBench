#!/usr/bin/env python3

import csv
import logging
import os
import subprocess
import sys
from typing import List


import dataset
import optionUtils

logger = logging.getLogger('diff_logger')
logger.setLevel(logging.INFO)


def normalizeFile(filePath, normalizedFile):
	with open(filePath, 'r', encoding='utf-8', errors='ignore') as f:
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


def processExample(baseFolderActual, baseFolderExpected, subjectRepo: dataset.SubjectRepo) -> List:
	'''

	:param baseFolderActual:
	:param baseFolderExpected:
	:param subjectRepo:
	:return:  csvFields ('repo', 'conflicting file', 'diff size')
	'''
	csvFields = [subjectRepo.repoName, subjectRepo.conflictingFile, '-']

	folderExpected = os.path.join(baseFolderExpected, subjectRepo.repoName)
	mergedFile = subjectRepo.getMergedFile(baseFolderExpected)
	fileExpected = os.path.join(folderExpected, mergedFile)
	folderActual = os.path.join(baseFolderActual, subjectRepo.repoName)
	fileActual = os.path.join(folderActual, mergedFile)
	if os.path.exists(fileExpected) is False:
		logger.warning("File " + fileExpected + " doesn't exist. The file may be deleted in the merge commit.")
		if os.path.exists(fileActual) is False:
			logger.info('Fully matched')
		else:
			logger.info(f'Merged file exists at {fileActual}.')
		return csvFields

	if os.path.exists(fileActual) is False:
		logger.info("File name error: File " + fileActual + " doesn't exist")
		return csvFields

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

	cmd = f'git diff --exit-code --no-index --ignore-blank-lines --ignore-all-space -- {fileActual} {fileExpected}'
	try:
		# On POSIX, if args is a string, the string is interpreted as the name or path of the program to execute.
		# On the other hand, the Windows API natively expects a string. So it's fine to pass the program path with arguments as one string to Popen().
		isPosix = sys.platform == 'linux'
		proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=isPosix)
		stdout, stderr = proc.communicate()
		if proc.returncode == 0:
			csvFields[2] = 0
			logger.info('Fully matched')
		elif proc.returncode == 1:
			stdout = stdout.decode('utf-8', errors='ignore')
			csvFields[2] = len(stdout)
			logger.info(f'Merged file does not fully match actual file. Diff size is {len(stdout)}. Command is {cmd}')
		else:
			stderr = stderr.decode('utf-8', errors='ignore')
			logger.error(f'Failed to run {cmd}: ' + stderr)
	except:
		logger.error(f'Failed to run {cmd}')

	return csvFields


if __name__ == '__main__':
	if '--help' in sys.argv:
		print('''
{0}

--help	show this help.
--merger str
The name of the merger, not path.

--log-file file	
specify the path of a log file. If this option is missing, log is not written to disk.

--csv file
Write a CSV report.

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

	try:
		i = sys.argv.index('--csv')
		arg = sys.argv[i + 1]
		# the csv module does its own newline handling.
		csvfile = open(arg, 'w', newline='')
		csvWriter = csv.writer(csvfile)

		csvWriter.writerow(['repo', 'conflicting file', 'diff size'])
	except:
		csvfile = None
		csvWriter = None

	baseFolderExpected = os.path.join(opt.path_prefix, 'Resource/workspace')

	try:
		i = sys.argv.index('--merger')
		baseFolderActual = os.path.join(opt.path_prefix, 'Resource/workspace/result/', sys.argv[i + 1])
	except:
		print('Option --merger is required.', file=sys.stderr)
		exit(1)

	for i in opt.evaluationRange:
		logger.info(f"Start verifying project {i} {opt.dataset[i].repoName}")
		csvFields = processExample(baseFolderActual, baseFolderExpected, opt.dataset[i])
		if csvWriter is not None:
			csvWriter.writerow(csvFields)

	if csvfile is not None:
		csvfile.close()
