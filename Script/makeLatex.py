import csv
import sys

if __name__ == '__main__':
	csv_file = sys.argv[-1]

	java_files = []
	javaZero = 0
	non_java_files = []
	nonJavaZero = 0

	with open(csv_file, newline='', encoding='utf-8') as f:
		reader = csv.DictReader(f)
		for row in reader:
			try:
				diff_size = int(row['diff size'])  # Filter: must be numeric
			except (ValueError, TypeError):
				continue  # skip rows with non-numeric or empty diff size

			repo = row['repo'].strip()
			file_path = row['conflicting file'].strip()

			if file_path.endswith(".java"):
				if diff_size == 0:
					javaZero += 1
					continue
				java_files.append((repo, diff_size))
			else:
				if diff_size == 0:
					nonJavaZero += 1
					continue
				non_java_files.append((repo, diff_size))

	# Sort by diff size ascending
	java_files.sort(key=lambda x: x[1])
	non_java_files.sort(key=lambda x: x[1])

	# Print Java files table
	print("Java Files (Top 5 by diff size)")
	print(f'{javaZero} are identical')
	for repo, size in java_files[:5]:
		print(r'\ShowDiffSize{' + repo + '}{' + str(size) + '}')

	print("\nNon-Java Files (Top 3 by diff size)")
	print(f'{nonJavaZero} are identical')
	for repo, size in non_java_files[:3]:
		print(r'\ShowDiffSize{' + repo + '}{' + str(size) + '}')
