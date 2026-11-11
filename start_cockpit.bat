@echo off
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo Installiere Pakete (nur beim ersten Mal dauert das etwas) ...
%PY% -m pip install -q -r requirements.txt
echo.
echo Starte Unternehmer-Cockpit ... Der Browser oeffnet sich gleich.
echo Zum Beenden dieses Fenster schliessen oder Strg+C druecken.
start "" cmd /c "timeout /t 8 >nul & start http://localhost:8501"
%PY% -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
pause
