# Early Warnings Weather Dashboard

A Flask-based web application for weather forecasting and early warning alerts for Pakistan districts.

## Features

- Interactive map showing weather forecasts for Pakistani districts
- AI-powered weather alerts using Groq API with retry logic
- Real-time weather data from Open-Meteo API
- Intelligent caching system for improved performance
- RESTful API endpoints for forecasts and alerts
- Health check endpoint for monitoring
- Comprehensive input validation and security measures
- Rate limiting and CORS protection
- Automated testing and CI/CD pipeline

## Installation

### Prerequisites

- Python 3.8+
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd earlywarnings
```

2. Install dependencies:
```bash
pip install flask folium groq pandas requests geopandas python-dotenv
```

3. Install development tools (optional):
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install pytest pytest-cov pytest-mock flake8 black bandit
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. Run the application:
```bash
python app.py
```

The application will be available at http://localhost:5000

## Configuration

### Environment Variables

- `OPENMETEO_URL`: Open-Meteo API base URL (default: https://api.open-meteo.com/v1/forecast)
- `GROQ_API_KEY`: Your Groq API key for AI alerts (required)
- `MAPBOX_TOKEN`: Your Mapbox token for map rendering (required)
- `SECRET_KEY`: Flask secret key for sessions (required in production)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `LOG_FILE`: Path to log file (default: app.log)
- `CACHE_TIME`: Cache timeout in seconds (default: 43200 = 12 hours)
- `API_TIMEOUT`: API request timeout in seconds (default: 30)
- `MAX_CONTENT_LENGTH`: Maximum request size in bytes (default: 16MB)
- `MAX_DISTRICTS_PER_REQUEST`: Maximum districts per API request (default: 100)
- `CORS_ORIGINS`: Comma-separated list of allowed origins (default: *)

### API Endpoints

- `GET /`: Main dashboard
- `GET /health`: Health check endpoint
- `GET /get_forecast/<province>/<district>/<days>`: Get weather forecast
- `GET /get_alert/<province>/<district>/<days>`: Get weather alert
- `GET /get_districts/<province>`: Get districts for a province
- `GET /refresh_map/<days>`: Refresh map with updated data
- `POST /generate_forecast`: Generate forecasts for districts
- `POST /generate_alerts`: Generate AI alerts
- `POST /generate_forecast_and_alerts`: Combined forecast and alert generation

## Development

### Code Quality

Run linting:
```bash
flake8 app.py
```

Format code:
```bash
black app.py
```

### Testing

Run tests:
```bash
# Run all tests with coverage
pytest tests/ -v --cov=. --cov-report=html

# Run specific test file
pytest tests/test_validation.py -v

# Run with coverage report
pytest --cov=. --cov-report=term-missing
```

### Project Structure

```
earlywarnings/
├── app.py                 # Main Flask application
├── config.py             # Configuration management
├── models.py             # Data models and constants
├── constants.py          # Application constants
├── health.py             # Health check utilities
├── services/             # Business logic services
│   ├── weather_service.py # Weather data fetching
│   ├── alert_service.py   # AI alert generation
│   └── map_service.py     # Map generation
├── utils/                # Utility modules
│   ├── validation.py     # Input validation
│   └── retry.py          # Retry logic for API calls
├── static/               # Static assets
│   ├── weatherdata/      # Cached weather/alert data
│   └── boundary/         # Geographic boundaries
├── templates/            # Jinja2 templates
├── tests/                # Unit tests
│   ├── test_weather_service.py
│   ├── test_alert_service.py
│   ├── test_map_service.py
│   ├── test_validation.py
│   └── test_endpoints.py
├── .github/workflows/    # CI/CD pipeline
├── requirements.txt      # Python dependencies
├── setup.cfg            # Tool configuration
└── AGENTS.md            # Development guidelines
```

## Contributing

1. Follow the code style guidelines in AGENTS.md
2. Add tests for new features
3. Run linting and tests before submitting PRs
4. Update documentation as needed

## License

[Add license information]