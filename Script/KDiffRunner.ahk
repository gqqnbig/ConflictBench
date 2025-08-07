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

CheckMergeResult(mainWindow)
{

	if IsSaveable('ahk_id ' . mainWindow)
	{
		send "^s"
		sleep 1000
		
		return
	}
	else
	{
		; file has conflicts
		ProcessClose(pid)
		ExitApp 1
	}
}

MergeOnce(mainWindow, begin)
{

	send "{F7}"

	sleep 1000
	
	;debugging
	;Exit

	While GetProcessCPUUsage(pid) > 2
	{}

	hwnd:=WinGetID('A')
	if CheckForModalDialog(hwnd)
	{
		title:=WinGetTitle(hwnd)
		if title = 'Starting Merge - KDiff3'
		{
			if begin
			{
				sleep 100
				send "!d"
				Tooltip('New merge starts')

				While GetProcessCPUUsage(pid) > 2
				{}
			}
			else
			{
				; The merge is a single file. It has been merged. 
				; A new round of merging starts.
				ProcessClose(pid)
				ExitApp 0
			}
		}
		else if InStr(title, 'Error')
		{
			message := GetDialogMessage('ahk_id ' . hwnd)
			if InStr(message, 'Select what to do')
			{
				; The file path conflict. 
				ProcessClose(pid)
				ExitApp 1
			}
		}
		else if InStr(title, 'Merge Complete')
		{
			; This message shows when there is a folder sturcture in the merging scope.
			ProcessClose(pid)
			ExitApp 0
		}
		else
			msgbox 'loop1' . title
	}
	else
		Tooltip('Continu merging')

	CheckMergeResult(mainWindow)
}

cmd:=quotePath(A_Args[1]) . ' ' . quotePath(A_Args[2]) . ' ' . quotePath(A_Args[3]) . ' ' . quotePath(A_Args[4]) . ' -o ' . quotePath(A_Args[5]) . ' -m --auto --cs ShowInfoDialogs=0 --cs FileAntiPattern=.git'

;msgbox cmd
pid:=0
run cmd,,, &pid

if ! WinWaitActive('Information - KDiff3 ' . 'ahk_pid ' . pid, , 5)
{
	msgbox 'failed to find KDiff window'
	ExitApp 1
}


send "{enter}"
;msgbox "Information window found"
sleep 1000

mainWindow:=WinGetID('ahk_pid ' . pid)

MergeOnce(mainWindow, true)
loop
{
	; MergeOnce will exit the program.
	MergeOnce(mainWindow, false)
}


