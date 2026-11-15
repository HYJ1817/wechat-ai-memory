Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = strPath & "\.venv-gui\Scripts\pythonw.exe"
appPath = strPath & "\app_modern.py"

If Not fso.FileExists(pythonwPath) Then
    MsgBox "Cannot find Python virtualenv in .venv-gui." & vbCrLf & "Please run start.cmd first to initialize dependencies.", vbCritical, "WeChat AI Memory"
    WScript.Quit 1
End If

WshShell.CurrentDirectory = strPath
WshShell.Run """" & pythonwPath & """ """ & appPath & """", 0, False
