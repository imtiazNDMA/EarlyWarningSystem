# NEOC AI-Based Early Warning System

A sophisticated, high-performance geospatial analytics dashboard for automated weather forecasting and early warning alerts across Pakistan.

![System Dashboard Interface](UI.png)

## Core Capabilities

*   **Geospatial Intelligence**: Interactive map with real-time district-level weather visualization and dynamic heat-map blinking effects.
*   **Local LLM Inference**: AI-powered alert generation using localized Large Language Models for high data privacy and reduced latency.
*   **Multiple Weather Models**: Integration with a variety of global and regional weather data providers to ensure data redundancy and accuracy.
*   **Intelligent Analytics**: Automated nowcasting and trend analysis for temperature, precipitation, and extreme weather events.
*   **Enterprise Caching**: Robust JSON-based state management for ultra-fast data retrieval and reduced API dependency.
*   **Professional UI/UX**: State-of-the-art Glassmorphic design with responsive animations and real-time typing effects.

## Technology Stack

*   **Backend**: Python / Flask (Layered Service-Oriented Architecture)
*   **Geospacial**: Folium / Leaflet / GeoPandas
*   **Inference**: Local LLM Deployment (Ollama / LangChain)
*   **Data Processing**: Pandas / GeoJSON
*   **Frontend**: Vanilla JS (Typed.js, Bootstrap 5, FontAwesome)

## Installation

### Prerequisites

*   Python 3.10+
*   Local LLM Server (e.g. Ollama)
*   Mapbox API Token

### Setup

1. **Clone & Navigate**:
    ```bash
    git clone <repository-url>
    cd earlywarnings
    ```

2. **Environment Configuration**:
    ```bash
    cp .env.example .env
    # Configure your MAPBOX_TOKEN and local LLM endpoints
    ```

3. **Dependency Installation**:
    ```bash
    pip install -r requirements.txt
    ```

4. **Launch Application**:
    ```bash
    python app.py
    ```


## Configuration Matrix

| Variable | Description | Default |
|----------|-------------|---------|
| `MAPBOX_TOKEN` | Required for premium Mapbox tiles | `N/A` |
| `LOCAL_LLM_URL` | Endpoint for local model inference | `http://localhost:11434` |
| `LLM_MODEL` | ID of the local model to be used | `llama3.1` |
| `SECRET_KEY` | Session encryption key | `dev_secret` |
| `CACHE_TIME` | Data persistence duration (seconds) | `43200` |

## Project Architecture

```bash
earlywarnings/
├── app.py                 # Service orchestration & API routing
├── config.py              # Environment & security management
├── models.py              # Geospatial & domain data models
├── services/              # Business logic layers
│   ├── weather_service.py # Multi-model data aggregation
│   ├── alert_service.py   # AI inference & parsing logic
│   └── map_service.py     # GIS rendering & visualization
├── utils/                 # Resiliency & validation helpers
├── static/                # Asset storage & localized cache
└── tests/                 # Comprehensive test suite
```

## Quality Assurance

The system maintains a rigorous testing protocol:
```bash
# Execute local test suite
pytest tests/ -v --cov=.
```

## License

Confidential - NEOC Internal Use Only.
