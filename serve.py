import os

from waitress import serve

from app import create_app

if __name__ == "__main__":
    host, port = os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", "5000"))
    print(f"Serving on http://{host}:{port}")
    serve(create_app(), host=host, port=port, threads=8)
