@echo off
setlocal

:: ==========================================
:: AUTENTICAZIONE REPO PRIVATA
:: Repo: github.com/lall0nz/4c-tool (privata)
:: Il token NON e' qui dentro: viene letto dal file .env locale (gitignorato),
:: riga:  var github_pat = "github_pat_...";
:: Cosi' questo .bat resta privo di segreti e committabile/distribuibile.
:: ==========================================
set "SCRIPT_DIR=%~dp0"

set "PAT="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[regex]::Match(([string](Get-Content -Raw -ErrorAction SilentlyContinue '%SCRIPT_DIR%.env')),'github_pat_[A-Za-z0-9_]+').Value"`) do set "PAT=%%P"
if not defined PAT (
    echo ERRORE: github_pat non trovato in .env
    echo Aggiungi questa riga al file .env nella cartella Scripts:
    echo     var github_pat = "github_pat_il_tuo_token";
    pause & exit /b 1
)
set "AUTH=Authorization='Bearer %PAT%'; Accept='application/vnd.github.raw'; 'User-Agent'='4c-updater'"

:: ==========================================
:: LINK DI DOWNLOAD (GitHub Contents API, repo privata)
:: ==========================================
set "URL_1=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_START.oajs?ref=main"
set "URL_2=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_UTILITIES.oajs?ref=main"
set "URL_3=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_REPAIRBENCH.oajs?ref=main"
set "URL_4=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_POSITIONS.oajs?ref=main"
set "URL_5=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_GUI.oajs?ref=main"
set "URL_6=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_FARM.oajs?ref=main"
set "URL_7=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_DOOM.oajs?ref=main"
set "URL_8=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_COMBAT_SYSTEM.oajs?ref=main"
set "URL_9=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_CHAMPION_RAIL.oajs?ref=main"
set "URL_10=https://api.github.com/repos/lall0nz/4c-tool/contents/beep.wav?ref=main"
set "URL_11=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_666_GUI.oajs?ref=main"
set "URL_12=https://api.github.com/repos/lall0nz/4c-tool/contents/COMPAGNONE_COVERAGE.oajs?ref=main"

:: ==========================================
:: CONFIGURAZIONE NOMI FILE DI DESTINAZIONE
:: ==========================================
set "FILE_1=%SCRIPT_DIR%COMPAGNONE_START.oajs"
set "FILE_2=%SCRIPT_DIR%COMPAGNONE_UTILITIES.oajs"
set "FILE_3=%SCRIPT_DIR%COMPAGNONE_REPAIRBENCH.oajs"
set "FILE_4=%SCRIPT_DIR%COMPAGNONE_POSITIONS.oajs"
set "FILE_5=%SCRIPT_DIR%COMPAGNONE_GUI.oajs"
set "FILE_6=%SCRIPT_DIR%COMPAGNONE_FARM.oajs"
set "FILE_7=%SCRIPT_DIR%COMPAGNONE_DOOM.oajs"
set "FILE_8=%SCRIPT_DIR%COMPAGNONE_COMBAT_SYSTEM.oajs"
set "FILE_9=%SCRIPT_DIR%COMPAGNONE_CHAMPION_RAIL.oajs"
set "FILE_10=%SCRIPT_DIR%beep.wav"
set "FILE_11=%SCRIPT_DIR%COMPAGNONE_666_GUI.oajs"
set "FILE_12=%SCRIPT_DIR%COMPAGNONE_COVERAGE.oajs"

:: Definizioni dei file di backup generati automaticamente
set "BACKUP_1=%FILE_1:.oajs= backup.oajs%"
set "BACKUP_2=%FILE_2:.oajs= backup.oajs%"
set "BACKUP_3=%FILE_3:.oajs= backup.oajs%"
set "BACKUP_5=%FILE_5:.oajs= backup.oajs%"
set "BACKUP_6=%FILE_6:.oajs= backup.oajs%"
set "BACKUP_7=%FILE_7:.oajs= backup.oajs%"
set "BACKUP_8=%FILE_8:.oajs= backup.oajs%"
set "BACKUP_9=%FILE_9:.oajs= backup.oajs%"
set "BACKUP_11=%FILE_11:.oajs= backup.oajs%"
set "BACKUP_12=%FILE_12:.oajs= backup.oajs%"

echo.
echo Avvio aggiornamento pacchetto script...
echo.

:: ------------------------------------------
:: FILE 1
:: ------------------------------------------
echo [1/12] Gestione COMPAGNONE_START.oajs...
if exist "%FILE_1%" (
    copy /Y "%FILE_1%" "%BACKUP_1%" >nul
    echo Backup creato per File 1.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_1%' -Headers @{%AUTH%} -OutFile '%FILE_1%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_START.oajs fallito.
    if exist "%BACKUP_1%" ( copy /Y "%BACKUP_1%" "%FILE_1%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 2
:: ------------------------------------------
echo [2/12] Gestione COMPAGNONE_UTILITIES.oajs...
if exist "%FILE_2%" (
    copy /Y "%FILE_2%" "%BACKUP_2%" >nul
    echo Backup creato per File 2.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_2%' -Headers @{%AUTH%} -OutFile '%FILE_2%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_UTILITIES.oajs fallito.
    if exist "%BACKUP_2%" ( copy /Y "%BACKUP_2%" "%FILE_2%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 3
:: ------------------------------------------
echo [3/12] Gestione COMPAGNONE_REPAIRBENCH.oajs...
if exist "%FILE_3%" (
    copy /Y "%FILE_3%" "%BACKUP_3%" >nul
    echo Backup creato per File 3.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_3%' -Headers @{%AUTH%} -OutFile '%FILE_3%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_REPAIRBENCH.oajs fallito.
    if exist "%BACKUP_3%" ( copy /Y "%BACKUP_3%" "%FILE_3%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 4 - COMPAGNONE_POSITIONS.oajs (Gestione speciale)
:: ------------------------------------------
echo [4/12] Controllo COMPAGNONE_POSITIONS.oajs...
if exist "%FILE_4%" (
    echo %FILE_4% gia presente.
    echo Salto il download per non sovrascrivere le tue posizioni della GUI.
) else (
    echo File non trovato. Download in corso...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_4%' -Headers @{%AUTH%} -OutFile '%FILE_4%'"
    if errorlevel 1 (
        echo ERRORE: download COMPAGNONE_POSITIONS.oajs fallito.
        pause & exit /b 1
    )
    echo Scaricato correttamente.
)
echo.

:: ------------------------------------------
:: FILE 5
:: ------------------------------------------
echo [5/12] Gestione COMPAGNONE_GUI.oajs...
if exist "%FILE_5%" (
    copy /Y "%FILE_5%" "%BACKUP_5%" >nul
    echo Backup creato per File 5.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_5%' -Headers @{%AUTH%} -OutFile '%FILE_5%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_GUI.oajs fallito.
    if exist "%BACKUP_5%" ( copy /Y "%BACKUP_5%" "%FILE_5%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 6
:: ------------------------------------------
echo [6/12] Gestione COMPAGNONE_FARM.oajs...
if exist "%FILE_6%" (
    copy /Y "%FILE_6%" "%BACKUP_6%" >nul
    echo Backup creato per File 6.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_6%' -Headers @{%AUTH%} -OutFile '%FILE_6%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_FARM.oajs fallito.
    if exist "%BACKUP_6%" ( copy /Y "%BACKUP_6%" "%FILE_6%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 7
:: ------------------------------------------
echo [7/12] Gestione COMPAGNONE_DOOM.oajs...
if exist "%FILE_7%" (
    copy /Y "%FILE_7%" "%BACKUP_7%" >nul
    echo Backup creato per File 7.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_7%' -Headers @{%AUTH%} -OutFile '%FILE_7%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_DOOM.oajs fallito.
    if exist "%BACKUP_7%" ( copy /Y "%BACKUP_7%" "%FILE_7%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 8
:: ------------------------------------------
echo [8/12] Gestione COMPAGNONE_COMBAT_SYSTEM.oajs...
if exist "%FILE_8%" (
    copy /Y "%FILE_8%" "%BACKUP_8%" >nul
    echo Backup creato per File 8.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_8%' -Headers @{%AUTH%} -OutFile '%FILE_8%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_COMBAT_SYSTEM.oajs fallito.
    if exist "%BACKUP_8%" ( copy /Y "%BACKUP_8%" "%FILE_8%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 9
:: ------------------------------------------
echo [9/12] Gestione COMPAGNONE_CHAMPION_RAIL.oajs...
if exist "%FILE_9%" (
    copy /Y "%FILE_9%" "%BACKUP_9%" >nul
    echo Backup creato per File 9.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_9%' -Headers @{%AUTH%} -OutFile '%FILE_9%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_CHAMPION_RAIL.oajs fallito.
    if exist "%BACKUP_9%" ( copy /Y "%BACKUP_9%" "%FILE_9%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 10 - beep.wav (Gestione speciale)
:: ------------------------------------------
echo [10/12] Controllo beep.wav...
if exist "%FILE_10%" (
    echo %FILE_10% gia presente.
    echo Salto il download per non sovrascrivere il file audio.
) else (
    echo File non trovato. Download in corso...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_10%' -Headers @{%AUTH%} -OutFile '%FILE_10%'"
    if errorlevel 1 (
        echo ERRORE: download beep.wav fallito.
        pause & exit /b 1
    )
    echo Scaricato correttamente.
)
echo.

:: ------------------------------------------
:: FILE 11
:: ------------------------------------------
echo [11/12] Gestione COMPAGNONE_666_GUI.oajs...
if exist "%FILE_11%" (
    copy /Y "%FILE_11%" "%BACKUP_11%" >nul
    echo Backup creato per File 11.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_11%' -Headers @{%AUTH%} -OutFile '%FILE_11%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_666_GUI.oajs fallito.
    if exist "%BACKUP_11%" ( copy /Y "%BACKUP_11%" "%FILE_11%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FILE 12 - COMPAGNONE_COVERAGE.oajs (pilot champ-spawn coverage)
:: ------------------------------------------
echo [12/12] Gestione COMPAGNONE_COVERAGE.oajs...
if exist "%FILE_12%" (
    copy /Y "%FILE_12%" "%BACKUP_12%" >nul
    echo Backup creato per File 12.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%URL_12%' -Headers @{%AUTH%} -OutFile '%FILE_12%'"
if errorlevel 1 (
    echo ERRORE: download COMPAGNONE_COVERAGE.oajs fallito.
    if exist "%BACKUP_12%" ( copy /Y "%BACKUP_12%" "%FILE_12%" >nul & echo Backup ripristinato. )
    pause & exit /b 1
)
echo Scaricato correttamente.
echo.

:: ------------------------------------------
:: FINE PROCESSO
:: ------------------------------------------
echo.
echo ==========================================
echo Operazione completata con successo!
echo Tutti i file idonei sono stati aggiornati.
echo ==========================================
echo.
pause
