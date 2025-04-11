@echo off 
:check 
timeout /t 60 /nobreak 
1
del temp.txt 
if %count% equ 0 ( 
  echo 程序已结束运行，自动重启... 
  start "" venv\Scripts\pythonw.exe deepseek_gui.py 
) 
goto check 
