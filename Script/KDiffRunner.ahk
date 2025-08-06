#Warn

quotePath(p)
{
	if InStr(p, " ")
		return '"' . p . '"'
	else
		return p
}

cmd:=quotePath(A_Args[1]) . ' ' . quotePath(A_Args[2]) . ' ' . quotePath(A_Args[3]) . ' ' . quotePath(A_Args[4]) . ' -o ' . quotePath(A_Args[5])
	. ' -m --auto --cs ShowInfoDialogs=0 --cs FileAntiPattern=.git'

;msgbox cmd
pid:=0
run cmd,,, &pid

if WinWaitActive('Information - KDiff3 ' . 'ahk_pid' . pid, , 5)
{
	send "{enter}"
	;msgbox "Information window found"
	sleep 1000
	send "{F7}"
	WinWaitActive('Starting Merge ' . 'ahk_pid' . pid, , 2)
	; start merging
	send "!d"

	if WinWaitActive('Error ' . 'ahk_pid' . pid, , 2)
	{
		; error in merging
		ProcessClose(pid)
		exit 1
	}
	
	send "^s"
	sleep 1000
	ProcessClose(pid)
}
else
	msgbox "not found"

;WinWaitActive("B:\ ahk_pid " pid, , 5)
