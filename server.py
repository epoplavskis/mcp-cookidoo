"""
Cookidoo MCP Server

Main server file containing MCP tool definitions for interacting with Cookidoo.
"""

from fastmcp import FastMCP
from cookidoo_service import CookidooService, load_cookidoo_credentials
from schemas import CustomRecipe, RecipeStep
import json

# Initialize FastMCP server
mcp = FastMCP("cookidoo-mcp-server")

# Module-level state to store the authenticated session
_cookidoo_service: CookidooService | None = None
_cookidoo_api = None


@mcp.tool()
async def connect_to_cookidoo() -> str:
    """
    Authenticate with Cookidoo and store the session.
    
    This tool must be called before using other Cookidoo tools. It will:
    1. Load your Cookidoo credentials from the .env file
    2. Authenticate with the Cookidoo platform
    3. Store the authenticated session for use by other tools
        
    Returns:
        str: Success message confirming connection
        
    Raises:
        ValueError: If credentials are missing from .env file
        Exception: If authentication fails
    """
    global _cookidoo_service, _cookidoo_api
    
    try:
        # Load credentials from .env file
        email, password = load_cookidoo_credentials()
        
        # Create Cookidoo service instance
        _cookidoo_service = CookidooService(email, password)
        
        # Authenticate and get API client
        _cookidoo_api = await _cookidoo_service.login()
        
        return f"Successfully connected to Cookidoo as {email}"
        
    except ValueError as e:
        # Missing credentials
        return f"Configuration Error: {str(e)}\n\nPlease ensure your .env file contains COOKIDOO_EMAIL and COOKIDOO_PASSWORD"
        
    except Exception as e:
        # Authentication or other errors
        return f"Connection Failed: {str(e)}\n\nPlease check your credentials and try again."


@mcp.tool()
async def get_recipe_details(recipe_id: str) -> str:
    """
    Get detailed information about a specific recipe by its ID.
    
    Use this tool to get full details about a recipe for inspiration before creating
    your own custom recipe. You must be connected first using connect_to_cookidoo.
    
    Args:
        recipe_id: The Cookidoo recipe ID (e.g., "r59322", "r907015")
        
    Returns:
        str: Detailed recipe information including ingredients, steps, cooking time, etc.
        
    Raises:
        Exception: If not connected or if the recipe is not found
    """
    global _cookidoo_api
    
    try:
        # Check if connected
        if not _cookidoo_api:
            return "Not connected. Please run 'connect_to_cookidoo' first."
        
        # Get recipe details
        recipe = await _cookidoo_api.get_recipe_details(recipe_id)
        
        # Format the results
        result = f"Recipe Details:\n\n"
        result += f"Name: {recipe.name}\n"
        result += f"ID: {recipe.id}\n\n"
        
        if hasattr(recipe, 'serving_size'):
            result += f"Servings: {recipe.serving_size}\n"
        
        if hasattr(recipe, 'total_time'):
            result += f"Total Time: {recipe.total_time} minutes\n"
        
        if hasattr(recipe, 'difficulty'):
            result += f"Difficulty: {recipe.difficulty}\n"
        
        result += "\n"
        
        # Ingredients
        if hasattr(recipe, 'ingredients') and recipe.ingredients:
            result += "Ingredients:\n"
            for ingredient in recipe.ingredients:
                if hasattr(ingredient, 'name'):
                    result += f"  • {ingredient.name}"
                    if hasattr(ingredient, 'quantity') and ingredient.quantity:
                        result += f" - {ingredient.quantity}"
                    result += "\n"
            result += "\n"
        
        # Steps
        if hasattr(recipe, 'steps') and recipe.steps:
            result += "Steps:\n"
            for i, step in enumerate(recipe.steps, 1):
                if hasattr(step, 'description'):
                    result += f"{i}. {step.description}\n"
            result += "\n"
        
        # URL if available
        if hasattr(recipe, 'url') and recipe.url:
            result += f"URL: {recipe.url}\n"
        
        return result
        
    except Exception as e:
        return f"Failed to get recipe details: {str(e)}"


@mcp.tool()
async def generate_recipe_structure(
    name: str,
    ingredients: str,
    steps_json: str,
    servings: int = 4,
    prep_time: int = 30,
    total_time: int = 60,
    hints: str = "",
    tools: str = "TM6",
) -> str:
    """
    Generate and validate a recipe structure ready for upload to Cookidoo.

    Args:
        name: Recipe name (required)
        ingredients: Ingredients list, one per line or comma-separated
        steps_json: JSON array of step objects. Each step must have a "text" field.

            Plain step (no machine setting):
              {"text": "Preheat oven to 200°C."}

            TTS step (manual machine setting):
              {
                "text": "Add 2 onions, halved to bowl.",
                "settings": [
                  {
                    "type": "tts",
                    "time_seconds": 5,
                    "speed": "5",
                    "temperature": {"value": "120", "unit": "C"},
                    "direction": "CCW"
                  }
                ],
                "linked_ingredients": ["2 onions, halved"]
              }

            MODE step (preset mode):
              {
                "text": "Blend the sauce.",
                "settings": [{"type": "mode", "name": "blend", "time_seconds": 30}]
              }

            A step can have multiple settings in sequence.

            TTS fields:
              - time_seconds (int): duration e.g. 60
              - speed (str): "0.5", "1" ... "10"
              - temperature (object, optional): {"value": "100", "unit": "C"}
              - direction (str, optional): "CCW" for Reverse; omit for Normal

            MODE names: blend, dough, turbo, warm_up, rice_cooker, browning, steaming

        servings: Number of servings (default: 4, range: 1-20)
        prep_time: Preparation time in minutes (default: 30)
        total_time: Total cooking time in minutes (default: 60)
        hints: Optional cooking tips, one per line or comma-separated
        tools: Comma-separated Thermomix models. Valid: TM5, TM6, TM7.
            Examples: "TM6" (default), "TM7", "TM6,TM7", "TM5,TM6,TM7"

    TM7 STANDARD SETTINGS REFERENCE (use these as defaults when adapting recipes):
      Chopping:        5-10 sec / speed 5 / no temp / Normal
      Sautéing:        5 min / 120°C / speed 1 / Normal
      Browning mince:  10 min / 120°C / speed 1 / CCW
      Simmering sauce: 20-30 min / 100°C / speed 1 / CCW
      Béchamel:        12 min / 90°C / speed 4 / Normal
      Steaming:        use MODE "steaming" with appropriate time

    INGREDIENT LINKING RULES:
      - Each string in linked_ingredients must exactly match its entry in the
        master ingredients list (same quantity, units, and description)
      - Every ingredient mentioned by name in the step text should also appear
        in linked_ingredients so the app can bold and link it

    CAPACITY & STEP RULES:
      - TM7 bowl is 2.2L. Steps with 1 kg+ of mince or large liquid volumes
        should always use CCW direction and include a spatula reminder in hints
      - Steps involving baking, assembling, layering, or resting must always be
        plain steps with no settings block
      - Always scrape down the bowl after chopping before the next step

    Returns:
        str: Validated recipe structure in JSON format, ready for upload
    """
    try:
        ingredients_list = [
            ing.strip()
            for ing in (
                ingredients.split("\n") if "\n" in ingredients else ingredients.split(",")
            )
            if ing.strip()
        ]

        try:
            raw_steps = json.loads(steps_json)
        except json.JSONDecodeError as e:
            return f"Invalid steps_json: {e}\n\nsteps_json must be a JSON array of step objects."

        if not isinstance(raw_steps, list):
            return "steps_json must be a JSON array."

        steps_list = [RecipeStep(**s) for s in raw_steps]

        hints_list = None
        if hints:
            hints_list = [
                h.strip()
                for h in (hints.split("\n") if "\n" in hints else hints.split(","))
                if h.strip()
            ]

        tools_list = [t.strip() for t in tools.split(",") if t.strip()]

        recipe = CustomRecipe(
            name=name,
            ingredients=ingredients_list,
            steps=steps_list,
            servings=servings,
            prep_time=prep_time,
            total_time=total_time,
            hints=hints_list,
            tools=tools_list,
        )

        return f"Recipe structure validated successfully!\n\n{recipe.model_dump_json(indent=2)}\n\nYou can now use this with 'upload_custom_recipe'."

    except Exception as e:
        return f"Validation failed: {str(e)}\n\nPlease check your recipe data and try again."


@mcp.tool()
async def upload_custom_recipe(recipe_json: str) -> str:
    """
    Upload a custom recipe to your Cookidoo account.
    
    This tool creates a brand new recipe from scratch on your Cookidoo account.
    Use 'generate_recipe_structure' first to validate your recipe data, then
    pass the resulting JSON to this tool.
    
    Args:
        recipe_json: The validated recipe JSON from generate_recipe_structure
        
    Returns:
        str: Success message with the created recipe ID
    """
    global _cookidoo_service, _cookidoo_api
    
    try:
        # Check if connected
        if not _cookidoo_service or not _cookidoo_api:
            return "Not connected. Please run 'connect_to_cookidoo' first."
        
        # Parse and validate the recipe JSON
        try:
            recipe_data = json.loads(recipe_json)
            recipe = CustomRecipe(**recipe_data)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {str(e)}"
        except Exception as e:
            return f"Invalid recipe data: {str(e)}"
        
        # Create the recipe using our custom service method
        recipe_id = await _cookidoo_service.create_custom_recipe(
            name=recipe.name,
            ingredients=recipe.ingredients,
            steps=recipe.steps,
            servings=recipe.servings,
            prep_time=recipe.prep_time,
            total_time=recipe.total_time,
            hints=recipe.hints,
            tools=recipe.tools,
        )
        
        # Get localization for URL
        localization = _cookidoo_api.localization
        recipe_url = f"https://{localization.url}/recipes/custom-recipes/{recipe_id}"
        
        return f"Recipe '{recipe.name}' created successfully!\n\nRecipe ID: {recipe_id}\nURL: {recipe_url}\n\nYour recipe is now saved in your Cookidoo account!"
        
    except Exception as e:
        return f"Upload failed: {str(e)}"


@mcp.tool()
async def update_custom_recipe(recipe_id: str, recipe_json: str) -> str:
    """
    Update an existing custom recipe on your Cookidoo account.

    Use this to edit a recipe you previously created. Pass the recipe ID and
    a full recipe JSON (from generate_recipe_structure). All fields will be
    replaced with the new values.

    Args:
        recipe_id: The ID of the recipe to update (e.g. "01KNY4A5HSKZTR6MPZ2K0SJ4EX")
        recipe_json: Full recipe JSON from generate_recipe_structure

    Returns:
        str: Success message confirming the update
    """
    global _cookidoo_service, _cookidoo_api

    try:
        if not _cookidoo_service or not _cookidoo_api:
            return "Not connected. Please run 'connect_to_cookidoo' first."

        try:
            recipe_data = json.loads(recipe_json)
            recipe = CustomRecipe(**recipe_data)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {str(e)}"
        except Exception as e:
            return f"Invalid recipe data: {str(e)}"

        await _cookidoo_service.update_custom_recipe(
            recipe_id=recipe_id,
            name=recipe.name,
            ingredients=recipe.ingredients,
            steps=recipe.steps,
            servings=recipe.servings,
            prep_time=recipe.prep_time,
            total_time=recipe.total_time,
            hints=recipe.hints,
            tools=recipe.tools,
        )

        localization = _cookidoo_api.localization
        recipe_url = f"https://{localization.url}/recipes/custom-recipes/{recipe_id}"
        return f"Recipe '{recipe.name}' updated successfully!\n\nRecipe ID: {recipe_id}\nURL: {recipe_url}"

    except Exception as e:
        return f"Update failed: {str(e)}"
