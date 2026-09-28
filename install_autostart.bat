@echo off
REM ===========================================================
REM  ARGUS AI — kompyuter yonganda AVTO ishga tushishni o'rnatish
REM  (login bo'lganda avtomatik, konsolsiz ishga tushadi)
REM  Bir marta ishga tushiring (o'ng tugma -> Run as administrator).
REM ===========================================================
set TASK=ARGUS_AI
set VBS=%~dp0run_hidden.vbs

schtasks /Create /TN "%TASK%" /TR "wscript.exe \"%VBS%\"" /SC ONLOGON /RL HIGHEST /F
if %errorlevel%==0 (
  echo.
  echo [OK] Avto-start o'rnatildi.
  echo Kompyuter yonib login bo'lganda ARGUS AI o'zi (konsolsiz) ishga tushadi.
  echo Eslatma: monitor ulanmasa, Windows'da AVTO-LOGIN yoqilgan bo'lishi kerak.
) else (
  echo [XATO] O'rnatilmadi. Administrator sifatida ishga tushiring.
)
echo.
pause
