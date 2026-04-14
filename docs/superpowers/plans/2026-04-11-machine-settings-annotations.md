# Machine Settings Annotations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the MCP server to support structured machine settings (TTS + MODE) and ingredient linking in recipe steps, using the Cookidoo API annotation system.

**Architecture:** Each step's `text` field embeds human-readable machine settings inline at specific character positions. An `annotations` array marks those positions with structured data (`TTS` for manual settings, `MODE` for preset modes, `INGREDIENT` for linked ingredients). The service builds both the text and annotations from structured input. Multiple settings per step are supported.

**Tech Stack:** Python 3.12, Pydantic v2, fastmcp, cookidoo-api

---

## Captured API Format (reference)

From network capture — a step with all annotation types:

```json
{
  "type": "STEP",
  "text": "...description...  1 min/85°C/speed 3  Blend /4 min 30 sec  6 min 30 sec/85°C//speed 5",
  "annotations": [
    {
      "type": "INGREDIENT",
      "data": {"description": "2 onions, halved"},
      "position": {"offset": 111, "length": 16}
    },
    {
      "type": "TTS",
      "data": {"speed": "3", "time": 60, "temperature": {"value": "85", "unit": "C"}},
      "position": {"offset": 139, "length": 18}
    },
    {
      "type": "MODE",
      "name": "blend",
      "data": {"speed": "7", "time": 270},
      "position": {"offset": 236, "length": 20}
    },
    {
      "type": "TTS",
      "data": {"speed": "5", "direction": "CCW", "time": 390, "temperature": {"value": "85", "unit": "C"}},
      "position": {"offset": 258, "length": 27}
    }
  ]
}
```

**Key rules:**
- Settings are appended to `text` separated by two spaces (`"  "`)
- TTS text format: `{time}/{temp}/speed {speed}` e.g. `"1 min/65°C/speed 3"` (18 chars)
- TTS reverse text format: `{time}/{temp}/{CCW_CHAR}/speed {speed}` — there is a special Unicode char between the two `/` for CCW; its exact codepoint is unknown so we use `\u21BA` (↺) as a placeholder and adjust if tests fail
- MODE text format: `{Name} {ICON}/{time}` — the mode name + an icon char + `/` + time (20 chars for "Blend ⊗/4 min 30 sec" with blend icon); exact icon chars unknown, use mode name capitalized + ` /` + time as approximation
- `direction: "CCW"` in TTS data = Reverse; omit field for Normal
- MODE `data.speed` is mode-preset: blend=7, dough=2, turbo=10, warm_up=1, rice_cooker=1, browning=3, steaming=3 (estimated — adjust from test)

---

## File Map

- **Modify:** `schemas.py` — replace `MachineSettings` with `TTSSetting` + `ModeSetting`; update `RecipeStep.settings` to `list[StepSetting]`
- **Modify:** `cookidoo_service.py` — update `_build_step_instruction` for multi-setting steps, CCW direction, and MODE type; update `create_custom_recipe` signature
- **Modify:** `server.py` — update `generate_recipe_structure` docstring/parameter for new schema
- **Create:** `tests/test_step_builder.py` — unit tests for annotation building

---

### Task 1: Update schema models

**Files:**
- Modify: `schemas.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_step_builder.py`:

```python
import pytest
from schemas import Temperature, TTSSetting, ModeSetting, RecipeStep, CustomRecipe


def test_temperature_defaults_to_celsius():
    t = Temperature(value="65")
    assert t.unit == "C"


def test_tts_setting_basic():
    s = TTSSetting(time_seconds=60, speed="3")
    assert s.time_seconds == 60
    assert s.speed == "3"
    assert s.temperature is None
    assert s.direction is None


def test_tts_setting_with_temp_and_reverse():
    s = TTSSetting(
        time_seconds=300,
        speed="1",
        temperature=Temperature(value="100"),
        direction="CCW",
    )
    assert s.direction == "CCW"
    assert s.temperature.value == "100"


def test_mode_setting():
    s = ModeSetting(name="blend", time_seconds=270)
    assert s.name == "blend"
    assert s.time_seconds == 270


def test_recipe_step_plain():
    step = RecipeStep(text="Preheat oven to 200°C.")
    assert step.settings is None
    assert step.linked_ingredients is None


def test_recipe_step_with_multiple_settings():
    step = RecipeStep(
        text="Chop then blend.",
        settings=[
            TTSSetting(time_seconds=5, speed="5"),
            ModeSetting(name="blend", time_seconds=30),
        ],
    )
    assert len(step.settings) == 2


def test_custom_recipe_accepts_recipe_steps():
    recipe = CustomRecipe(
        name="Test",
        ingredients=["100g flour"],
        steps=[RecipeStep(text="Mix well.")],
    )
    assert isinstance(recipe.steps[0], RecipeStep)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ep/projects/mcp-cookidoo
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/test_step_builder.py -v
```

Expected: `ImportError` — `TTSSetting`, `ModeSetting` not yet defined.

- [ ] **Step 3: Replace `schemas.py`**

```python
"""
Recipe Schemas

Pydantic models for custom recipe data validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal, Union, Annotated


class Temperature(BaseModel):
    value: str = Field(..., description="Temperature value e.g. '65', '100', '120'")
    unit: Literal["C"] = "C"


class TTSSetting(BaseModel):
    """Manual Thermomix machine setting (time + speed + optional temperature)."""

    type: Literal["tts"] = "tts"
    time_seconds: int = Field(..., description="Duration in seconds", ge=1)
    speed: str = Field(..., description="Speed: '0.5', '1', '2' ... '10'")
    temperature: Optional[Temperature] = Field(
        default=None,
        description="Omit for Temperature OFF",
    )
    direction: Optional[Literal["CCW"]] = Field(
        default=None,
        description="Set to 'CCW' for Reverse. Omit for Normal.",
    )


class ModeSetting(BaseModel):
    """Preset Thermomix mode (Blend, Dough, Turbo, Warm Up, Rice Cooker, etc.)."""

    type: Literal["mode"] = "mode"
    name: str = Field(
        ...,
        description=(
            "Lowercase mode name: 'blend', 'dough', 'turbo', "
            "'warm_up', 'rice_cooker', 'browning', 'steaming'"
        ),
    )
    time_seconds: int = Field(..., description="Duration in seconds", ge=1)


StepSetting = Annotated[
    Union[TTSSetting, ModeSetting],
    Field(discriminator="type"),
]


class RecipeStep(BaseModel):
    text: str = Field(..., description="Full human-readable step description")
    settings: Optional[list[StepSetting]] = Field(
        default=None,
        description=(
            "Ordered list of machine settings for this step. "
            "Each setting's text is appended to `text` at the position recorded "
            "in the annotation. Supports TTSSetting and ModeSetting."
        ),
    )
    linked_ingredients: Optional[list[str]] = Field(
        default=None,
        description=(
            "Ingredient descriptions that appear verbatim in `text` "
            "and should be linked (e.g. '2 onions, halved')"
        ),
    )


class CustomRecipe(BaseModel):
    """Model for a custom recipe to be created on Cookidoo."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Bolognese",
                "ingredients": ["2 onions, halved", "30 g olive oil"],
                "steps": [
                    {
                        "text": "Add 2 onions, halved to the bowl.",
                        "settings": [
                            {"type": "tts", "time_seconds": 5, "speed": "5"}
                        ],
                        "linked_ingredients": ["2 onions, halved"],
                    },
                    {
                        "text": "Add olive oil and sauté.",
                        "settings": [
                            {
                                "type": "tts",
                                "time_seconds": 300,
                                "speed": "1",
                                "temperature": {"value": "120", "unit": "C"},
                            }
                        ],
                    },
                    {
                        "text": "Blend the sauce.",
                        "settings": [
                            {"type": "mode", "name": "blend", "time_seconds": 30}
                        ],
                    },
                    {"text": "Preheat oven to 200°C."},
                ],
                "servings": 4,
                "prep_time": 10,
                "total_time": 30,
            }
        }
    )

    name: str = Field(..., description="Recipe name", min_length=1, max_length=200)
    ingredients: list[str] = Field(
        ..., description="List of ingredients with quantities", min_length=1
    )
    steps: list[RecipeStep] = Field(
        ..., description="List of cooking steps", min_length=1
    )
    servings: int = Field(default=4, ge=1, le=20)
    prep_time: int = Field(default=30, description="Preparation time in minutes", ge=1, le=1440)
    total_time: int = Field(default=60, description="Total cooking time in minutes", ge=1, le=1440)
    hints: Optional[list[str]] = Field(default=None, description="Optional cooking tips")
```

- [ ] **Step 4: Run tests**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/test_step_builder.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/ep/projects/mcp-cookidoo
git add schemas.py tests/test_step_builder.py
git commit -m "feat: add TTSSetting, ModeSetting, RecipeStep schema models"
```

---

### Task 2: Add `_build_step_instruction()` helper

**Files:**
- Modify: `cookidoo_service.py`
- Modify: `tests/test_step_builder.py`

- [ ] **Step 1: Append tests for `_build_step_instruction`**

Add to the bottom of `tests/test_step_builder.py`:

```python
from cookidoo_service import _build_step_instruction, _format_time


# --- _format_time ---

def test_format_whole_minutes():
    assert _format_time(60) == "1 min"
    assert _format_time(300) == "5 min"


def test_format_seconds_only():
    assert _format_time(30) == "30 sec"
    assert _format_time(5) == "5 sec"


def test_format_minutes_and_seconds():
    assert _format_time(90) == "1 min 30 sec"
    assert _format_time(270) == "4 min 30 sec"


# --- _build_step_instruction ---

def test_plain_step_no_annotations():
    step = RecipeStep(text="Preheat oven to 200°C.")
    result = _build_step_instruction(step)
    assert result == {"type": "STEP", "text": "Preheat oven to 200°C."}
    assert "annotations" not in result


def test_tts_no_temp_appended():
    step = RecipeStep(
        text="Blend.",
        settings=[TTSSetting(time_seconds=30, speed="10")],
    )
    result = _build_step_instruction(step)
    assert result["text"] == "Blend.  30 sec/speed 10"


def test_tts_with_temp_appended():
    # "Chop the vegetables." = 20 chars -> offset 22, settings text 18 chars
    step = RecipeStep(
        text="Chop the vegetables.",
        settings=[
            TTSSetting(
                time_seconds=60,
                speed="3",
                temperature=Temperature(value="65", unit="C"),
            )
        ],
    )
    result = _build_step_instruction(step)
    assert result["text"] == "Chop the vegetables.  1 min/65°C/speed 3"
    tts = next(a for a in result["annotations"] if a["type"] == "TTS")
    assert tts["position"]["offset"] == 22
    assert tts["position"]["length"] == 18
    assert tts["data"] == {
        "speed": "3",
        "time": 60,
        "temperature": {"value": "65", "unit": "C"},
    }


def test_tts_ccw_direction_in_data():
    step = RecipeStep(
        text="Cook.",
        settings=[
            TTSSetting(
                time_seconds=60,
                speed="1",
                temperature=Temperature(value="100"),
                direction="CCW",
            )
        ],
    )
    result = _build_step_instruction(step)
    tts = next(a for a in result["annotations"] if a["type"] == "TTS")
    assert tts["data"]["direction"] == "CCW"


def test_mode_annotation_structure():
    step = RecipeStep(
        text="Knead.",
        settings=[ModeSetting(name="dough", time_seconds=120)],
    )
    result = _build_step_instruction(step)
    mode = next(a for a in result["annotations"] if a["type"] == "MODE")
    assert mode["name"] == "dough"
    assert mode["data"]["time"] == 120
    assert "speed" in mode["data"]


def test_multiple_settings_sequential_offsets():
    # "X." = 2 chars
    # TTS text = "30 sec/speed 5" = 14 chars -> offset 4, length 14
    # Mode text appended at offset 4+14+2=20
    step = RecipeStep(
        text="X.",
        settings=[
            TTSSetting(time_seconds=30, speed="5"),
            ModeSetting(name="blend", time_seconds=30),
        ],
    )
    result = _build_step_instruction(step)
    annotations = result["annotations"]
    tts = next(a for a in annotations if a["type"] == "TTS")
    mode = next(a for a in annotations if a["type"] == "MODE")
    assert tts["position"]["offset"] == 4
    assert mode["position"]["offset"] == tts["position"]["offset"] + tts["position"]["length"] + 2


def test_ingredient_annotation():
    # "Add 2 onions, halved to bowl." -> "2 onions, halved" at offset 4, length 16
    step = RecipeStep(
        text="Add 2 onions, halved to bowl.",
        linked_ingredients=["2 onions, halved"],
    )
    result = _build_step_instruction(step)
    ing = next(a for a in result["annotations"] if a["type"] == "INGREDIENT")
    assert ing["position"]["offset"] == 4
    assert ing["position"]["length"] == 16
    assert ing["data"] == {"description": "2 onions, halved"}


def test_ingredient_not_in_text_is_skipped():
    step = RecipeStep(
        text="Add garlic.",
        linked_ingredients=["2 onions, halved"],
    )
    result = _build_step_instruction(step)
    assert "annotations" not in result


def test_ingredient_and_tts_both_present():
    step = RecipeStep(
        text="Add 2 onions, halved.",
        settings=[TTSSetting(time_seconds=60, speed="3", temperature=Temperature(value="65"))],
        linked_ingredients=["2 onions, halved"],
    )
    result = _build_step_instruction(step)
    types = {a["type"] for a in result["annotations"]}
    assert types == {"INGREDIENT", "TTS"}
```

- [ ] **Step 2: Run to verify they fail**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/test_step_builder.py -v -k "build_step or format_time"
```

Expected: `ImportError` — `_build_step_instruction`, `_format_time` not yet defined.

- [ ] **Step 3: Add helpers to `cookidoo_service.py`**

Add after the imports, before the `CookidooService` class. Also add `from schemas import RecipeStep, TTSSetting, ModeSetting` to the imports block.

```python
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
            settings_text = f"{setting.name.capitalize()} /{time_str}"
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
```

- [ ] **Step 4: Run all tests**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/test_step_builder.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cookidoo_service.py tests/test_step_builder.py
git commit -m "feat: add _build_step_instruction with TTS, MODE, INGREDIENT annotation support"
```

---

### Task 3: Wire structured steps through service and server

**Files:**
- Modify: `cookidoo_service.py` — update `create_custom_recipe` signature
- Modify: `server.py` — update `generate_recipe_structure` tool

- [ ] **Step 1: Update `create_custom_recipe` signature in `cookidoo_service.py`**

Change `steps: list[str]` to `steps: list[RecipeStep]` in the method signature and update the instructions line in `update_data`.

Old:
```python
async def create_custom_recipe(
    self,
    name: str,
    ingredients: list[str],
    steps: list[str],
    ...
```

New:
```python
async def create_custom_recipe(
    self,
    name: str,
    ingredients: list[str],
    steps: list[RecipeStep],
    ...
```

Old instructions line inside `update_data`:
```python
"instructions": [{"type": "STEP", "text": step} for step in steps],
```

New:
```python
"instructions": [_build_step_instruction(step) for step in steps],
```

- [ ] **Step 2: Update `generate_recipe_structure` in `server.py`**

Add `RecipeStep` to the import:
```python
from schemas import CustomRecipe, RecipeStep
```

Replace the entire `generate_recipe_structure` function:

```python
@mcp.tool()
async def generate_recipe_structure(
    name: str,
    ingredients: str,
    steps_json: str,
    servings: int = 4,
    prep_time: int = 30,
    total_time: int = 60,
    hints: str = "",
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

    Returns:
        str: Validated recipe structure in JSON format, ready for upload
    """
    import json as _json

    try:
        ingredients_list = [
            ing.strip()
            for ing in (
                ingredients.split("\n") if "\n" in ingredients else ingredients.split(",")
            )
            if ing.strip()
        ]

        try:
            raw_steps = _json.loads(steps_json)
        except _json.JSONDecodeError as e:
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

        recipe = CustomRecipe(
            name=name,
            ingredients=ingredients_list,
            steps=steps_list,
            servings=servings,
            prep_time=prep_time,
            total_time=total_time,
            hints=hints_list,
        )

        return f"Recipe structure validated successfully!\n\n{recipe.model_dump_json(indent=2)}\n\nYou can now use this with 'upload_custom_recipe'."

    except Exception as e:
        return f"Validation failed: {str(e)}\n\nPlease check your recipe data and try again."
```

- [ ] **Step 3: Verify server imports cleanly**

```bash
cd /Users/ep/projects/mcp-cookidoo
/Users/ep/.virtualenvs/cookidoo/bin/python -c "import server; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite**

```bash
/Users/ep/.virtualenvs/cookidoo/bin/python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cookidoo_service.py server.py
git commit -m "feat: wire TTSSetting/ModeSetting through service and MCP generate tool"
```

---

### Task 4: Smoke test end-to-end

**Files:** none (manual verification)

- [ ] **Step 1: Call `generate_recipe_structure` from Claude Desktop**

Use `fastmcp dev server.py` or restart Claude Desktop. Call the tool with:

```
name: "Annotation Test"
ingredients: "2 onions, halved\n30 g olive oil"
steps_json: [{"text":"Add 2 onions, halved to bowl.","settings":[{"type":"tts","time_seconds":5,"speed":"5"}],"linked_ingredients":["2 onions, halved"]},{"text":"Add olive oil.","settings":[{"type":"tts","time_seconds":300,"speed":"1","temperature":{"value":"120","unit":"C"}},{"type":"mode","name":"blend","time_seconds":30}]},{"text":"Preheat oven to 200°C."}]
servings: 2
prep_time: 5
total_time: 15
```

Expected: JSON output with annotations embedded.

- [ ] **Step 2: Upload and verify in the app**

Call `connect_to_cookidoo` then `upload_custom_recipe` with the JSON from Step 1.

Open the Cookidoo app, navigate to the new recipe, and verify:
- Step 1 shows the machine setting UI (5 sec / Speed 5) and ingredient link
- Step 2 shows both the TTS setting and Blend mode
- Step 3 is plain text

- [ ] **Step 3: Fix CCW character if needed**

If reverse direction shows `↺` as a literal character instead of the TM arrow icon, capture the actual PATCH from the app for a reverse step and update `_CCW_CHAR` in `cookidoo_service.py` to match the exact codepoint.

- [ ] **Step 4: Commit any fixups**

```bash
git add -p
git commit -m "fix: adjust annotation format based on smoke test"
```
