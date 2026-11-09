# Contributing to Passageworks

Thank you for your interest in contributing to Passageworks! This project is maintained by **Ayush Morbar** and follows strict engineering guidelines regarding evidence boundaries, measurement integrity, and automated testing.

---

## Code of Conduct & Ground Rules

1. **Restricted Knowledge Corpus:**  
   Answer claims must remain strictly confined to the 3 authoritative arXiv papers:
   - *Attention Is All You Need* (arXiv:1706.03762v7)
   - *Moshi: a speech-text foundation model for real-time dialogue* (arXiv:2410.00037v1)
   - *Dynamic Chunking for End-to-End Hierarchical Sequence Modeling* (arXiv:2507.07955v2)
   Do not introduce outside knowledge or ungrounded facts into answer generation.

2. **Citation Integrity:**  
   Every claim must cite `[Paper Title, Section, Page]`. If the papers do not answer a query, the assistant must explicitly refuse.

3. **Measurement Integrity:**  
   Always use monotonic clocks (`time.perf_counter()`). Never replace missing metrics with zero. Preserve blanks / nulls.

---

## Development Workflow

### 1. Environment Setup
```powershell
# Clone the repository
git clone https://github.com/ayushmorbar/passageworks.git
cd passageworks

# Install in editable mode with development dependencies
uv pip install --system -e ".[dev]"
# Or: pip install -e ".[dev]"
```

### 2. Code Standards & Linting
We use Ruff for linting and code formatting:
```powershell
# Format code
ruff format .

# Run linter
ruff check .
```

### 3. Running Tests
All tests must pass locally before opening a pull request. Tests do not require a Groq API key:
```powershell
pytest tests/ -v -m "not real_provider"
pytest tests/test_csv_schema.py -v
```

---

## Submitting Pull Requests

1. Create a short-lived feature branch (`git checkout -b feature/your-feature-name`).
2. Keep commits atomic and clearly descriptive.
3. Ensure all tests and Ruff checks pass cleanly.
4. Submit your pull request against the `main` branch.
