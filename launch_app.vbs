Option Explicit

Dim shell, fso, scriptDir, appScript, exiftoolPath, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
appScript = fso.BuildPath(scriptDir, "drone_images_to_kmz.py")

If fso.FileExists(fso.BuildPath(scriptDir, "exiftool.exe")) Then
    exiftoolPath = fso.BuildPath(scriptDir, "exiftool.exe")
ElseIf fso.FileExists(fso.BuildPath(fso.BuildPath(scriptDir, "exiftool"), "exiftool.exe")) Then
    exiftoolPath = fso.BuildPath(fso.BuildPath(scriptDir, "exiftool"), "exiftool.exe")
Else
    exiftoolPath = ""
End If

command = "cmd /c cd /d """ & scriptDir & """ && (pyw -3 """ & appScript & """ --gui"
If fso.FileExists(fso.BuildPath(fso.BuildPath(scriptDir, ".venv"), "Scripts\pythonw.exe")) Then
    command = "cmd /c cd /d """ & scriptDir & """ && (""" & fso.BuildPath(fso.BuildPath(scriptDir, ".venv"), "Scripts\pythonw.exe") & """ """ & appScript & """ --gui"
ElseIf fso.FileExists(fso.BuildPath(fso.BuildPath(scriptDir, ".venv"), "Scripts\python.exe")) Then
    command = "cmd /c cd /d """ & scriptDir & """ && (""" & fso.BuildPath(fso.BuildPath(scriptDir, ".venv"), "Scripts\python.exe") & """ """ & appScript & """ --gui"
Else
    command = "cmd /c cd /d """ & scriptDir & """ && (pyw -3 """ & appScript & """ --gui"
End If
If exiftoolPath <> "" Then
    command = command & " --exiftool """ & exiftoolPath & """"
End If
command = command & " || pythonw """ & appScript & """ --gui"
If exiftoolPath <> "" Then
    command = command & " --exiftool """ & exiftoolPath & """"
End If
command = command & " || py -3 """ & appScript & """ --gui"
If exiftoolPath <> "" Then
    command = command & " --exiftool """ & exiftoolPath & """"
End If
command = command & " || python """ & appScript & """ --gui"
If exiftoolPath <> "" Then
    command = command & " --exiftool """ & exiftoolPath & """"
End If
command = command & ")"

shell.Run command, 0, False
