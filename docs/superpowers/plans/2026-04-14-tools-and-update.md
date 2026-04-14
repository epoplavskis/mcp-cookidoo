# Tools Field and Update Recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable `tools` field (TM5/TM6/TM7) to recipes and a new `update_custom_recipe` MCP tool for editing existing recipes.

**Architecture:** The `tools` field is added to `CustomRecipe` as a validated list (API-confirmed valid values: TM5, TM6, TM7 only). A shared `_build_recipe_payload` helper is extracted from `create_custom_recipe` so both create and update reuse identical payload construction. The update MCP tool mirrors the existing `upload_custom_recipe` interface, adding only a `recipe_id` parameter.

**Tech Stack:** Python 3.12, Pydantic v2, fastmcp, aiohttp

---

## Confirmed API facts

- Valid `tools` values: `"TM5"`, `"TM6"`, `"TM7"` only (all other values return 400)
- Multiple tools allowed in one recipe: `["TM5", "TM6", "TM7"]` accepted
- Update uses `PATCH /created-recipes/{locale}/{recipe_id}` — same endpoint as the post-create patch in `create_custom_recipe`
- PATCH accepts partial payloads (only changed fields needed), but we send full payload for consistency

---

## File Map

- **Modify:** `schemas.py` — add `ToolName` type alias, add `tools` field to `CustomRecipe`
- **Modify:** `cookidoo_service.py` — extract `_build_recipe_payload`, add `tools` param to `create_custom_recipe`, add `update_custom_recipe` method
- **Modify:** `server.py` — add `tools` param to `generate_recipe_structure`, add `update_custom_recipe` MCP tool
- **Modify:** `tests/test_step_builder.py` — add tests for `tools` field validation

---

### Task 1: Add `tools` field to schema and wire through

**Files:**
- Modify: `schemas.py`
- Modify: `cookidoo_service.py`
- Modify: `server.py`
- Modify: `tests/test_step_builder.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_step_builder.py`:

```python
# --- tools field ---

def test_custom_recipe_tools_defaults_to_tm6():
    recipe = CustomRecipe(
        name="Test",
        ingredients=["100g flour"],
        steps=[RecipeStep(text="Mix.")],
    )
    assert recipe.tools == ["TM6"]


def test_custom_recipe_tools_accepts_valid_values():
    recipe = CustomRecipe(
        name="Test",
        ingredients=["100g flour"],
        steps=[RecipeStep(text="Mix.")],
        tools=["TM5", "TM6", "TM7"],
    )
    assert recipe.tools == ["TM5", "TM6", "TM7"]


def test_custom_recipe_tools_rejects_invalid():
    import pytest
    with pytest.raises(Exception):
        CustomRecipe(
            name="Test",
            ingredients=["100g flour"],
            steps=[RecipeStep(text="Mix.")],
            tools=["Oven"],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ep/projects/mcp-cookidoo
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/test_step_builder.py -v -k "tools"
```

Expected: `AttributeError` or `ValidationError` — `tools` field not yet defined on `CustomRecipe`.

- [ ] **Step 3: Add `ToolName` and `tools` field to `schemas.py`**

Add after the `ModeName` line (line 32):

```python
ToolName = Literal["TM5", "TM6", "TM7"]
```

Add `tools` field to `CustomRecipe` after `servings` (after line 119):

```python
    tools: list[ToolName] = Field(
        default=["TM6"],
        description="Thermomix models this recipe is compatible with. Valid values: 'TM5', 'TM6', 'TM7'.",
        min_length=1,
    )
```

Also update the `json_schema_extra` example dict to include `"tools": ["TM6"]` (add it after `"servings": 4`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/test_step_builder.py -v -k "tools"
```

Expected: All 3 tools tests PASS.

- [ ] **Step 5: Add `tools` parameter to `create_custom_recipe` in `cookidoo_service.py`**

Change the method signature — add `tools: list[str] = ["TM6"]` after `hints`:

```python
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
```

Change the hardcoded line in `update_data`:

Old:
```python
"tools": ["TM6"],
```

New:
```python
"tools": tools,
```

Also update the docstring for `create_custom_recipe` to add:
```
            tools: List of compatible Thermomix models, e.g. ["TM6", "TM7"] (default: ["TM6"])
```

- [ ] **Step 6: Add `tools` parameter to `generate_recipe_structure` in `server.py`**

Add `tools: str = "TM6"` parameter to the function signature (after `hints`):

```python
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
```

Add to the docstring Args section:

```
        tools: Comma-separated Thermomix models. Valid: TM5, TM6, TM7.
            Examples: "TM6" (default), "TM7", "TM6,TM7", "TM5,TM6,TM7"
```

Add tools parsing before the `recipe = CustomRecipe(...)` call:

```python
        tools_list = [t.strip() for t in tools.split(",") if t.strip()]
```

Pass `tools=tools_list` to `CustomRecipe(...)`:

```python
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
```

- [ ] **Step 7: Update `upload_custom_recipe` in `server.py` to pass `tools`**

In `upload_custom_recipe`, the call to `_cookidoo_service.create_custom_recipe` currently passes keyword args from `recipe`. Add `tools=recipe.tools`:

Find:
```python
        recipe_id = await _cookidoo_service.create_custom_recipe(
            name=recipe.name,
            ingredients=recipe.ingredients,
            steps=recipe.steps,
            servings=recipe.servings,
            prep_time=recipe.prep_time,
            total_time=recipe.total_time,
            hints=recipe.hints,
        )
```

Change to:
```python
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
```

- [ ] **Step 8: Verify server imports cleanly and all tests pass**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -c "import server; print('OK')"
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/ -v
```

Expected: `OK` and all 23 tests PASS (20 existing + 3 new tools tests).

- [ ] **Step 9: Commit**

```bash
git add schemas.py cookidoo_service.py server.py tests/test_step_builder.py
git commit -m "feat: add configurable tools field (TM5/TM6/TM7) to recipes"
```

---

### Task 2: Add `update_custom_recipe` service method and MCP tool

**Files:**
- Modify: `cookidoo_service.py` — extract `_build_recipe_payload`, add `update_custom_recipe`
- Modify: `server.py` — add `update_custom_recipe` MCP tool

- [ ] **Step 1: Extract `_build_recipe_payload` helper in `cookidoo_service.py`**

Add this method to `CookidooService` (after `close`, before `create_custom_recipe`):

```python
    def _build_recipe_payload(
        self,
        name: str,
        ingredients: list[str],
        steps: list[RecipeStep],
        servings: int,
        prep_time: int,
        total_time: int,
        hints: Optional[list[str]],
        tools: list[str],
    ) -> dict:
        """Build the PATCH payload dict for create or update."""
        return {
            "name": name,
            "image": None,
            "isImageOwnedByUser": False,
            "tools": tools,
            "yield": {"value": servings, "unitText": "portion"},
            "prepTime": prep_time * 60,
            "cookTime": 0,
            "totalTime": total_time * 60,
            "ingredients": [{"type": "INGREDIENT", "text": ing} for ing in ingredients],
            "instructions": [_build_step_instruction(step) for step in steps],
            "hints": "\n".join(hints) if hints and isinstance(hints, list) else (hints if hints else ""),
            "workStatus": "PRIVATE",
            "recipeMetadata": {"requiresAnnotationsCheck": False},
        }
```

Then update `create_custom_recipe` to use it — replace the inline `update_data = { ... }` dict with:

```python
            update_data = self._build_recipe_payload(
                name=name,
                ingredients=ingredients,
                steps=steps,
                servings=servings,
                prep_time=prep_time,
                total_time=total_time,
                hints=hints,
                tools=tools,
            )
```

- [ ] **Step 2: Run tests to verify nothing broke**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/ -q
```

Expected: 23 tests PASS.

- [ ] **Step 3: Add `update_custom_recipe` method to `CookidooService`**

Add after `create_custom_recipe`:

```python
    async def update_custom_recipe(
        self,
        recipe_id: str,
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
        Update an existing custom recipe via PATCH.

        Args:
            recipe_id: The existing recipe ID to update
            name: Recipe name
            ingredients: List of ingredient descriptions
            steps: List of RecipeStep objects with optional machine settings and ingredient links
            servings: Number of servings (default: 4)
            prep_time: Preparation time in minutes (default: 30)
            total_time: Total cooking time in minutes (default: 60)
            hints: Optional list of hints/tips for the recipe
            tools: List of compatible Thermomix models, e.g. ["TM6", "TM7"] (default: ["TM6"])

        Returns:
            str: The updated recipe ID

        Raises:
            Exception: If the update fails
        """
        if not self._api_client or not self._session:
            raise Exception("Not authenticated. Please call login() first.")

        try:
            auth_data = self._api_client.auth_data
            if not auth_data:
                raise Exception("No authentication data available")

            localization = self._api_client.localization
            url_parts = localization.url.split("/")
            base_url = f"{url_parts[0]}//{url_parts[2]}"
            locale = localization.language

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_client.auth_data.access_token}",
            }

            api_session = self._api_client._session
            update_url = f"{base_url}/created-recipes/{locale}/{recipe_id}"

            update_data = self._build_recipe_payload(
                name=name,
                ingredients=ingredients,
                steps=steps,
                servings=servings,
                prep_time=prep_time,
                total_time=total_time,
                hints=hints,
                tools=tools,
            )

            async with api_session.patch(update_url, json=update_data, headers=headers) as response:
                response_text = await response.text()
                if response.status not in [200, 204]:
                    raise Exception(f"Failed to update recipe: {response_text}")

            return recipe_id

        except Exception as e:
            raise Exception(f"Failed to update custom recipe: {str(e)}") from e
```

- [ ] **Step 4: Add `update_custom_recipe` MCP tool to `server.py`**

Add after `upload_custom_recipe`:

```python
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
```

- [ ] **Step 5: Verify server imports cleanly and all tests pass**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -c "import server; print('OK')"
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/ -q
```

Expected: `OK` and 23 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add cookidoo_service.py server.py
git commit -m "feat: add update_custom_recipe tool and extract _build_recipe_payload helper"
```

---

### Task 3: Add TM7 recipe reference guidelines to `generate_recipe_structure` docstring

**Files:**
- Modify: `server.py`

The goal is to embed authoritative TM7 defaults, ingredient-linking rules, and capacity rules directly in the tool docstring so any agent calling `generate_recipe_structure` has them in context.

- [ ] **Step 1: Replace the `generate_recipe_structure` docstring in `server.py`**

Replace the existing docstring (the triple-quoted string between the `async def generate_recipe_structure(...)` signature and the `try:` block) with the version below. The function body (`try:` onwards) is unchanged.

```python
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
```

- [ ] **Step 2: Verify server imports cleanly**

```bash
cd /Users/ep/projects/mcp-cookidoo
/Users/ep/.virtualenvs/cookidoo/bin/python -c "import server; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify tests still pass**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/ -q
```

Expected: 23 tests PASS (docstring change has no effect on test suite).

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "docs: add TM7 settings reference and recipe rules to generate_recipe_structure"
```
