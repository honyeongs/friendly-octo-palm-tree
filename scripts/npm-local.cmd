@echo off
set "PATH=%~dp0..\.tools;%PATH%"
node "%~dp0..\.tools\package\bin\npm-cli.js" %*
