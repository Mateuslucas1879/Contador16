@echo off
rem Gera o executavel do Windows (pasta dist\Contador16). Rode com o ambiente virtual ativo.
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name Contador16 --hidden-import serial.tools.list_ports_windows main.py
echo.
echo Pronto: dist\Contador16\Contador16.exe
