@echo off
setlocal enabledelayedexpansion

REM Directory setup
set APP_DIR=%USERPROFILE%\.payment_update_system
set CURRENT_DIR=%CD%

echo ===== Payment Update System Installation =====

REM Check if we're already in the app directory
if "%CURRENT_DIR%"=="%APP_DIR%" (
    echo Already in the application directory.
) else (
    echo Creating application directory if it doesn't exist...
    if not exist "%APP_DIR%" mkdir "%APP_DIR%"
    
    REM Copy the entire project structure more reliably
    echo Copying project files to %APP_DIR%...
    robocopy "%CURRENT_DIR%" "%APP_DIR%" /E /NFL /NDL /NJH /NJS /nc /ns /np
    if %ERRORLEVEL% GEQ 8 (
        echo Error copying files. Installation failed.
        exit /b 1
    )
)

REM Change to the app directory
cd /d "%APP_DIR%"

REM Install uv if not present
echo Checking for uv installation...
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing uv package manager...
    powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; Invoke-WebRequest -Uri https://astral.sh/uv/install.ps1 -OutFile uv-installer.ps1; ./uv-installer.ps1"
    
    REM Update PATH for current session
    for /f "tokens=*" %%i in ('powershell -Command "[Environment]::GetEnvironmentVariable('PATH', 'User')"') do set USER_PATH=%%i
    set PATH=%USERPROFILE%\.local\bin;%PATH%
    set PATH=%USER_PATH%;%PATH%
)

REM Verify uv installation
uv --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install uv. Please check your internet connection and try again.
    exit /b 1
) else (
    echo Successfully installed uv package manager.
)

REM Check/install Python using uv
echo Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python not found. Installing Python via uv...
    uv pip install python==3.11
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install Python. Please check your internet connection and try again.
        exit /b 1
    ) else (
        echo Python installed successfully.
    )
)

REM Create or recreate virtual environment 
echo Setting up virtual environment...
if exist ".venv" (
    echo Virtual environment already exists. Checking if it works...
    if not exist ".venv\Scripts\activate.bat" (
        echo Virtual environment seems corrupted. Recreating...
        rmdir /S /Q .venv
        uv venv .venv
    )
) else (
    echo Creating new virtual environment...
    uv venv .venv
)

REM Activate the virtual environment
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment. Please try reinstalling.
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
if exist "requirements.txt" (
    uv pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install dependencies. Please check your internet connection and try again.
        exit /b 1
    )
) else (
    echo Warning: requirements.txt not found. Dependencies may not be installed correctly.
)

REM Create logs directory
echo Creating logs directory...
if not exist "logs" mkdir logs
echo Log directory created at: %APP_DIR%\logs

REM Create a .env file if not present
if not exist ".env" (
    echo Creating default .env file...
    (
        echo # Email configuration
        echo EMAIL_SERVER=imap.gmail.com
        echo EMAIL_USER=your_email@gmail.com
        echo EMAIL_PASS=your_app_password
        echo SMTP_SERVER=smtp.gmail.com
        echo SMTP_PORT=465
        echo SMTP_USE_SSL=true
        echo # Stripe configuration
        echo STRIPE_API_KEY=your_stripe_key
        echo # NLP configuration
        echo NLP_API_KEY=your_anthropic_key
        echo # System configuration
        echo CONFIDENCE_THRESHOLD=0.9
    ) > .env
    
    echo.
    echo IMPORTANT: You need to edit the .env file with your actual credentials.
    echo.
    echo To edit the .env file, run this command after installation:
    echo notepad "%APP_DIR%\.env"
    echo.
    pause
)

echo.
echo Installation complete! You can now run the application with:
echo cd "%APP_DIR%" ^& .venv\Scripts\activate.bat ^& python main.py
echo.
echo Would you like to run the application now? (Y/N)
choice /C YN
if %ERRORLEVEL% EQU 1 (
    echo Starting the Payment Update System...
    python main.py
) else (
    echo You can run the application later by navigating to the directory and running main.py
)

exit /b 0