# AGENTS.md - Early Warnings Weather Dashboard

## Build/Lint/Test Commands
- **Install deps**: `pip install -r requirements.txt`
- **Run app**: `python app.py` or `flask run`
- **Run all tests**: `pytest tests/ -v --cov=. --cov-report=term`
- **Run single test**: `pytest tests/test_endpoints.py::TestFlaskEndpoints::test_index_get -v`
- **Run tests with coverage**: `pytest tests/ -v --cov=. --cov-report=xml --cov-report=html --cov-report=term`
- **Lint**: `flake8 . --max-line-length=100 --exclude=.git,__pycache__,.pytest_cache,.venv,venv`
- **Format**: `black . --line-length=100 --exclude='/(\.git|__pycache__|\.pytest_cache|\.venv|venv)/'`
- **Security scan**: `bandit -r . --exclude .git,__pycache__,.pytest_cache,.venv,venv`
- **Safety check**: `safety check`

## Code Style Guidelines
- **Imports**: Standard library → third-party → local. One per line. Use `from typing import` for type hints.
- **Naming**: snake_case (functions/vars), PascalCase (classes), UPPER_CASE (constants)
- **Types**: Use type hints for function parameters and return values (Dict, List, Optional, etc.)
- **Line length**: 100 chars max (enforced by black)
- **Docstrings**: Triple quotes for functions, describe purpose, args, and return values
- **Error handling**: Specific exceptions, log with context, user-friendly messages
- **Flask patterns**: Use `jsonify()` for API responses, validate inputs, CORS properly configured
- **Security**: Environment variables for secrets, input validation, no hardcoded credentials
- **File ops**: `with` statements, `encoding="utf-8"`, `ensure_ascii=False` for JSON
- **Structure**: Single responsibility functions, constants at module level, minimize globals
- **Database**: Use SQLite for caching/persistence, prefer database queries over file I/O
- **Testing**: Use pytest with class-based test organization, mock external services
- **Architecture**: Service-oriented pattern (WeatherService, AlertService, MapService)
- **Logging**: Use Python logging module with appropriate levels and structured messages
- **Configuration**: Use Config class for all settings, environment variables for secrets</content>
<parameter name="filePath">G:\AI Projects\projects\earlyWarnings\AGENTS.md