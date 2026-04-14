from schemas import Temperature, TTSSetting, ModeSetting, RecipeStep, CustomRecipe
from cookidoo_service import _build_step_instruction, _format_time


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
    # "Blend." = 6 chars -> offset 8, "30 sec/speed 10" = 15 chars
    step = RecipeStep(
        text="Blend.",
        settings=[TTSSetting(time_seconds=30, speed="10")],
    )
    result = _build_step_instruction(step)
    assert result["text"] == "Blend.  30 sec/speed 10"
    tts = next(a for a in result["annotations"] if a["type"] == "TTS")
    assert tts["position"]["offset"] == 8
    assert tts["position"]["length"] == 15
    assert tts["data"] == {"speed": "10", "time": 30}


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


def test_mode_text_multi_word_name():
    step = RecipeStep(text="Warm.", settings=[ModeSetting(name="warm_up", time_seconds=60)])
    result = _build_step_instruction(step)
    assert "Warm_up" not in result["text"]
    assert "Warm Up /1 min" in result["text"]


def test_ingredient_and_tts_both_present():
    step = RecipeStep(
        text="Add 2 onions, halved.",
        settings=[TTSSetting(time_seconds=60, speed="3", temperature=Temperature(value="65"))],
        linked_ingredients=["2 onions, halved"],
    )
    result = _build_step_instruction(step)
    types = {a["type"] for a in result["annotations"]}
    assert types == {"INGREDIENT", "TTS"}


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
