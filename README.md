# SafetyCulture Tools

A Streamlit-based app and Python script collection for SafetyCulture API operations. Provides tools for bulk management of templates, sites, issues, and other SafetyCulture resources.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the app
streamlit run app/Home.py
```

## 📁 Available Scripts

> **💡 Each script has its own README with detailed setup instructions, input formats, and usage examples. Click any script link below to view its complete documentation.**

### Actions
- **[delete_actions/](scripts/actions/delete_actions/)** - Delete SafetyCulture actions in bulk (batches of 300)
- **[delete_action_schedules/](scripts/actions/delete_action_schedules/)** - Delete action schedules with efficient async pagination

### Assets
- **[export_assets/](scripts/assets/export_assets/)** - High-performance asset export to CSV
- **[export_asset_types/](scripts/assets/export_asset_types/)** - Export asset type definitions
- **[update_assets/](scripts/assets/update_assets/)** - Bulk update assets from CSV
- **[delete_assets/](scripts/assets/delete_assets/)** - Archive-then-delete assets with colored output

### Courses
- **[assign_courses/](scripts/courses/assign_courses/)** - Assign training courses to sites in bulk

### Groups
- **[create_groups/](scripts/groups/create_groups/)** - Create SafetyCulture groups
- **[export_group_assignees/](scripts/groups/export_group_assignees/)** - Export group assignee information

### Inspections
- **[archive_inspections/](scripts/inspections/archive_inspections/)** - Bulk archive inspections with rate limiting
- **[complete_inspections/](scripts/inspections/complete_inspections/)** - Bulk complete inspections
- **[delete_inspections/](scripts/inspections/delete_inspections/)** - Permanently delete inspections in bulk
- **[export_inspection_location_changes/](scripts/inspections/export_inspection_location_changes/)** - Export address field changes from revision history
- **[export_inspection_pdfs/](scripts/inspections/export_inspection_pdfs/)** - Bulk export inspection PDFs
- **[unarchive_inspections/](scripts/inspections/unarchive_inspections/)** - Bulk unarchive inspections
- **[update_inspection_site/](scripts/inspections/update_inspection_site/)** - Configure inspection-site relationships

### Issues
- **[export_issue_relations/](scripts/issues/export_issue_relations/)** - Export issue relationship data to CSV
- **[export_issue_public_links/](scripts/issues/export_issue_public_links/)** - Generate public sharing links for issues

### Organizations
- **[export_contractor_companies/](scripts/organizations/export_contractor_companies/)** - Export contractor company records to CSV

### Sites
- **[create_sites/](scripts/sites/create_sites/)** - Create SafetyCulture sites with hierarchy support
- **[delete_sites/](scripts/sites/delete_sites/)** - Delete SafetyCulture sites in bulk
- **[export_sites_inactive/](scripts/sites/export_sites_inactive/)** - Identify and export inactive sites
- **[update_site_users/](scripts/sites/update_site_users/)** - Bulk update user site assignments

### Templates
- **[archive_templates/](scripts/templates/archive_templates/)** - Archive SafetyCulture templates in bulk
- **[export_template_access_rules/](scripts/templates/export_template_access_rules/)** - Export template permission matrices
- **[export_template_questions/](scripts/templates/export_template_questions/)** - Export template questions and structure

### Users
- **[deactivate_users/](scripts/users/deactivate_users/)** - Deactivate user accounts in bulk
- **[export_user_custom_fields/](scripts/users/export_user_custom_fields/)** - Export user custom field data

### Admin Tools
- **[nuke_account/](scripts/nuke_account/)** - ⚠️ Comprehensive account cleanup tool (use with extreme caution)

## 🛠️ Development

### Code Quality
This project uses automated linting and formatting tools. **All linting commands must be run from the `contribution_tools/` directory**:

```bash
cd contribution_tools/
make lint      # Check code quality
make fix       # Auto-fix formatting issues
make help      # See all available commands
```

### Pre-commit Hooks
Automatically format and lint code before commits:

```bash
cd contribution_tools/
make pre-commit
```

### GitHub Actions
- Automated code quality checks on all pull requests
- Linting and formatting validation
- Ensures consistent code standards

## 📋 Prerequisites

- **Python 3.8+** with pip
- **SafetyCulture API Token** - [Get yours here](https://developer.safetyculture.com/reference/getting-started)
- **API Access** - Appropriate permissions for your use case

## 🔧 Dependencies

Install all required dependencies for the scripts:
```bash
pip install -r requirements.txt
```

This installs:
- **pandas** - CSV data processing and manipulation
- **requests** - HTTP requests to SafetyCulture API
- **aiohttp** - Async HTTP requests (for concurrent processing scripts)
- **tqdm** - Progress bars for long-running operations

## 📖 Usage Patterns

### Standard Workflow
1. Install dependencies: `pip install -r requirements.txt`
2. Navigate to desired script directory
3. Set API token in `main.py` or environment variable
4. Prepare `input.csv` (if required)
5. Run `python main.py`
6. Check output files

### Authentication Methods
- **Token in script**: `TOKEN = 'your-token-here'` (most scripts)
- **Environment variable**: `export SC_API_TOKEN="your-token-here"` (advanced scripts)

## 📊 Input/Output Formats

### Standard Input
Most scripts expect `input.csv` with relevant IDs or parameters. See individual script READMEs for specific formats.

### Standard Output
- CSV files with processing results
- Timestamped output directories (for complex scripts)
- Terminal progress logging

## ⚠️ Important Notes

- **Security**: Never commit API tokens or sensitive data
- **Testing**: Always test with small datasets first
- **Irreversible**: Many operations (delete, archive) cannot be undone
- **Rate Limits**: Scripts include appropriate delays and retry logic

## 📚 API Documentation

- [SafetyCulture API Reference](https://developer.safetyculture.com/reference/)
- [Getting Started Guide](https://developer.safetyculture.com/reference/getting-started)

## 🤝 Contributing

See the [contribution guide](contribution_tools/CONTRIBUTE.md) for development setup and code quality tools.

## 📄 License

This project is provided as-is for SafetyCulture API automation. Use responsibly and in accordance with SafetyCulture's terms of service.
