import os
import tempfile

import compare


def test_normalizeFile():
	sampleFile = tempfile.NamedTemporaryFile(delete_on_close=False)
	sampleFile.write(b'import b;\nimport a;\n')
	sampleFile.close()

	outputFile = tempfile.NamedTemporaryFile(delete_on_close=False)
	compare.normalizeFile(sampleFile.name, outputFile.name)

	with open(outputFile.name, 'r', encoding='utf-8') as f:
		fileContent = f.read()
	outputFile.close()

	assert fileContent == 'import a;\nimport b;\n'

	os.unlink(sampleFile.name)
	os.unlink(outputFile.name)
