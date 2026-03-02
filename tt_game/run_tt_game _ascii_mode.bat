@echo off
cd /d "%~dp0"

:: Check if the file exists before attempting to open it
if exist "commands.txt" (
    start "" "commands.txt"
) else (
    echo [Notice] commands.txt not found, skipping open.
)

:: Run Python program
python tt_game.py --ascii  ::Ascii characters

pause
