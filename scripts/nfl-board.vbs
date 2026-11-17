Option Explicit
Dim sh, fso, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
cmd = """" & fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "nfl-board.cmd") & """"
sh.Run cmd, 0, False
