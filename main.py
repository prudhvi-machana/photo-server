from fastapi import FastAPI

app = FastAPI(title="Family Photo Server")


@app.get("/")
def root():
    return {"status": "ok", "service": "family-photo-server"}


@app.get("/health")
def health():
    return {"status": "healthy"}
