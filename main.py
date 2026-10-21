"""Run the development API server with ``python3 main.py``."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.main:app", reload=True)
