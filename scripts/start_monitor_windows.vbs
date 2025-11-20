' EdgePilot Usage Monitor - Windows Startup Script
' This script starts the usage monitor silently in the background

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the script's directory and navigate to EdgePilot root
strScriptPath = WScript.ScriptFullName
strScriptDir = objFSO.GetParentFolderName(strScriptPath)
strRootDir = objFSO.GetParentFolderName(strScriptDir)

' Path to the Python script
strMonitorScript = strRootDir & "\tools\usage_monitor.py"

' Check if settings.json exists and usage alerts are enabled
strSettingsFile = strRootDir & "\data\settings.json"
If objFSO.FileExists(strSettingsFile) Then
    Set objFile = objFSO.OpenTextFile(strSettingsFile, 1)
    strSettings = objFile.ReadAll
    objFile.Close

    ' Simple check if usage_alerts_enabled is true
    If InStr(strSettings, """usage_alerts_enabled"": true") > 0 Then
        ' Find pythonw.exe (hidden Python interpreter)
        strPythonw = ""

        ' Try common Python locations
        strPython1 = "pythonw.exe"
        strPython2 = "C:\Python39\pythonw.exe"
        strPython3 = "C:\Python310\pythonw.exe"
        strPython4 = "C:\Python311\pythonw.exe"
        strPython5 = "C:\Python312\pythonw.exe"

        ' Try to find pythonw in PATH first
        On Error Resume Next
        objShell.Run strPython1 & " --version", 0, True
        If Err.Number = 0 Then
            strPythonw = strPython1
        End If
        On Error GoTo 0

        ' If pythonw not found in PATH, try to find python in PATH and construct pythonw path
        If strPythonw = "" Then
            On Error Resume Next
            Set objExec = objShell.Exec("where python")
            If Err.Number = 0 Then
                strPythonPath = objExec.StdOut.ReadLine()
                If strPythonPath <> "" Then
                    strPythonw = objFSO.GetParentFolderName(strPythonPath) & "\pythonw.exe"
                    If Not objFSO.FileExists(strPythonw) Then
                        strPythonw = ""
                    End If
                End If
            End If
            On Error GoTo 0
        End If

        ' If we found pythonw, start the monitor
        If strPythonw <> "" Then
            strCommand = """" & strPythonw & """ """ & strMonitorScript & """ start"
            objShell.Run strCommand, 0, False
        End If
    End If
End If

Set objFSO = Nothing
Set objShell = Nothing
