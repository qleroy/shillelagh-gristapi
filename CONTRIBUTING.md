# 🤝 Contributing to shillelagh-gristapi

First off, thank you for considering contributing! It's people like you who make the open-source community such an amazing place.

## 🛠️ Development Setup

The project uses `setuptools` and `pyproject.toml`. We recommend using a virtual environment.

### 1. Clone the repository
```bash
git clone https://github.com/qleroy/shillelagh-gristapi.git
cd shillelagh-gristapi
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install in editable mode with dev dependencies
```bash
pip install -e ".[dev]"
```

### 4. Install pre-commit hooks
We use `pre-commit` to ensure code quality.
```bash
pre-commit install
```

---

## 🧪 Testing

We use `pytest` for testing.

### Run all tests
```bash
pytest
```

### Run tests with coverage
```bash
pytest --cov=shillelagh_gristapi
```

---

## 🧹 Linting and Formatting

We use `ruff` for linting and formatting, and `mypy` for type checking.

### Run ruff
```bash
ruff check .
ruff format .
```

### Run mypy
```bash
mypy src
```

---

## 🚀 Pull Request Process

1.  **Create a branch:** `git checkout -b feature/my-new-feature` or `git checkout -b bugfix/fix-some-issue`.
2.  **Write tests:** Ensure your changes are covered by tests.
3.  **Validate:** Run tests, linting, and type checking.
4.  **Commit:** Follow [Conventional Commits](https://www.conventionalcommits.org/) if possible.
5.  **Push and Open a PR:** Push your branch to GitHub and open a Pull Request against the `main` branch.

### PR Guidelines
- Keep PRs small and focused on a single change.
- Update documentation if you add or change features.
- Ensure CI passes.

---

## 📁 Project Structure

- `src/shillelagh_gristapi/`: Core logic.
    - `adapter.py`: The Shillelagh adapter implementation.
    - `http.py`: Grist API client and caching logic.
    - `schema.py`: Grist to Shillelagh type mapping.
    - `cache.py`: Local SQLite/Memory caching backend.
- `tests/`: Unit and integration tests.
- `docs/`: Detailed user documentation.
