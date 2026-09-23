Option Explicit

Dim shell, command
Set shell = CreateObject("WScript.Shell")

command = "cmd.exe /c ""C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\scripts\startmcp.bat"""
shell.Run command, 0, False
