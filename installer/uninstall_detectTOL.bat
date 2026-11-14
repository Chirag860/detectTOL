@echo off
rem Removes the detectTOL shortcuts and launcher. The conda environment is kept unless you
rem answer y (it may be used for other work).
setlocal
del "%USERPROFILE%\Desktop\detectTOL.lnk" 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\detectTOL.lnk" 2>nul
rmdir /s /q "%LOCALAPPDATA%\detectTOL" 2>nul
echo Shortcuts and launcher removed.
set /p ANSWER=Also remove the conda environment "detecttol"? [y/N]
if /i "%ANSWER%"=="y" (
  for %%R in ("%USERPROFILE%\miniforge3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3") do (
    if exist "%%~R\Scripts\conda.exe" "%%~R\Scripts\conda.exe" env remove -y -n detecttol
  )
)
echo Done.
pause
