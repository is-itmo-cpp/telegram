from pydantic import BaseModel, Field

from itmogus.sheets import SheetRef


class ExamState(BaseModel):
    tasks: SheetRef = Field(default_factory=SheetRef)
    log: SheetRef = Field(default_factory=SheetRef)
