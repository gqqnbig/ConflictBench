# ConflictBench

To use this test bench on Windows, you should enable long path support because many Java repositories have paths more than 260 characters. In gpedit.msc, set `Computer Configuration > Administrative Templates > System > Filesystem > Enable Win32 long paths`. [ref](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation)




`ConflictBench`

├── `Logger`

│	 ├── textual_conflict.log

├── `Data`

│	 ├── project_record.txt

│	 ├── total_list.txt

│	 └── DataSheet.xlsx


├── `MergeTools`

│	 ├── `AutoMerge`

│	 ├── `FSTMerge`

│	 ├── `IntelliMerge`

│	 ├── `JDime`

│	 └── `KDiff3`

├── `Resource`

│	 ├── `output`

│	 └── `workspace`

├── `Script`

│	 └── script.txt

├── README.md

└── requirements.txt


`Logger` folder store log informaion during script running.

`Data` folder store the input total_list.txt, also store the project_record.txt to contain all information. DataSheet.xlsx is the manually checked sheet for all 180 merge scenarios.

`MergeTools` folder contain 5 merge tools used in this experiment.
FSTMerge requires Java 8.
AutoMerge requires JavaFX. Adoptium JDK may not work.[ref](https://github.com/adoptium/temurin-build/issues/577)

`Resource` folder contain 3 folders including `output`, `workspace` and `merge_scenarios`.
`merge_scenarios` folder stores all 180 merge scenarios. The download link is https://drive.google.com/file/d/1UyHKtQEyFiIcfi-Y1aEmmpNbOQns645M/view?usp=drive_link. There are 180 folders named with the project name in `merge_scenarios` folder. In each project folder, there is only one folder named with commit hash. The commit hash is developers’ merged version m in paper. In each commit folder, there are 8 folders. 4 folders are tool execution reuslts corresponding to FSTMerge/JDime/IntelliMerge/AutoMerge. 4 folders are origin versions include base/left/right/child. Only the conflicting file remained in these folders. All other files are removed.
`workspace` is temp folder during experiments.
`output` contain all experiment results.

`Script` folder contain python script to run this experiment.

NOTICE: 
1. Before running the script, update the variable `path_prefix` to your local repository path in `script.py`. `resume_experiment` is set to FALSE by default. If it's true, script will always read stored project_record.txt in Data folder.
2. `project_record.txt` is the key file to store all information. As the script running, `project_record.txt` will be updated and `output` folder will store experiment result.
3. `JDime` and `AutoMerge` need to install libgit2-1.1. Use command `apt install libgit2-1.1`
