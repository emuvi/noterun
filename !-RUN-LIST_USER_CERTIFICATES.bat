@echo off
setlocal
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "SCRIPT_PY=%~dpn0.py"
set "TMP_DIR=%TEMP%"
if not defined TMP_DIR set "TMP_DIR=%~dp0"
set "ERR_FILE=%TMP_DIR%\%~n0_%RANDOM%_%RANDOM%.err.log"

if not exist "%SCRIPT_PY%" (
    echo.
    echo ============================================================
    echo [!] ATENCAO: Script Python nao encontrado!
    echo     Esperado: "%SCRIPT_PY%"
    echo ============================================================
    echo.
    pause
    endlocal & exit /b 1
)

set "PY_CMD=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py"
)

%PY_CMD% "%SCRIPT_PY%" %* 2>"%ERR_FILE%"
set "EXIT_CODE=%ERRORLEVEL%"

set "ERR_SIZE=0"
if exist "%ERR_FILE%" for %%A in ("%ERR_FILE%") do set "ERR_SIZE=%%~zA"
if not defined ERR_SIZE set "ERR_SIZE=0"

if %ERR_SIZE% GTR 0 (
    echo.
    echo ============================================================
    echo [!] ATENCAO: Ocorreram erros durante a execucao!
    echo     Verifique as mensagens abaixo:
    echo ============================================================
    type "%ERR_FILE%"
    echo ============================================================
    del /f /q "%ERR_FILE%" >nul 2>&1
    echo.
    pause
) else (
    if exist "%ERR_FILE%" del /f /q "%ERR_FILE%" >nul 2>&1
)

endlocal & exit /b %EXIT_CODE%
