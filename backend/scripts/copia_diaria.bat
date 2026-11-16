@echo off
rem Hace la copia de seguridad diaria de la base de datos de DOMUX (TT-009).
rem Se usa desde el Programador de tareas de Windows. No lleva claves: la base de datos y la
rem carpeta de copias se leen del archivo backend\.env.
cd /d "%~dp0.."
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m scripts.copia_diaria %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m scripts.copia_diaria %*
) else (
    python -m scripts.copia_diaria %*
)
exit /b %ERRORLEVEL%
