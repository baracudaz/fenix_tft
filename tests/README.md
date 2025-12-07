# Testing Fenix TFT Integration

This directory contains the test suite for the Fenix TFT Home Assistant integration.

## Running Tests

### Quick Test Run

```bash
./scripts/test
```

### Test with Coverage Report

```bash
./scripts/test --cov-report=html
```

Then open `htmlcov/index.html` in your browser to see detailed coverage.

### Run Specific Tests

```bash
# Run only config flow tests
uv run pytest tests/components/fenix_tft/test_config_flow.py

# Run a specific test function
uv run pytest tests/components/fenix_tft/test_config_flow.py::test_user_flow_success

# Run with verbose output
uv run pytest tests/ -v

# Run with extra verbosity
uv run pytest tests/ -vv
```

## Test Structure

```
tests/
└── components/
    └── fenix_tft/
        ├── conftest.py                 # Shared fixtures
        ├── fixtures/                   # Test data (JSON responses)
        ├── test_config_flow.py        # Config flow tests (100% coverage required)
        ├── test_init.py               # Integration setup tests
        ├── test_climate.py            # Climate entity tests
        ├── test_sensor.py             # Sensor entity tests
        ├── test_diagnostics.py        # Diagnostics tests
        └── test_services.py           # Service tests
```

## Test Coverage Requirements

Home Assistant requires **95%+ test coverage** for integrations. Key areas:

- ✅ Config flow (all paths: success, errors, reauth, options)
- ✅ Integration setup and teardown
- ✅ Entity creation and attributes
- ✅ Service calls
- ✅ Diagnostics data
- ✅ Error handling

## Writing New Tests

### Using Fixtures

The `conftest.py` file provides reusable fixtures:

```python
async def test_my_feature(hass: HomeAssistant, init_integration, mock_fenix_api):
    """Test my feature."""
    # init_integration has already set up the integration
    # mock_fenix_api is the mocked API client
    
    # Your test code here
    pass
```

### Mocking API Responses

Add JSON fixtures to `fixtures/` directory and load them in `conftest.py`:

```python
with open(fixtures_path / "my_data.json") as f:
    my_data = json.load(f)

mock_api.my_method = AsyncMock(return_value=my_data)
```

### Testing Error Conditions

```python
mock_fenix_api.authenticate.side_effect = FenixTFTConnectionError("Connection failed")

with patch("custom_components.fenix_tft.config_flow.FenixTFTApi", return_value=mock_fenix_api):
    result = await hass.config_entries.flow.async_configure(...)

assert result["errors"] == {"base": "cannot_connect"}
```

## Continuous Integration

Tests should be run automatically on:

- Every commit (pre-commit hook)
- Pull requests (GitHub Actions)
- Before releases

Add to `.github/workflows/test.yml`:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -e ".[test]"
      - name: Run tests
        run: uv run pytest tests/ --cov=custom_components.fenix_tft --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

## Debugging Tests

### Run with pdb debugger

```bash
uv run pytest tests/ --pdb
```

### Show print statements

```bash
uv run pytest tests/ -s
```

### Show local variables on failure

```bash
uv run pytest tests/ -l
```

## Coverage Goals

Target coverage by module:

- `config_flow.py`: 100% (all error paths)
- `__init__.py`: 95%+
- `api.py`: 90%+ (some edge cases may be difficult)
- `coordinator.py`: 95%+
- `climate.py`: 95%+
- `sensor.py`: 95%+
- `helpers.py`: 100%
- `diagnostics.py`: 100%

Overall target: **95%+ coverage**
