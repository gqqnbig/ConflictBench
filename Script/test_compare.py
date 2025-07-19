import os
import tempfile

import compare


def test_normalizeFile():
	sampleFile = tempfile.NamedTemporaryFile(delete_on_close=False)
	lines = [
		b'//preamble\n',
		b'\n',
		b'import b;\n',
		b'\n',
		b'import a;\n',
		b'\n',
		b'after\n',
		b'\n',
	]
	sampleFile.writelines(lines)
	sampleFile.close()

	outputFile = tempfile.NamedTemporaryFile(delete_on_close=False)
	compare.normalizeFile(sampleFile.name, outputFile.name)

	with open(outputFile.name, 'r', encoding='utf-8') as f:
		fileContent = f.read()
	outputFile.close()

	p1 = fileContent.find('//preamble')
	assert p1 != -1

	p2 = fileContent.find('import a;\nimport b;', p1)
	assert p2 != -1

	p3 = fileContent.find('after', p2)
	assert p3 != -1

	os.unlink(sampleFile.name)
	os.unlink(outputFile.name)
