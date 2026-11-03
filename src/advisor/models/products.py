"""Products, specifications, commercial data and catalog join reports."""

from __future__ import annotations

import warnings
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, computed_field, model_validator

from advisor.models.base import Contract, DataConsistencyWarning
from advisor.models.documents import Evidence
from advisor.models.enums import Category, CommercialStatus

SpecValue = str | int | float | bool | list[str]


class ProductSpecification(Contract):
    key: str = Field(min_length=1)  # canonical key from config/spec_registry.yaml
    value: SpecValue | None  # None = not found in source (never imputed)
    unit: str | None = None
    raw_value: str | None = None
    evidence: list[Evidence] = []


class CommercialInformation(Contract):
    """One catalog row. The catalog is the source of truth for status, price and stock."""

    part_number: str = Field(min_length=1)
    description: str
    manufacturer: str
    category: Category
    status: CommercialStatus
    discontinued_on: date | None = None
    last_buy_on: date | None = None
    price_usd: Decimal | None = Field(default=None, ge=0)
    stock_units: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _drop_computed(cls, data: Any) -> Any:
        # model_dump() includes the computed field; accept it back so dumps round-trip.
        if isinstance(data, dict) and "inventory_value_usd" in data:
            data = {k: v for k, v in data.items() if k != "inventory_value_usd"}
        return data

    @model_validator(mode="after")
    def _price_matches_status(self) -> CommercialInformation:
        if self.price_usd is not None and self.status is not CommercialStatus.ACTIVE:
            warnings.warn(
                f"{self.part_number}: price present but status is {self.status}",
                DataConsistencyWarning,
                stacklevel=2,
            )
        if self.price_usd is None and self.status is CommercialStatus.ACTIVE:
            warnings.warn(
                f"{self.part_number}: ACTIVE without price",
                DataConsistencyWarning,
                stacklevel=2,
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def inventory_value_usd(self) -> Decimal | None:
        if self.price_usd is None or self.stock_units is None:
            return None
        return self.price_usd * self.stock_units


class Product(Contract):
    part_number: str = Field(min_length=1)
    manufacturer: str
    category: Category
    family: str | None = None
    description: str | None = None
    specifications: list[ProductSpecification] = []
    commercial: CommercialInformation | None = None
    document_ids: list[str] = []
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> Product:
        keys = [s.key for s in self.specifications]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.part_number}: duplicated specification keys")
        if self.commercial and self.commercial.part_number != self.part_number:
            raise ValueError("commercial.part_number must match product part_number")
        return self


class PartMatch(Contract):
    part_number: str
    score: float = Field(ge=0.0, le=1.0)
    method: Literal["exact", "normalized", "fuzzy", "kg"]


class JoinReport(Contract):
    matched: dict[str, str] = {}  # part_number -> document_id
    unmatched_catalog: list[str] = []
    unmatched_documents: list[str] = []
    status_conflicts: list[str] = []  # datasheet status disagreeing with catalog (catalog wins)
    notes: list[str] = []
