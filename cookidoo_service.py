"""
Cookidoo Service

Module to encapsulate all cookidoo-api logic for interacting with the Cookidoo platform.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from aiohttp import ClientSession
from cookidoo_api import Cookidoo, CookidooConfig
from cookidoo_api.helpers import (
    get_localization_options,
)
import aiohttp
import asyncio
from schemas import RecipeStep


# Mode preset speeds (from API observations)
_MODE_SPEEDS: dict[str, str] = {
    "blend": "7",
    "dough": "2",
    "turbo": "10",
    "warm_up": "1",
    "rice_cooker": "1",
    "browning": "3",
    "steaming": "3",
}

# CCW arrow character used in reverse-mode machine settings text
_CCW_CHAR = "\u21BA"  # ↺


def _format_time(seconds: int) -> str:
    """Format seconds as human-readable time string. Requires seconds >= 1."""
    mins, secs = divmod(seconds, 60)
    if mins == 0:
        return f"{secs} sec"
    if secs == 0:
        return f"{mins} min"
    return f"{mins} min {secs} sec"


def _build_step_instruction(step: "RecipeStep") -> dict:
    """Convert a RecipeStep into the Cookidoo API instruction format with annotations."""
    text = step.text
    annotations: list[dict] = []

    # INGREDIENT annotations — computed against original text before settings are appended
    if step.linked_ingredients:
        for description in step.linked_ingredients:
            offset = text.find(description)
            if offset >= 0:
                annotations.append({
                    "type": "INGREDIENT",
                    "data": {"description": description},
                    "position": {"offset": offset, "length": len(description)},
                })

    # Machine setting annotations — each appended sequentially with two-space separator
    for setting in (step.settings or []):
        if setting.type == "tts":
            time_str = _format_time(setting.time_seconds)
            if setting.direction == "CCW":
                if setting.temperature:
                    settings_text = f"{time_str}/{setting.temperature.value}°{setting.temperature.unit}/{_CCW_CHAR}/speed {setting.speed}"
                else:
                    settings_text = f"{time_str}/{_CCW_CHAR}/speed {setting.speed}"
            else:
                if setting.temperature:
                    settings_text = f"{time_str}/{setting.temperature.value}°{setting.temperature.unit}/speed {setting.speed}"
                else:
                    settings_text = f"{time_str}/speed {setting.speed}"

            offset = len(text) + 2
            text = f"{text}  {settings_text}"

            tts_data: dict = {"speed": setting.speed, "time": setting.time_seconds}
            if setting.temperature:
                tts_data["temperature"] = {
                    "value": setting.temperature.value,
                    "unit": setting.temperature.unit,
                }
            if setting.direction:
                tts_data["direction"] = setting.direction

            annotations.append({
                "type": "TTS",
                "data": tts_data,
                "position": {"offset": offset, "length": len(settings_text)},
            })

        elif setting.type == "mode":
            time_str = _format_time(setting.time_seconds)
            settings_text = f"{setting.name.replace('_', ' ').title()} /{time_str}"
            preset_speed = _MODE_SPEEDS.get(setting.name, "1")

            offset = len(text) + 2
            text = f"{text}  {settings_text}"

            annotations.append({
                "type": "MODE",
                "name": setting.name,
                "data": {"speed": preset_speed, "time": setting.time_seconds},
                "position": {"offset": offset, "length": len(settings_text)},
            })

    instruction: dict = {"type": "STEP", "text": text}
    if annotations:
        instruction["annotations"] = annotations
    return instruction


def load_cookidoo_credentials() -> tuple[str, str]:
    """
    Load Cookidoo credentials from .env file.
    
    Returns:
        tuple[str, str]: Email and password
        
    Raises:
        ValueError: If credentials are not found in environment variables
    """
    load_dotenv()
    
    email = os.getenv("COOKIDOO_EMAIL")
    password = os.getenv("COOKIDOO_PASSWORD")
    
    if not email or not password:
        raise ValueError(
            "Missing Cookidoo credentials. Please set COOKIDOO_EMAIL and "
            "COOKIDOO_PASSWORD in your .env file"
        )
    
    return email, password


class CookidooService:
    """Service class for managing Cookidoo API interactions."""
    
    def __init__(self, email: str, password: str):
        """
        Initialize the Cookidoo service with credentials.
        
        Args:
            email: Cookidoo account email
            password: Cookidoo account password
        """
        self.email = email
        self.password = password
        self._api_client: Optional[Cookidoo] = None
        self._session: Optional[ClientSession] = None
    
    async def login(self) -> Cookidoo:
        """
        Authenticate with Cookidoo and return the API client.
        
        Returns:
            Cookidoo: Authenticated Cookidoo API client
            
        Raises:
            Exception: If authentication fails
        """
        try:
            # Create aiohttp ClientSession with a timeout
            self._session = ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False))
            

            # Create CookidooConfig with credentials
            config = CookidooConfig(
                email=self.email,
                password=self.password,
                localization=(
                    await get_localization_options(country="fr", language="fr-FR")
                )[0],
            )
            
            # Create Cookidoo API client with session and config
            self._api_client = Cookidoo(session=self._session, cfg=config)
            
            # Perform login (no parameters needed - uses config)
            await self._api_client.login()
            
            return self._api_client
            
        except Exception as e:
            # Clean up session if login fails
            if self._session:
                await self._session.close()
            raise Exception(f"Failed to authenticate with Cookidoo: {str(e)}") from e
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
    
    async def create_custom_recipe(
        self,
        name: str,
        ingredients: list[str],
        steps: list[RecipeStep],
        servings: int = 4,
        prep_time: int = 30,
        total_time: int = 60,
        hints: Optional[list[str]] = None,
        tools: list[str] = ["TM6"],
    ) -> str:
        """
        Create a completely new custom recipe from scratch using the undocumented API.

        Args:
            name: Recipe name
            ingredients: List of ingredient descriptions
            steps: List of RecipeStep objects with optional machine settings and ingredient links
            servings: Number of servings (default: 4)
            prep_time: Preparation time in minutes (default: 30)
            total_time: Total cooking time in minutes (default: 60)
            hints: Optional list of hints/tips for the recipe
            tools: List of compatible Thermomix models, e.g. ["TM6", "TM7"] (default: ["TM6"])

        Returns:
            str: The created recipe ID

        Raises:
            Exception: If recipe creation fails
        """
        if not self._api_client or not self._session:
            raise Exception("Not authenticated. Please call login() first.")
        
        try:
            # Get the access token from the authenticated client
            auth_data = self._api_client.auth_data
            if not auth_data:
                raise Exception("No authentication data available")
            
            localization = self._api_client.localization
            # Extract base domain from the URL (e.g., "https://cookidoo.fr/foundation/fr-FR" -> "https://cookidoo.fr")
            url_parts = localization.url.split("/")
            base_url = f"{url_parts[0]}//{url_parts[2]}"  # protocol + domain
            locale = localization.language 
            
            # Headers for the undocumented API
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_client.auth_data.access_token}"
            }
            
            # Use the API client's session to ensure cookies are shared
            api_session = self._api_client._session
        
            
            # Step 1: Create the recipe with just the name
            create_url = f"{base_url}/created-recipes/{locale}"
            create_data = {"recipeName": name}
            
            async with api_session.post(
                create_url, json=create_data, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to create recipe. Status: {response.status}, Error: {error_text}"
                    )
                
                result = await response.json()
                recipe_id = result.get("recipeId")
                
                if not recipe_id:
                    raise Exception("No recipe ID returned from creation")
            
            # Step 2: Update recipe with ingredients
            update_url = f"{base_url}/created-recipes/{locale}/{recipe_id}"
            
            # PATCH requires a complete recipe structure with ALL required fields
            update_data = {
                "name": name,
                "image": None,  # Can be null or match pattern: ^((prod|nonprod)/img/customer-recipe/)?[A-Za-z0-9-_]{1,}.(bmp|jpe|jpeg|jpg|png)$
                "isImageOwnedByUser": False,
                "tools": tools,
                "yield": {"value": servings, "unitText": "portion"},
                "prepTime": prep_time * 60,  # Convert minutes to seconds
                "cookTime": 0,
                "totalTime": total_time * 60,  # Convert minutes to seconds
                "ingredients": [{"type": "INGREDIENT", "text": ing} for ing in ingredients],
                "instructions": [_build_step_instruction(step) for step in steps],
                "hints": "\n".join(hints) if hints and isinstance(hints, list) else (hints if hints else ""),
                "workStatus": "PRIVATE",
                "recipeMetadata": {
                    "requiresAnnotationsCheck": False
                }
            }
            
            await asyncio.sleep(5)

            async with api_session.patch(update_url, json=update_data, headers=headers) as response:
                print(f"  Response Status: {response.status}")
                response_text = await response.text()
                print(f"  Response Body: {response_text}")
                
                if response.status not in [200, 204]:
                    raise Exception(f"Failed to update recipe: {response_text}")
            
            return recipe_id
            
        except Exception as e:
            raise Exception(f"Failed to create custom recipe: {str(e)}") from e
    
    @property
    def api_client(self) -> Optional[Cookidoo]:
        """Get the current API client instance."""
        return self._api_client
