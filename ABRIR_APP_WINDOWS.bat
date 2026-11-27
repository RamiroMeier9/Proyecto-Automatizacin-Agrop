@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo No se encontro Python.
        echo Instala Python 3.11 o posterior desde https://www.python.org/downloads/
        echo Durante la instalacion marca la opcion "Add Python to PATH".
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando el entorno de la aplicacion...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
echo Instalando o comprobando dependencias...
python -m pip install -e ".[app]"
if errorlevel 1 goto :error

python -m inta_forrajes.cli init-db
python -m inta_forrajes.cli import-manual

echo Abriendo la aplicacion. Para cerrarla, volve a esta ventana y presiona Ctrl+C.
python -m streamlit run streamlit_app.py
exit /b 0

:error
echo.
echo No se pudo iniciar la aplicacion. Copia el mensaje de error y envialo para revisarlo.
pause
exit /b 1
