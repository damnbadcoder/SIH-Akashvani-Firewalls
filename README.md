# SIH Current

## Install

Requirements: Python 3.12+ and Node.js 20.19+.

Install the Python and frontend dependencies from the repository root:

```bash
npm run install:all
```

This uses `requirements.txt` for Python packages and the committed
`frontend/package-lock.json` for the frontend packages. To install them
separately:

```bash
python -m pip install -r requirements.txt
npm --prefix frontend ci
```

## Frontend commands

```bash
npm run dev
npm run build
npm run lint
```
