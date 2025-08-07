#Requires AutoHotKey >=2.0
#include Acc.ahk
#include cpuAPI.ahk

#Warn All
#Warn LocalSameAsGlobal, Off

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

IsSaveable(winTitle)
{
	; Get the dialog window
	mainWindow := Acc.ElementFromHandle(winTitle)
	toolBar := mainWindow.FindElement({Role: 22})
	saveButton := toolBar[2]
	STATE_SYSTEM_UNAVAILABLE:=0x1
	return !(saveButton.State & STATE_SYSTEM_UNAVAILABLE)
}


GetDialogMessage(winTitle)
{

	try {
		; Get the dialog window
		oDialog := Acc.ElementFromHandle(winTitle)
		
		; Look for text/static elements that contain the message
		; Usually dialog content is in elements with Role "text" or "static text"
		oTextElement := oDialog.FindElement({Role: 41})  ; Role 42 = ROLE_STATICTEXT
		
		if (oTextElement) {
			dialogContent := oTextElement.Name
			return dialogContent
		}
	} catch Error as e {
		return ''
	}

}

cmd:=quotePath(A_Args[1]) . ' ' . quotePath(A_Args[2]) . ' ' . quotePath(A_Args[3]) . ' ' . quotePath(A_Args[4]) . ' -o ' . quotePath(A_Args[5]) . ' -m --auto --cs ShowInfoDialogs=0 --cs FileAntiPattern=.git'

;msgbox cmd
pid:=0
run cmd,,, &pid

if ! WinWaitActive('Information - KDiff3 ' . 'ahk_pid' . pid, , 5)
{
	msgbox 'failed to find KDiff window'
	exit 1
}

send "{enter}"
;msgbox "Information window found"
sleep 1000
send "{F7}"

Loop {
	cpu := GetProcessCPUUsage(pid)
	tooltip cpu
	if cpu > 2
		continue

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
		else if InStr(title, 'Error')
		{
			message := GetDialogMessage('ahk_id ' . hwnd)
			if InStr(message, 'Select what to do')
			{
				; The file path conflict. 
				ProcessClose(pid)
				exit 1
			}
		}
		else
			msgbox 'loop1' . title
	}
	else
		break
}


; there is no more dialog. KDiff is on its main window.
sleep 1000

if IsSaveable('ahk_id ' . hwnd)
{
	send "^s"
	sleep 1000
	
	loop {
		cpu := GetProcessCPUUsage(pid)
		tooltip cpu
		if cpu > 2
			continue
		else
			break
	}
	
	ProcessClose(pid)
	exit 0
	
}
else
{
	; file has conflicts
	ProcessClose(pid)
	exit 1
}

