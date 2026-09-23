Option Explicit

' ===============================================================
' CvingTrade25X Hidden Startup Launcher
' Put ONLY this VBS file/shortcut in Windows Startup folder.
' Do NOT put the BAT directly in Startup, otherwise CMD can appear.
' ===============================================================

Dim WshShell, FSO
Dim scriptDir, projectRoot, parentDir, logDir, startupLog
Dim candidates, i, launcher, cmd

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
parentDir = FSO.GetParentFolderName(scriptDir)

' Default project path. Change this only if your project moved.
projectRoot = "C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"

' If this VBS is stored in/near the project folder, auto-detect the root.
If FSO.FileExists(scriptDir & "\backend\app.py") Then projectRoot = scriptDir
If FSO.FileExists(parentDir & "\backend\app.py") Then projectRoot = parentDir

logDir = projectRoot & "\logs"
Call EnsureFolder(logDir)
If Not FSO.FolderExists(logDir) Then
  logDir = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\CvingTrade25X\logs"
  Call EnsureFolder(logDir)
End If

startupLog = logDir & "\cvingtrade25x_startup_events.log"

candidates = Array( _
  scriptDir & "\start_flask_cvingtrade25x.bat", _
  scriptDir & "\start_flask_cvingtrade25x_FIXED.bat", _
  projectRoot & "\start_flask_cvingtrade25x.bat", _
  projectRoot & "\start_flask_cvingtrade25x_FIXED.bat" _
)

launcher = ""
For i = 0 To UBound(candidates)
  If FSO.FileExists(candidates(i)) Then
    launcher = candidates(i)
    Exit For
  End If
Next

If launcher = "" Then
  Call WriteLog("[VBS_ERROR] Launcher BAT not found. scriptDir=" & scriptDir & " projectRoot=" & projectRoot)
  WScript.Quit 1
End If

WshShell.CurrentDirectory = FSO.GetParentFolderName(launcher)
cmd = """" & WshShell.ExpandEnvironmentStrings("%ComSpec%") & """ /d /c call """ & launcher & """ --hidden"

Call WriteLog("[VBS_INFO] Hidden startup launch begin. launcher=" & launcher)
Call WriteLog("[VBS_INFO] command=" & cmd)

' 0 = hidden window. False = do not block Windows login/startup.
WshShell.Run cmd, 0, False

Call WriteLog("[VBS_INFO] Hidden startup launch submitted.")
WScript.Quit 0

Sub EnsureFolder(ByVal folderPath)
  On Error Resume Next
  If Len(folderPath) > 0 Then
    If Not FSO.FolderExists(folderPath) Then FSO.CreateFolder(folderPath)
  End If
  On Error GoTo 0
End Sub

Sub WriteLog(ByVal message)
  Dim lf
  On Error Resume Next
  Set lf = FSO.OpenTextFile(startupLog, 8, True)
  lf.WriteLine Now & " " & message
  lf.Close
  On Error GoTo 0
End Sub
