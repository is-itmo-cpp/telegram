from pydantic import BaseModel, Field

from itmogus.sheets import SheetRef


class ReviewState(BaseModel):
    requests: SheetRef = Field(default_factory=SheetRef)
