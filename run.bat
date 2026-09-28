@echo off
REM ==========================================================
REM  ARGUS AI - jonli haydovchi nazorati
REM  Ishga tushirish: shu faylni ikki marta bosing
REM  Chiqish: kamera oynasida 'q' yoki ESC
REM ==========================================================
cd /d "%~dp0"
"C:\sdv\Scripts\python.exe" -u "%~dp0app.py" %*
pause
