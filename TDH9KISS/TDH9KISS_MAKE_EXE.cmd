@echo off

rem # author  # https://github.com/dkxce/Tidradio-TD-H9
rem # version # v1.0.0.0

:begin
chcp 65001 >nul
set "PROCESS_NAME=tdh9kiss"

:iflaunched
tasklist /nh /fi "imagename eq %PROCESS_NAME%.exe" 2>nul | findstr /i "%PROCESS_NAME%" >nul
if %errorlevel% neq 0 goto build
echo Процесс %PROCESS_NAME% сейчас запущен.
set /p "choice=Остановить его и запустить сборку exe? [Y/N]: "
if /i "%choice%"=="Y" (
    powershell -Command "Stop-Process -Name %PROCESS_NAME% -Force"
	goto build
) else exit /b	

:build
@echo on
.venv\Scripts\create-version-file TDH9KISS.yaml --outfile TDH9KISS.txt
@rem .venv\Scripts\pyinstaller.exe  --version-file="TDH9KISS.txt" -i "TDH9KISS.ico" --noconsole --onefile main.py
.venv\Scripts\pyinstaller.exe  --clean --version-file="TDH9KISS.txt" -i "TDH9KISS.ico" --noconsole --onefile main.py
@del /Q TDH9KISS.txt
@move /Y dist\main.exe dist\tdh9kiss.exe
tools\upx.exe -9f dist\tdh9kiss.exe
@echo Сборка завершена
@pause

:end