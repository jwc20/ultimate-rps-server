from starlette.middleware.cors import CORSMiddleware


def add_cors_middleware(app):
    return CORSMiddleware(
        app=app,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def add_logging_middleware(app):
    async def middleware(scope, receive, send):
        path = scope["path"]
        print("Request:", path)
        await app(scope, receive, send)

    return middleware