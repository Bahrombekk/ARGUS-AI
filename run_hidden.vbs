' ARGUS AI — konsolsiz (yashirin) ishga tushirish.
' pythonw.exe oyna/konsol ochmaydi. Avto-start shu faylni chaqiradi.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyExe  = "C:\sdv\Scripts\pythonw.exe"      ' <-- muhit boshqa joyda bo'lsa shuni o'zgartiring

sh.CurrentDirectory = appDir
sh.Run """" & pyExe & """ """ & appDir & "\app.py""", 0, False
