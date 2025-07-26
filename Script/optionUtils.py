import os
import pathlib
import sys
import typing

import dataset


class Options:
	dataset: typing.List[dataset.SubjectRepo]

	def __init__(self):
		self.dataset = None
		self.evaluationRange = None
		try:
			i = sys.argv.index('--path-prefix')
			self.path_prefix = sys.argv[i + 1]
		except:
			self.path_prefix = pathlib.Path(__file__).parent.parent.resolve()

	def LoadDataset(self):
		try:
			i = sys.argv.index('--total_list')
			totalListPath = sys.argv[i + 1]
		except:
			totalListPath = os.path.join(self.path_prefix, 'Data', "total_list.txt")
		if not os.path.isfile(totalListPath):
			print(f'The list of example files is not at {totalListPath}.', file=sys.stderr)
			print('Use option --path-prefix to specify the path prefix.', file=sys.stderr)
			print('Use option --total_list to directly specify the path to total_list.txt.', file=sys.stderr)
			exit(1)

		with open(totalListPath, 'r') as f:
			lines = f.readlines()
			total_list = []
			for line in lines:
				parts = line.strip().split('\t')
				# Create a dictionary for each line
				item = dataset.SubjectRepo()
				item.repoUrl = parts[0]
				item.repoName = parts[1]
				item.mergeCommit = parts[2]
				item.leftCommit = parts[3]
				item.rightCommit = parts[4]
				item.baseCommit = parts[5]
				item.conflictingFile = parts[6]

				total_list.append(item)

		self.dataset = total_list

	def LoadRange(self):
		try:
			i = sys.argv.index('--range')
			value = sys.argv[i + 1]
			s = value.find('..')
			if s == -1:
				print(f'{value} is not a valid value for option --range. ".." must present.', file=sys.stderr)
				exit(1)
			if s == 0:
				evaluateFrom = 0
			else:
				evaluateFrom = int(value[0:s])
			if s == len(value) - 2:
				evaluateTo = len(self.dataset)
			else:
				evaluateTo = int(value[s + 2:])
		except ValueError as ex:
			evaluateFrom = 0
			evaluateTo = len(self.dataset)

		self.evaluationRange = range(evaluateFrom, evaluateTo)


def getHelp():
	return \
'''
--path-prefix folder
the directory of ConflictBench. If this option is missing, the path is {0}.

--total_list file
the path to the file containing all examples. If this option is missing, the path is derived from --path-prefix.

--range	n1..n2
run experiments against examples from n1, inclusive to n2, exclusive. n1 starts at 0. If this option is missing, run all examples.	
'''.format(pathlib.Path(__file__).parent.parent.resolve())
