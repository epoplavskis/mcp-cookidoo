# Cookidoo MCP Server

An MCP (Model Context Protocol) server for interacting with the Thermomix Cookidoo platform, built with `fastmcp`.

> **Disclaimer:** This is an unofficial project. The developers are not affiliated with, endorsed by, or connected to Cookidoo, Vorwerk, Thermomix, or any of their subsidiaries or trademarks.

## Features

- **Authentication**: Connect to your Cookidoo account securely
- **Recipe Details**: Fetch detailed recipe information by ID
- **Custom Recipe Retrieval**: Get a custom recipe you previously created
- **Recipe Generation**: Structure and validate new custom recipes with full Thermomix machine settings (TTS, modes, ingredient linking)
- **Recipe Upload**: Upload custom recipes to your Cookidoo account
- **Recipe Update**: Edit existing custom recipes
- **Thermomix Machine Settings**: Supports TTS steps (time/speed/temperature/direction) and preset modes (blend, dough, turbo, steaming, etc.)
- **Multi-model support**: Tag recipes as compatible with TM5, TM6, and/or TM7

## Setup

1. **Clone the repository and navigate to the project directory**

2. **Create a virtual environment and activate it:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your credentials:**
   ```bash
   cp .env.example .env
   # Edit .env with your Cookidoo credentials
   ```

5. **Run the MCP server:**
   ```bash
   fastmcp run server.py
   ```

## Running as HTTP Server

To expose the server over HTTP (for use with Claude on mobile or other remote clients):

```bash
python server.py
```

The server starts on `http://0.0.0.0:8000`. The MCP endpoint is at `/mcp/`.

### With OIDC Authentication (recommended for public exposure)

Set the OIDC env vars in `.env` (see `.env.example`). The server will require OAuth 2.0 on every request. Works with any standard OIDC provider — Authentik, Google, Okta, Auth0.

**Authentik setup:**
1. In Authentik, create a new **OAuth2/OpenID Connect Provider**
2. Set the redirect URI to `https://mcp.yourdomain.com/auth/callback`
3. Note the Client ID and Client Secret
4. Fill in the `OIDC_*` vars in `.env` using the provider's endpoints
5. Set `BASE_URL=https://mcp.yourdomain.com`

**Claude connector config (claude.ai → Add custom connector):**
- URL: `https://mcp.yourdomain.com/mcp/`
- OAuth Client ID: *(from your OIDC provider)*
- OAuth Client Secret: *(from your OIDC provider)*

### Without Authentication

Leave the OIDC env vars unset. The server runs without authentication — suitable for local use or when protected by a VPN/trusted network.

### Docker

```bash
# Build and push to GitHub Container Registry
make login   # requires GITHUB_TOKEN env var
make push    # builds for linux/amd64 and pushes

# Run with docker compose (edit domain in docker-compose.yml first)
docker compose up -d
```

## Available Tools

| Tool | Description |
|------|-------------|
| `connect_to_cookidoo` | Authenticate with Cookidoo (required before all other tools) |
| `get_recipe_details` | Get full details of any Cookidoo recipe by ID |
| `get_custom_recipe` | Get a custom recipe you previously created |
| `generate_recipe_structure` | Validate and structure a new recipe (ingredients, steps with machine settings, servings, tools) |
| `upload_custom_recipe` | Upload a new custom recipe to your Cookidoo account |
| `update_custom_recipe` | Update an existing custom recipe by ID |

### Typical workflow

```
connect_to_cookidoo
  → generate_recipe_structure   (validate data, get JSON)
  → upload_custom_recipe        (create on Cookidoo)
  → update_custom_recipe        (edit later if needed)
  → get_custom_recipe           (inspect current state)
```

## Acknowledgments

This project is built on top of the [cookidoo-api](https://github.com/miaucl/cookidoo-api), which provides the Python interface to interact with the Cookidoo platform. Special thanks for making this integration possible!

## License

MIT
