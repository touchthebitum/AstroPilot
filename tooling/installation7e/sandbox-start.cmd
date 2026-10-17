@echo off
if /I not "%USERNAME%"=="WDAGUtilityAccount" goto refuse
if not exist "C:\NightMeritInput\kit.json" goto refuse
set "NIGHTMERIT_LAB=%TEMP%\NightMeritInstallationTest"
if exist "%NIGHTMERIT_LAB%" goto refuse
mkdir "%NIGHTMERIT_LAB%"
robocopy "C:\NightMeritInput" "%NIGHTMERIT_LAB%" /E /XD RESULTATS COPIES-ISOLEES /XF TEST-ISOLE-GENERE.wsb /R:0 /W:0
if errorlevel 8 goto refuse
cd /d "%NIGHTMERIT_LAB%"
"TestController\TestController.exe"
if errorlevel 1 pause
exit /b
:refuse
echo Test non valide. Aucune installation sur le PC habituel.
pause
exit /b 1
