@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PixelForge

rem --- Python (3.11 via le lanceur py si disponible, sinon python) ---
set "PYEXE=python"
py -3.11 --version >nul 2>&1 && set "PYEXE=py -3.11"
%PYEXE% --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python 3.11+ est introuvable. Installez-le depuis https://www.python.org/
    pause
    exit /b 1
)

rem --- Environnement virtuel et dependances backend (premiere fois seulement) ---
if not exist "backend\.venv\Scripts\python.exe" (
    echo Creation de backend\.venv ...
    %PYEXE% -m venv backend\.venv
    if errorlevel 1 goto :fail
)
if not exist "backend\.venv\.pixelforge-installed" (
    echo Installation du backend ...
    "backend\.venv\Scripts\python.exe" -m pip install -e "backend[dev]"
    if errorlevel 1 goto :fail
    echo ok> "backend\.venv\.pixelforge-installed"
)

rem --- Dependances frontend ---
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Node.js ^(npm^) est introuvable. Installez-le depuis https://nodejs.org/
    pause
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo Installation du frontend ...
    pushd frontend
    call npm install
    if errorlevel 1 ( popd & goto :fail )
    popd
)

rem --- Adresse de ComfyUI : .env si present, sinon valeur par defaut ---
if not defined PIXELFORGE_COMFY_URL (
    set "PIXELFORGE_COMFY_URL=http://127.0.0.1:8188"
    if exist ".env" (
        for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
            if /i "%%A"=="PIXELFORGE_COMFY_URL" set "PIXELFORGE_COMFY_URL=%%B"
        )
    )
)

curl -s -o NUL "%PIXELFORGE_COMFY_URL%/system_stats"
if errorlevel 1 (
    echo [AVERTISSEMENT] ComfyUI ne repond pas sur %PIXELFORGE_COMFY_URL%.
    echo Lancez-le ^(run_nvidia_gpu.bat^) pour generer des images, ou utilisez PIXELFORGE_FAKE_COMFY=1 ^(mode demo^).
)

rem --- Lancement : backend et frontend dans deux fenetres ---
start "PixelForge backend" cmd /k "backend\.venv\Scripts\python.exe -m pixelforge"
start "PixelForge frontend" /d "%~dp0frontend" cmd /k npm run dev
timeout /t 5 /nobreak >nul
start http://localhost:5173
exit /b 0

:fail
echo [ERREUR] L'installation a echoue.
pause
exit /b 1
