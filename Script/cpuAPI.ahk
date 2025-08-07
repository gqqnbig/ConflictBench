#Requires AutoHotkey v2.0

SampleProcess(hProcess)
{

    ; Structures to hold file times
    FileTimeSize := 8  ; FILETIME is 64-bit
    ftSysKernel1:=Buffer(FileTimeSize)
    ftSysUser1:=Buffer(FileTimeSize)
    ftProcKernel1:=Buffer(FileTimeSize)
    ftProcUser1:=Buffer(FileTimeSize)
	ftSysIdle1 := Buffer(FileTimeSize)

	lpCreationTime:=Buffer(FileTimeSize)
	lpExitTime:=Buffer(FileTimeSize)

    ; First snapshot
    DllCall("GetSystemTimes", "Ptr", ftSysIdle1 , "Ptr", ftSysKernel1, "Ptr", ftSysUser1)
    DllCall("GetProcessTimes", "Ptr", hProcess, "Ptr", lpCreationTime, "Ptr", lpExitTime, "Ptr", ftProcKernel1, "Ptr", ftProcUser1)

	return [FileTimeToInt64(ftSysKernel1) + FileTimeToInt64(ftSysUser1), FileTimeToInt64(ftProcKernel1) + FileTimeToInt64(ftProcUser1)]
}

GetProcessCPUUsage(pid, interval := 1000) {
    static PROCESS_QUERY_INFORMATION := 0x0400
    static PROCESS_VM_READ := 0x0010

    ; Open handle to the process
    hProcess := DllCall("OpenProcess", "UInt", PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, "Int", false, "UInt", pid, "Ptr")
    if !hProcess
		return -1
    
	time1 := SampleProcess(hProcess)
    Sleep(interval)  ; Wait to measure delta
	time2 := SampleProcess(hProcess)

    DllCall("CloseHandle", "Ptr", hProcess)

    ; Convert FILETIME to integer (100-ns units)

    TotalSysDelta := time2[1] - time1[1]
    ProcDelta := time2[2] - time1[2]

    if (TotalSysDelta = 0)
        return 0

    ; CPU usage as a percentage
    return Round((ProcDelta / TotalSysDelta) * 100, 2)
}

FileTimeToInt64(ft) {
    return NumGet(ft, 0, "UInt") | (NumGet(ft, 4, "UInt") << 32)
}

