@echo off
REM Dois cliques no Windows Explorer para instalar.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python instalar.py
) else (
  echo Python nao encontrado. Instale o Python 3 e rode de novo.
)
echo.
pause
