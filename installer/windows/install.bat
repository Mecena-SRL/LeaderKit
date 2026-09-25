@echo off
rem LeaderKit - installazione per l'utente corrente (Windows). NON ANCORA TESTATO.
setlocal
set "HERE=%~dp0"
set "FUSION=%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion"
if /I "%~1"=="--uninstall" (
  del /Q "%FUSION%\Scripts\Utility\LeaderKit.py" 2>nul
  del /Q "%FUSION%\Templates\LeaderKit.drfx" 2>nul
  rmdir /S /Q "%FUSION%\LeaderKit\leaderkit" 2>nul
  rmdir /S /Q "%FUSION%\LeaderKit\presets" 2>nul
  echo LeaderKit rimosso. I preset utente restano in "%FUSION%\LeaderKit\presets-user".
  goto :end
)
mkdir "%FUSION%\Scripts\Utility" 2>nul
mkdir "%FUSION%\Templates" 2>nul
mkdir "%FUSION%\LeaderKit\presets-user" 2>nul
rmdir /S /Q "%FUSION%\LeaderKit\leaderkit" 2>nul
rmdir /S /Q "%FUSION%\LeaderKit\presets" 2>nul
xcopy /E /I /Y /Q "%HERE%payload\LeaderKit" "%FUSION%\LeaderKit" >nul
copy /Y "%HERE%payload\Scripts\Utility\LeaderKit.py" "%FUSION%\Scripts\Utility\LeaderKit.py" >nul
copy /Y "%HERE%LeaderKit.drfx" "%FUSION%\Templates\LeaderKit.drfx" >nul
echo LeaderKit installato in "%FUSION%".
echo Riavvia DaVinci Resolve, poi: Workspace ^> Scripts ^> LeaderKit
:end
pause
