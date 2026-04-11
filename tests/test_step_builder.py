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
