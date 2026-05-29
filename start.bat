@echo off
title ECHO Orchestrator
echo.
echo  =============================================
echo    ECHO Orchestrator wird gestartet ...
echo  =============================================
echo.

:: Zum Projektverzeichnis wechseln
cd /d "%~dp0"

:: Ollama sicherstellen
echo  [0/2] Starte Ollama ...
start "ECHO | Ollama" /min ollama serve
timeout /t 5 /nobreak > nul

:: Orchestrator Service starten (eigenes Fenster)
echo  [1/2] Starte Orchestrator Service ...
start "ECHO | Orchestrator" cmd /c "cd /d "%~dp0" && python main.py"

:: Warten bis der Service hochgefahren ist
echo  Warte auf Service-Start ...
timeout /t 4 /nobreak > nul

:: Chat UI starten
echo  [2/2] Starte Chat UI ...
python chat_ui.py

echo.
echo  Chat UI beendet.
pause
