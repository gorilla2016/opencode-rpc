@echo off
setlocal
set "SCRIPT=C:\Users\orang\opencode-rpc\opencode-rpc.py"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%STARTUP%\opencode-rpc.vbs" echo Set s = CreateObject("WScript.Shell")
>> "%STARTUP%\opencode-rpc.vbs" echo s.Run "pythonw ""%SCRIPT%""", 0, False
echo Installed autostart: %STARTUP%\opencode-rpc.vbs
endlocal
