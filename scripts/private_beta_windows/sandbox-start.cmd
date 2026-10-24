@echo off
set "NIGHTMERIT_KIT_CONTEXT_B64=%~1"
powershell.exe -NoProfile -Command "& ([ScriptBlock]::Create([IO.File]::ReadAllText('C:\NightMeritInput\Audit\controller.ps1')))"
if errorlevel 1 pause
