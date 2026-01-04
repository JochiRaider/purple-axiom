# Contributing to Purple Axiom

Thank you for your interest in contributing!

## Development Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Install dev dependencies: `pip install -r requirements-dev.txt`

## Code Style

- Use `black` for formatting: `black .`
- Use `ruff` for linting: `ruff check .`
- Use `mypy` for type checking: `mypy services/`

## Testing

Run tests with: `pytest`

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests and linting
5. Commit with clear messages
6. Push and create a PR

## Code of Conduct

Be respectful, inclusive, and professional.
