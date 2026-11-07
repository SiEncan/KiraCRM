"""Entry point Flask yang diimpor oleh Vercel."""

from server import create_app

app = create_app(serve_frontend=False)
