if (__name__ == "__main__"):
    
    import logging
    logging.basicConfig(
        level = logging.INFO,
        format = "%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from app.api.jobs import app
    app.run(
        host = "127.0.0.1",
        port = 3000,
        debug = True,
    )
