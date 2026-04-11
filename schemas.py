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
