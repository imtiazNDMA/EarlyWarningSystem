# Good and Bad Tests

## Good Tests

**Integration-style**: Test through real interfaces, not mocks of internal parts.

```python
# GOOD: Tests observable behaviour
async def test_issues_an_alert_when_a_signal_appears(session) -> None:
    screened = screened_with(signal(hazard="heavy_rain", level="severe"))

    actions = await apply_lifecycle(session, run_id, [screened])

    assert actions[Action.ISSUE] == 1
```

Characteristics:

- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

## Bad Tests

**Implementation-detail tests**: Coupled to internal structure.

```python
# BAD: Tests implementation details
async def test_apply_lifecycle_calls_write_alert_text(session, mocker) -> None:
    write = mocker.patch("ews.alerts.service.write_alert_text")
    await apply_lifecycle(session, run_id, [screened])
    write.assert_called_once_with(signal, "Badin")
```

Red flags:

- Mocking internal collaborators
- Testing private methods
- Asserting on call counts/order
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of interface

```python
# BAD: Bypasses the interface to verify
async def test_apply_lifecycle_writes_a_row(session) -> None:
    await apply_lifecycle(session, run_id, [screened])
    result = await session.execute(
        text("SELECT 1 FROM alerts WHERE district_id = 'badin'")
    )
    assert result.first() is not None


# GOOD: Verifies through the interface
async def test_issued_alert_is_listed_as_active(session) -> None:
    await apply_lifecycle(session, run_id, [screened])

    active = await active_alerts(session)

    assert [alert.hazard for alert in active] == ["heavy_rain"]
```

**Tautological tests**: Expected value restates the implementation, so the test passes by construction.

```python
# BAD: Expected value is recomputed the way the code computes it
def test_screen_reports_the_peak_value() -> None:
    days = [day(precipitation_mm=60), day(precipitation_mm=120)]
    expected = max(d.precipitation_mm for d in days)
    assert screen(days, "Sindh", rules)[0].peak_value == expected


# GOOD: Expected value is an independent, known literal
def test_screen_reports_the_peak_value() -> None:
    days = [day(precipitation_mm=60), day(precipitation_mm=120)]
    assert screen(days, "Sindh", rules)[0].peak_value == 120
```
