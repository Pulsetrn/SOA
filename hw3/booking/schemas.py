from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    flight_id: UUID
    passenger_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    passenger_email: EmailStr = Field(max_length=254)
    seat_count: int = Field(gt=0, le=2147483647, strict=True)


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    flight_id: UUID
    passenger_name: str
    passenger_email: str
    seat_count: int
    total_price: Decimal
    status: Literal["CONFIRMED", "CANCELLED"]
    created_at: datetime


class FlightResponse(BaseModel):
    id: UUID
    flight_number: str
    airline: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    total_seats: int
    available_seats: int
    price: Decimal
    status: Literal["SCHEDULED", "DEPARTED", "CANCELLED", "COMPLETED"]
