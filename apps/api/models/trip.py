from __future__ import annotations
from pydantic import BaseModel, Field


class KidAge(BaseModel):
    age: int = Field(ge=2, le=8)


class GroupComposition(BaseModel):
    infants: int = Field(default=0, ge=0)       # 0-2 years
    kids: list[KidAge] = Field(default_factory=list)  # 2-8 years
    adults: int = Field(default=1, ge=0)        # 8+ years
    seniors: int = Field(default=0, ge=0)       # 60+ years
    pets: int = Field(default=0, ge=0)

    @property
    def has_kids(self) -> bool:
        return len(self.kids) > 0

    @property
    def has_young_kids(self) -> bool:
        """Any child under 5 — triggers auto-Relaxed pace."""
        return any(k.age < 5 for k in self.kids)

    @property
    def has_infants(self) -> bool:
        return self.infants > 0


class AccommodationPrefs(BaseModel):
    style: list[str] = Field(default_factory=list)
    min_bedrooms: int = 1
    bathrooms: int = 1
    private_pool: bool = False
    kitchen: bool = False
    wheelchair_accessible: bool = False
    pet_friendly: bool = False


class Budget(BaseModel):
    amount: float
    currency: str = "USD"


class DestinationInput(BaseModel):
    city: str
    country: str = ""
    lat: float = 0.0
    lon: float = 0.0


class OriginInput(BaseModel):
    city: str
    iata: str = ""
    lat: float = 0.0
    lon: float = 0.0


class TripConfig(BaseModel):
    purpose: str = ""
    dates: dict = Field(default_factory=lambda: {"start": None, "end": None, "flexible": False})  # {"start": "YYYY-MM-DD" | null, "end": "YYYY-MM-DD" | null, "flexible": bool}
    scope: str = "international"   # "local" | "domestic" | "international"
    origin: OriginInput = Field(default_factory=lambda: OriginInput(city="", lat=0, lon=0))
    destination: DestinationInput | None = None
    destination_mode: str = "fixed"  # "fixed" | "exploring" | "country"
    destination_country: str | None = None  # used when mode = "country"
    hops: list[DestinationInput] = Field(default_factory=list)  # multi-stop, max 5
    themes: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    group: GroupComposition = Field(default_factory=GroupComposition)
    accommodation: AccommodationPrefs = Field(default_factory=AccommodationPrefs)
    pace: str = "moderate"  # "relaxed" | "moderate" | "packed"
    budget: Budget = Field(default_factory=lambda: Budget(amount=0, currency="USD"))

    def effective_pace(self) -> str:
        """Auto-apply Relaxed if any kid is under 5."""
        if self.group.has_young_kids and self.pace != "packed":
            return "relaxed"
        return self.pace
