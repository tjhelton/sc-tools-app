-- SafetyCulture Tools launcher
-- Compiled into a .app with: osacompile -o "SafetyCulture Tools.app" launch_app.applescript
-- Then restore the custom icon: cp AppIcon.icns "SafetyCulture Tools.app/Contents/Resources/"

on run
	-- Resolve the repo root (parent directory of the .app bundle)
	set appBundle to POSIX path of (path to me)
	set appRoot to do shell script "dirname " & quoted form of appBundle

	-- Verify Python 3 is available
	set pythonPath to ""
	try
		set pythonPath to do shell script "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH && command -v python3"
	end try

	if pythonPath is "" then
		display dialog "Python 3 is not installed." & return & return & "Download it from python.org/downloads and try again." buttons {"OK"} default button "OK" with icon caution with title "SafetyCulture Tools"
		return
	end if

	-- Show a notification on first run (venv setup can take a minute)
	try
		do shell script "test -d " & quoted form of (appRoot & "/.venv")
	on error
		display notification "Setting up for first use — this may take a minute..." with title "SafetyCulture Tools"
	end try

	-- Build the setup + launch command (runs silently, no Terminal window)
	set shellCmd to "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
	set shellCmd to shellCmd & " && cd " & quoted form of appRoot
	set shellCmd to shellCmd & " && if [ ! -d .venv ]; then python3 -m venv .venv; fi"
	set shellCmd to shellCmd & " && . .venv/bin/activate"
	set shellCmd to shellCmd & " && if ! python3 -c 'import streamlit; import webview' 2>/dev/null; then pip install -r requirements.txt --quiet; fi"
	set shellCmd to shellCmd & " && python3 launcher.py"

	do shell script shellCmd
end run
