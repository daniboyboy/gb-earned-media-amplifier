from typing import Literal
from pydantic import BaseModel


class Article(BaseModel):
    url: str
    outlet: str | None = None
    title: str | None = None
    published_date: str | None = None
    region: str
    text: str
    source: Literal["url", "manual"]