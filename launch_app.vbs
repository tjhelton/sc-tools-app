' SafetyCulture Tools — Windows Launcher (Hidden)
' Double-click this file to start the app without a command window.

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Check if Python is available
returnCode = objShell.Run("cmd /c python --version", 0, True)
If returnCode <> 0 Then
    MsgBox "Python is not installed." & vbCrLf & vbCrLf & _
           "Download it from python.org/downloads and try again.", _
           vbExclamation, "SafetyCulture Tools"
    WScript.Quit
End If

' Run the launcher in a hidden window
objShell.Run "cmd /c cd /d """ & strPath & """ && launch_app.bat", 0, False
