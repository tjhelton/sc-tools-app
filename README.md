# SafetyCulture Tools

A collection of bulk operations tools for the SafetyCulture platform. Includes a Streamlit web app with a guided UI and 30+ standalone CLI scripts for managing actions, assets, inspections, sites, templates, users, and more via the SafetyCulture API.

## Download & Install

### Mac

> **[Download for Mac](https://github.com/tjhelton/issue_tracker_demo/archive/refs/heads/main.zip)**

1. Download and extract the ZIP
2. Double-click **SafetyCulture Tools.app**
3. The app opens in a native window — first launch sets up dependencies and may take a minute

If the `.app` doesn't work on your system, double-click `launch_app.command` instead.

### Windows

> **[Download for Windows](https://github.com/tjhelton/issue_tracker_demo/archive/refs/heads/main.zip)**

1. Download and extract the ZIP
2. Double-click **launch_app.vbs**
3. The app opens in a native window — first launch sets up dependencies and may take a minute

If the `.vbs` doesn't work on your system, double-click `launch_app.bat` instead.

### Prerequisites

- **Python 3.8+** — pre-installed on most Macs; [download for Windows](https://www.python.org/downloads/)
- **SafetyCulture API Token** — [Get yours here](https://developer.safetyculture.com/reference/getting-started)

### Manual Setup (Linux / advanced)

```bash
python3 -m pip install -r requirements.txt
streamlit run app/Home.py
```

## How It Works

The web app provides a point-and-click interface for bulk SafetyCulture operations:

1. Paste your API token on the home page and validate it
2. Pick a category from the sidebar (Actions, Assets, Inspections, etc.)
3. Choose a tool from the tabs within that category
4. Upload a CSV if the tool requires one (each tool shows the required columns)
5. Click Run and watch the progress
6. Download the results when complete

Your API token is stored only for the browser session and is never saved to disk.

## Available Tools

| Category | Tools | Operations |
|---|---|---|
| **Actions** | 5 | Export, update status, delete actions, manage schedules |
| **Assets** | 4 | Export assets/types, bulk update fields, delete |
| **Inspections** | 7 | Archive, unarchive, complete, delete, export PDFs and location changes |
| **Sites** | 4 | Create, delete, find inactive sites, manage user access |
| **Templates** | 3 | Archive, export access rules and questions |
| **Users** | 2 | Deactivate accounts, export custom field data |
| **Courses** | 1 | Assign training courses to sites |
| **Groups** | 2 | Create groups, export member details |
| **Issues** | 2 | Export public links and relationships |
| **Organizations** | 1 | Export contractor company records |
| **Schedules** | 2 | Export and update legacy schedules |

## CLI Scripts

Each tool is also available as a standalone Python script in the [scripts/](scripts/) directory. Every script has its own README with input format, usage, and examples.

```bash
cd scripts/inspections/archive_inspections/
# Edit main.py to set your API token, prepare input.csv
python main.py
```

## Important Notes

- **Always test with small datasets first** — many operations (delete, archive) cannot be undone
- **Never commit API tokens** — the `.gitignore` is configured to keep secrets out of the repo
- Scripts include built-in rate limiting, retry logic, and progress tracking

## API Documentation

- [SafetyCulture API Reference](https://developer.safetyculture.com/reference/)
- [Getting Started Guide](https://developer.safetyculture.com/reference/getting-started)

## Contributing

See the [contribution guide](contribution_tools/CONTRIBUTE.md) for development setup, linting, and code quality tools.
