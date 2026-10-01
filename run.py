if (__name__ == "__main__"):
    from app.api.jobs import app
    app.run(
        host = "127.0.0.1",
        port = 3000,
        debug = True,
    )
