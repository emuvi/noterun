@echo off
setlocal
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "SCRIPT_PY=%~dpn0.py"
for /f "tokens=2-4 delims=/ " %%%%a in ('date /t') do (set "DATE_PART=%%%%c%%%%a%%%%b")
for /f "tokens=1-2 delims=/:" %%%%a in ('time /t') do (set "TIME_PART=%%%%a%%%%b")
for /f "tokens=3 delims=/:" %%%%a in ('time /t') do (set "SECONDS_PART=%%%%a")
set "TIMESTAMP=%DATE_PART%_%TIME_PART%%SECONDS_PART%"
set "ERR_FILE=%CD%\%~n0_%TIMESTAMP%.log"

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
if not defined EXIT_CODE set "EXIT_CODE=0"

set "ERR_SIZE=0"
if exist "%ERR_FILE%" for %%%%A in ("%ERR_FILE%") do set "ERR_SIZE=%%%%~zA"
if not defined ERR_SIZE set "ERR_SIZE=0"

if %EXIT_CODE% NEQ 0 (
    echo.
    echo ============================================================
    echo [!] ATENCAO: Ocorreram erros durante a execucao!
    echo     Codigo de saida: %EXIT_CODE%
    if %ERR_SIZE% GTR 0 (
        echo     Verifique as mensagens abaixo:
        echo ============================================================
        type "%ERR_FILE%"
    )
    echo ============================================================
    echo.
    pause
) else (
    if exist "%ERR_FILE%" del /f /q "%ERR_FILE%" >nul 2>&1
)

endlocal & exit /b %EXIT_CODE%
