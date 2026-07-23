# Third-party notices

This repository's own source code is licensed under the MIT License in
`LICENSE`. The following third-party packages are installed separately through
`requirements.txt`; they remain subject to their own licenses.

## Current direct dependencies

### FastAPI

- Source: [`fastapi/fastapi`](https://github.com/fastapi/fastapi)
- Version range: `>=0.115,<1`
- Use: HTTP API framework and static-file routing
- License: [MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE)

### HTTPX

- Source: [`encode/httpx`](https://github.com/encode/httpx)
- Version range: `>=0.27,<1`
- Use: Character and TTS HTTPS requests
- License: [BSD 3-Clause](https://github.com/encode/httpx/blob/master/LICENSE.md)

### Pydantic

- Source: [`pydantic/pydantic`](https://github.com/pydantic/pydantic)
- Version range: `>=2,<3`
- Use: request-body validation and API data models
- License: [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE)

### python-dotenv

- Source: [`theskumar/python-dotenv`](https://github.com/theskumar/python-dotenv)
- Version range: `>=1,<2`
- Use: local development configuration from `.env`
- License: [BSD 3-Clause](https://github.com/theskumar/python-dotenv/blob/main/LICENSE)

### Uvicorn

- Source: [`Kludex/uvicorn`](https://github.com/Kludex/uvicorn)
- Version range: `>=0.30,<1`, with the `standard` extra
- Use: ASGI development server
- License: [BSD 3-Clause](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md)

## Android APK releases

The current public template does not contain or distribute AndroidX source or
binaries. If a future APK release actually bundles AndroidX components, add
their exact Maven coordinates and versions here, include the applicable
Apache License 2.0 text and notices in the distributed source or APK materials,
and retain upstream attribution.

