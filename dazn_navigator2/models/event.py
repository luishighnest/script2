from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any
from datetime import datetime

class Image(BaseModel):
    url: Optional[str] = Field(default=None, alias="Id")
    width: Optional[int] = None
    height: Optional[int] = None
    model_config = ConfigDict(extra='ignore', populate_by_name=True)

class Sport(BaseModel):
    id: Optional[str] = Field(default=None, alias="Id")
    name: Optional[str] = Field(default="Unknown Sport", alias="Title")
    model_config = ConfigDict(extra='ignore', populate_by_name=True)

class Competition(BaseModel):
    id: Optional[str] = Field(default=None, alias="Id")
    name: Optional[str] = Field(default="Unknown Competition", alias="Title")
    model_config = ConfigDict(extra='ignore', populate_by_name=True)

class BaseItem(BaseModel):
    id: str = Field(default="N/A", alias="Id")
    asset_id: Optional[str] = Field(default=None, alias="AssetId")
    title: str = Field(default="Senza Titolo", alias="Title")
    description: Optional[str] = Field(default=None, alias="Description")
    start_time: Optional[datetime] = Field(default=None, alias="Start")
    end_time: Optional[datetime] = Field(default=None, alias="End")
    status: Optional[str] = Field(default="UNKNOWN", alias="Status")
    images: List[Image] = Field(default_factory=list, alias="Images")
    duration: Optional[int] = Field(default=None, alias="Duration")
    sport: Optional[Sport] = Field(default=None, alias="Sport")
    competition: Optional[Competition] = Field(default=None, alias="Competition")
    raw_data: Optional[Any] = None

    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True
    )

    def __init__(self, **data):
        super().__init__(**data)
        self.raw_data = data

    @property
    def cover_image(self) -> str:
        return self.images[0].url if self.images else "N/A"

class Event(BaseItem):
    pass

class Channel(BaseItem):
    pass

class CatalogueResponse(BaseModel):
    items: List[Event] = []