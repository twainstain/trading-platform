"""Base configuration loader — JSON file to frozen dataclass.

Products subclass BaseConfig and add their own fields. The base handles:
  - Loading from JSON file
  - Auto-converting float/int to Decimal for financial fields
  - Validation hook
  - Serialization back to dict

Usage:
    @dataclass(frozen=True)
    class MyConfig(BaseConfig):
        pair: str = ""
        trade_size: Decimal = Decimal("1")
        min_profit: Decimal = Decimal("0.001")

        def validate(self) -> None:
            if self.trade_size <= 0:
                raise ValueError("trade_size must be positive")

    config = MyConfig.from_file("config/my_config.json")
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BaseConfig:
    """Base configuration class. Products subclass and add fields."""

    def __post_init__(self) -> None:
        """Auto-convert numeric fields to Decimal where the type hint is Decimal."""
        for f in fields(self):
            if f.type == "Decimal" or (isinstance(f.type, type) and issubclass(f.type, Decimal)):
                val = getattr(self, f.name)
                if not isinstance(val, Decimal):
                    try:
                        object.__setattr__(self, f.name, Decimal(str(val)))
                    except (InvalidOperation, ValueError):
                        pass

    @classmethod
    def from_file(cls, path: str | Path, **overrides: Any) -> "BaseConfig":
        """Load config from a JSON file.

        Extra keys in the JSON that don't match dataclass fields are ignored.
        Overrides are applied after loading from file.
        """
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw, **overrides)

    @classmethod
    def from_dict(cls, data: dict, **overrides: Any) -> "BaseConfig":
        """Create config from a dict, filtering to known fields only."""
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        filtered.update(overrides)
        instance = cls(**filtered)
        instance.validate()
        return instance

    def validate(self) -> None:
        """Override in subclass to add validation rules."""
        pass

    def to_dict(self) -> dict:
        """Serialize back to a dict (Decimals become strings)."""
        d = asdict(self)
        for key, val in d.items():
            if isinstance(val, Decimal):
                d[key] = str(val)
        return d
