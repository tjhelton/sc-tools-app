-- SafetyCulture Tools launcher
-- Compiled into a .app with: osacompile -o "SafetyCulture Tools.app" launch_app.applescript

on run
	set appRoot to do shell script "dirname " & quoted form of POSIX path of (path to me)
	
	-- Find python3
	set pythonPath to ""
	try
		set pythonPath to do shell script "export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH && command -v python3"
	end try
	
	if pythonPath is "" then
		display dialog "Python 3 is not installed." & return & return & "Download it from python.org/downloads and try again." buttons {"OK"} default button "OK" with icon caution with title "SafetyCulture Tools"
		return
	end if
	
	-- Launch in Terminal so the user can see output and close it to stop
	tell application "Terminal"
		activate
		set newTab to do script "cd " & quoted form of appRoot & " && if [ ! -d .venv ]; then echo 'Setting up (first run)...' && python3 -m venv .venv; fi && source .venv/bin/activate && if ! python3 -c 'import streamlit' 2>/dev/null; then echo 'Installing dependencies...' && pip install -r requirements.txt --quiet; fi && echo 'Starting SafetyCulture Tools...' && python3 -m streamlit run app/Home.py --server.headless true"
	end tell
end run
