# AGENTS.md - Early Warnings Weather Dashboard

## Build/Lint/Test Commands

### Running the Application
- **Start development server**: `python app.py` or `flask run`
- **Run with debug mode**: `python app.py` (debug=True by default)

### Dependencies
Install required packages:
```bash
pip install flask folium groq pandas requests geopandas python-dotenv
```

### Project Structure
- `app.py` - Main Flask application with routes
- `config.py` - Configuration management
- `models.py` - Data models and constants
- `services/` - Business logic services
  - `weather_service.py` - Weather data fetching and caching
  - `alert_service.py` - AI-powered alert generation
  - `map_service.py` - Interactive map generation
- `utils/` - Utility modules
  - `validation.py` - Input validation functions

### Testing
- No formal test suite exists
- Manual testing: Access http://localhost:5000 after starting the server
- Test endpoints: `/get_forecast/<province>/<district>/<days>`, `/generate_alerts`

### Linting & Code Quality
- No linting tools configured
- Recommended: `pip install flake8 black` then `flake8 app.py` or `black app.py`

## Code Style Guidelines

### Python Style
- **Imports**: Standard library first, then third-party, then local imports. One import per line.
- **Naming**: snake_case for variables/functions, PascalCase for classes, UPPER_CASE for constants
- **Line length**: Keep lines under 100 characters when possible
- **Docstrings**: Use triple quotes for function documentation
- **Error handling**: Use try/except blocks with specific exception types, log errors appropriately

### Flask-Specific Patterns
- **Route naming**: Use descriptive names like `@app.route("/get_forecast/<province>/<district>/<int:days>")`
- **JSON responses**: Use `jsonify()` for API responses
- **Template rendering**: Pass context variables clearly to `render_template()`

### Data Handling
- **File operations**: Use `with` statements for file handling, specify encoding="utf-8"
- **JSON handling**: Use `json.dump()` with `ensure_ascii=False` and `indent=2` for readability
- **DataFrame operations**: Use pandas for data manipulation, convert to dict for JSON responses

### Security & Best Practices
- **API keys**: Store sensitive keys in environment variables, never commit to repository
- **Input validation**: Validate user inputs, especially for file paths and API parameters
- **Caching**: Implement appropriate cache timeouts (currently 43200 seconds = 12 hours)
- **Error messages**: Don't expose internal errors to users, provide user-friendly messages

### File Organization
- **Static files**: Store in `static/` directory (weatherdata/, boundary/, images)
- **Templates**: Use Jinja2 templates in `templates/` directory
- **Data files**: Cache weather/alert data as JSON files with descriptive naming: `{type}_{days}_{province}_{district}.json`

### Code Structure
- **Functions**: Keep functions focused on single responsibilities
- **Constants**: Define constants at module level (like PROVINCES dict)
- **Global state**: Minimize global variables, prefer function parameters
- **Comments**: Add comments for complex logic, especially API integrations and data processing</content>
<parameter name="filePath">G:\AI Projects\projects\earlyWarnings\AGENTS.md