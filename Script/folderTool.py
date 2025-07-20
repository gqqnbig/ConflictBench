#!/usr/bin/env python3
import pathlib
import sys
import subprocess

from git import Repo

import dataset
import optionUtils


def diff_BaseToLeft(folder, repo: dataset.SubjectRepo):
	subprocess.Popen([r'C:\Program Files\TortoiseGit\bin\TortoiseGitProc.exe', '/command:showcompare',
					  '/revision1:' + repo.baseCommit,
					  '/revision2:' + repo.leftCommit],
					 cwd=folder,
					 stdin=None, stdout=None, stderr=None, close_fds=True, creationflags=subprocess.DETACHED_PROCESS)


def diff_BaseToRight(folder, repo: dataset.SubjectRepo):
	subprocess.Popen([r'C:\Program Files\TortoiseGit\bin\TortoiseGitProc.exe', '/command:showcompare',
					  '/revision1:' + repo.baseCommit,
					  '/revision2:' + repo.rightCommit],
					 cwd=folder,
					 stdin=None, stdout=None, stderr=None, close_fds=True, creationflags=subprocess.DETACHED_PROCESS)


def runAction(folder, repo: dataset.SubjectRepo):
	match sys.argv[-2]:
		case '--diff-base-to-left':
			diff_BaseToLeft(folder, repo)
		case '--diff-base-to-right':
			diff_BaseToRight(folder, repo)
		case _:
			print(f'{sys.argv[-2]} is not --diff-base-to-left or --diff-base-to-right.', file=sys.stderr)
			input()
			exit(1)


if __name__ == '__main__':
	folder = sys.argv[-1]

	repo = Repo(folder, search_parent_directories=True)

	repoName = pathlib.Path(repo.working_dir).name

	opt = optionUtils.Options()
	opt.LoadDataset()

	for example in opt.dataset:
		if example.repoName == repoName:
			runAction(folder, example)
			exit(0)

	print(f'Repository {repoName} is not found.', file=sys.stderr)
	input()
	exit(1)
