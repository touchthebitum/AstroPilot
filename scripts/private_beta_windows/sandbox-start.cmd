@echo off
set "NIGHTMERIT_KIT_CONTEXT_B64=%~1"
set "NIGHTMERIT_OPEN_DATA_TRANSFER=0"
if "%~2"=="1" set "NIGHTMERIT_OPEN_DATA_TRANSFER=1"
powershell.exe -NoProfile -Command "& ([ScriptBlock]::Create([IO.File]::ReadAllText('C:\NightMeritInput\Audit\controller.ps1')))"
if errorlevel 1 pause
