import os

from git import Repo


def _findRenamedFile(file, commit1, commit2, repo_path):
	repo = Repo(repo_path)

	# Use git diff with --name-status and -M to detect renames
	diff_output = repo.git.diff(f'{commit1}', f'{commit2}', name_status=True, find_renames=True)

	# Each line has format like:
	# R100    old/path/file.txt    new/path/file_renamed.txt
	for line in diff_output.splitlines():
		parts = line.strip().split('\t')
		if parts[0].startswith('R') and len(parts) == 3:
			_, old_path, new_path = parts
			if old_path == file:
				return new_path

	return file


class SubjectRepo:
	def __init__(self):
		self.repoUrl = None
		self.repoName = None
		self.baseCommit = None
		self.leftCommit = None
		self.rightCommit = None
		self.mergeCommit = None
		self.conflictingFile = None
		self._mergedFile = None

	def getMergedFile(self, baseFolder) -> str:
		"""
		Merged file is usually the same as the conflicting file, but a resolver may choose to rename this file.
		:return:
		"""
		if self._mergedFile is None:
			self._mergedFile = _findRenamedFile(self.conflictingFile, self.baseCommit, self.mergeCommit, os.path.join(baseFolder, self.repoName))

		return self._mergedFile
