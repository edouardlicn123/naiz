@echo off
REM run_wsl2.bat — Launch the patched wxnp21kai under WSL2 on Windows.
REM
REM This avoids the unpatched Windows NP21X64W (black screen after entering the
REM game). The Naiz repo's Linux build flow applies tools/np2kaipatch/*.patch and
REM compiles a patched wxnp21kai; we simply run it inside WSL2 and let WSLg show
REM the window on the Windows desktop.
REM
REM Requires (one-time, inside WSL2 default distro):
REM   bash start.sh deps   && bash start.sh watcom && bash start.sh pip
REM   && bash start.sh np2kai
REM
REM Usage:
REM   run_wsl2.bat            (default game: demo-a2)
REM   run_wsl2.bat animatest (specific game)
setlocal
set GAME=%1
if "%GAME%"=="" set GAME=demo-a2

REM Normalize repo path (drop trailing backslash for wslpath).
set REPO=%~dp0
if "%REPO:~-1%"=="\" set REPO=%REPO:~0,-1%

wsl.exe bash -lc "cd \"$(wslpath -u '%REPO%')\" && bash makegame.sh build %GAME% && bash makegame.sh test %GAME%"
endlocal
