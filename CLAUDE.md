# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Codebase Overview

This is a Flask-based web application for weather forecasting and early warning alerts in Pakistan. It provides a geospatial dashboard with real-time weather visualization and AI-powered alert generation using local LLMs (Ollama).

## Architecture

The application follows a layered service-oriented architecture with:

1. **Flask Web Application** - Main entry point handling HTTP requests
2. **Services Layer**:
   - WeatherService: Fetches and processes weather data from Open-Meteo API
   - AlertService: Generates alerts using local LLM (Ollama) inference
   - MapService: Creates interactive Folium maps with district data
3. **Database Layer**: SQLite-based caching system for weather data and alerts
4. **Frontend**: Vanilla JS with Bootstrap 5 and FontAwesome for UI

## Key Files and Structure

- `app.py` - Main Flask application with routing and business logic
- `database.py` - SQLite database operations for caching weather data and alerts
- `config.py` - Configuration management with environment variables
- `services/` - Directory containing service classes for weather, alerts, and maps
- `templates/` - HTML templates for the web interface
- `static/` - Static assets (CSS, JS, images)
- `tests/` - Test suite for endpoints and services

## Development Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and configure MAPBOX_TOKEN

# Initialize database (automatically created on first run)
python app.py
```

### Running the Application
```bash
# Start the Flask development server
python app.py

# The application will run on http://localhost:5001
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_endpoints.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Code Quality
```bash
# Run linters
flake8 app.py
# or
black app.py

# Security checks
bandit -r app.py
```

## Key Features

1. **Geospatial Visualization**: Interactive map using Folium with district-level weather data
2. **AI-Powered Alerts**: Local LLM inference (Ollama) for generating weather alerts
3. **Caching System**: SQLite-based caching for efficient data retrieval
4. **Multiple Weather Models**: Integration with Open-Meteo API for reliable forecasting
5. **Responsive UI**: Modern Glassmorphic design with Bootstrap 5

## Environment Requirements

- Python 3.10+
- Ollama (running locally) for LLM inference
- Mapbox API Token for premium map tiles
- SQLite for database operations

## Important Endpoints

- `/` - Main dashboard
- `/get_forecast/<province>/<district>/<days>` - Get weather forecast
- `/get_alert/<province>/<district>/<days>` - Get alerts for district
- `/generate_forecast` - Generate weather forecasts
- `/generate_alerts` - Generate alerts using local LLM
- `/health` - Health check endpoint

## Database Schema

The application uses a SQLite database (`weather.db`) with two main tables:
1. `weather_cache` - Stores cached weather data with expiration
2. `alerts` - Stores generated alerts for districts with timestamps

## Configuration

Environment variables are loaded from `.env` file:
- `MAPBOX_TOKEN` - Required for Mapbox API
- `OLLAMA_BASE_URL` - Local LLM endpoint (default: http://localhost:11434)
- `OLLAMA_MODEL` - Local model to use (default: llama3.1)
- `SECRET_KEY` - Flask session encryption key
- `CACHE_TIME` - Data persistence duration in seconds (default: 43200)