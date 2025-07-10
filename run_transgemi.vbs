Set WshShell = CreateObject("WScript.Shell")
' 0 = hidden window, True = wait for the process to finish
WshShell.Run "pythonw.exe .\scrtrans_winocr.py", 0, True