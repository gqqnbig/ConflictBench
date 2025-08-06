#Requires AutoHotKey >=2.0
#Warn

quotePath(p)
{
	if InStr(p, " ")
		return '"' . p . '"'
	else
		return p
}

CheckForModalDialog(hwnd) 
{
	style := WinGetStyle(hwnd)
	isDialog := (style & 0x80000000) && (style & 0x00C00000) ; WS_POPUP + WS_CAPTION

	if isDialog {
		; Get the parent or owner window of the active window
		parentWin := DllCall("GetWindow", "Ptr", hwnd, "UInt", 4, "Ptr") ; GW_OWNER = 4

		if parentWin && (hwnd != parentWin) {
			isOwnerDisabled := !DllCall("IsWindowEnabled", "Ptr", parentWin)

			if isOwnerDisabled {
				;ToolTip("Modal dialog detected:`n" WinGetTitle(hwnd))
				return true
			}
		}
	}

    ;ToolTip("No modal dialog detected.")
    return false
}

cmd:=quotePath(A_Args[1]) . ' ' . quotePath(A_Args[2]) . ' ' . quotePath(A_Args[3]) . ' ' . quotePath(A_Args[4]) . ' -o ' . quotePath(A_Args[5]) . ' -m --auto --cs ShowInfoDialogs=0 --cs FileAntiPattern=.git'

;msgbox cmd
pid:=0
run cmd,,, &pid

if WinWaitActive('Information - KDiff3 ' . 'ahk_pid' . pid, , 5)
{
	send "{enter}"
	;msgbox "Information window found"
	sleep 1000
	send "{F7}"

	Loop {
		sleep 1000

		hwnd:=WinGetID('A')
		if CheckForModalDialog(hwnd)
		{
			title:=WinGetTitle(hwnd)
			if title = 'Dialog - KDiff3'
				continue
			else if title = 'Starting Merge - KDiff3'
			{
				sleep 100
				send "!d"
			}
			else
				msgbox 'loop1' . title
		}
		else
			break
	}

	; there is no more dialog. KDiff is on its main window.
	sleep 1000
	send "^s"
	sleep 1000
	; Merge one more time
	send '{F7}'
	
	Loop {
		sleep 1000

		hwnd:=WinGetID('A')
		if CheckForModalDialog(hwnd)
		{
			title:=WinGetTitle(hwnd)
			if title == 'Merge Complete - KDiff3'
			{
				send '{enter}'
				sleep 500				
				ProcessClose(pid)
				exit 0
			}
			else if title = 'Starting Merge - KDiff3'
			{
				; already merged
				ProcessClose(pid)
				exit 0
			}
			else
				msgbox "loop2" . title
		}
		else
			break
	}
}
else
	msgbox "not found"

;WinWaitActive("B:\ ahk_pid " pid, , 5)
