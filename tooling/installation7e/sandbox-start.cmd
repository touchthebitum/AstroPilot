@echo off
if /I not "%USERNAME%"=="WDAGUtilityAccount" goto refuse
if not exist "C:\NightMeritInput\kit.json" goto refuse
if not exist "C:\NightMeritResults" goto refuse
set "NIGHTMERIT_BOOT_LOG=C:\NightMeritResults\demarrage-sandbox-%RANDOM%-%RANDOM%.log"
echo [%DATE% %TIME%] Sandbox demarree, copie du kit en preparation. > "%NIGHTMERIT_BOOT_LOG%"
set "NIGHTMERIT_LAB=%TEMP%\NightMeritInstallationTest"
if exist "%NIGHTMERIT_LAB%" goto refuse
mkdir "%NIGHTMERIT_LAB%"
robocopy "C:\NightMeritInput" "%NIGHTMERIT_LAB%" /E /XD RESULTATS COPIES-ISOLEES /XF TEST-ISOLE-GENERE.wsb /R:0 /W:0 /NP /NFL /NDL >> "%NIGHTMERIT_BOOT_LOG%" 2>&1
if errorlevel 8 goto refuse
echo [%DATE% %TIME%] Copie terminee, lancement du controleur. >> "%NIGHTMERIT_BOOT_LOG%"
cd /d "%NIGHTMERIT_LAB%"
"TestController\TestController.exe" >> "%NIGHTMERIT_BOOT_LOG%" 2>&1
set "NIGHTMERIT_EXIT=%ERRORLEVEL%"
echo [%DATE% %TIME%] Controleur termine, code %NIGHTMERIT_EXIT%. >> "%NIGHTMERIT_BOOT_LOG%"
if not "%NIGHTMERIT_EXIT%"=="0" pause
exit /b %NIGHTMERIT_EXIT%
:refuse
echo Test non valide. Aucune installation sur le PC habituel.
if defined NIGHTMERIT_BOOT_LOG echo [%DATE% %TIME%] Demarrage refuse ou copie incomplete. >> "%NIGHTMERIT_BOOT_LOG%"
pause
exit /b 1
