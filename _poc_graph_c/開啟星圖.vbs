' One-click launch CodeSextant code star-map GUI (no console window).
' Double-click this file. It opens the star-map in Edge/Chrome and the server
' auto-stops ~30s after you close the tab (no leftover process / port).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyExe = "C:\Python311\python.exe"
If Not fso.FileExists(pyExe) Then pyExe = "python.exe"
' set working dir to this folder, pass relative script name (avoid non-ASCII argv)
sh.CurrentDirectory = scriptDir
sh.Run Chr(34) & pyExe & Chr(34) & " start_stargraph.py", 0, False
