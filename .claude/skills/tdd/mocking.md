# When to Mock

Mock at **system boundaries** only:

- External APIs (payment, email, etc.)
- Databases (sometimes - prefer test DB; this repo uses a real disposable Postgres per test)
- Time/randomness
- File system (sometimes)

Don't mock:

- Your own classes/modules
- Internal collaborators
- Anything you control

## Designing for Mockability

At system boundaries, design interfaces that are easy to mock:

**1. Use dependency injection**

Pass external dependencies in rather than creating them internally:

```python
# Easy to mock - the transport is injected, so tests pass httpx.MockTransport
class OpenMeteoForecastClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url


# Hard to mock - the client builds its own transport from the environment
class OpenMeteoForecastClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)
        self._base_url = os.environ["OPEN_METEO_URL"]
```

**2. Prefer SDK-style interfaces over generic fetchers**

Create specific functions for each external operation instead of one generic function with conditional logic:

```python
# GOOD: Each operation is independently mockable, with a typed return
class ForecastSource:
    async def daily(
        self, locations: Sequence[Location], days: int
    ) -> list[LocationForecast]: ...

    async def hourly(
        self, location: Location, hours: int
    ) -> list[HourlyForecast]: ...


# BAD: One generic fetcher pushes conditional logic into every mock
class ForecastSource:
    async def get(self, path: str, **params: Any) -> dict[str, Any]: ...
```

The SDK approach means:
- Each mock returns one specific shape
- No conditional logic in test setup
- Easier to see which endpoints a test exercises
- Type safety per endpoint
