from typing import Literal

from pydantic import BaseModel, Field


class SupplierFacts(BaseModel):
    """Результат extractor-агента: структурированные факты из текста поставщика."""

    product_name: str = Field(description="Название товара из текста поставщика")
    characteristics: dict[str, str] = Field(
        default_factory=dict, description="Характеристики: ключ-значение"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Что не найдено в тексте (например: гарантия, цвет)",
    )


class CardDraft(BaseModel):
    """Результат generator-агента: черновик карточки товара."""

    title: str = Field(description="Заголовок карточки, до 60 символов")
    description: str = Field(description="Описание на 3-4 предложения")
    characteristics: dict[str, str] = Field(default_factory=dict)
    benefits: list[str] = Field(default_factory=list)


class CritiqueReport(BaseModel):
    """Результат critic-агента: вердикт и список проблем."""

    verdict: Literal["approve", "regenerate"] = Field(
        description="approve — карточка годится; regenerate — переделать"
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Список проблем: заголовок длиннее 60 символов, "
        "выдуманные характеристики, пустые поля и т.п.",
    )


class JobIn(BaseModel):
    supplier_text: str


class JobOut(BaseModel):
    id: str
    status: str
    attempts: int
    result: CardDraft | None = None
    error: str | None = None
