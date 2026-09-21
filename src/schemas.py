from typing import Literal
from pydantic import BaseModel, Field


class Article(BaseModel):
    url: str
    outlet: str | None = None
    title: str | None = None
    published_date: str | None = None
    region: str
    text: str
    source: Literal["url", "manual"]


class Spokesperson(BaseModel):
    name: str
    title: str
    location: str | None


class Statement(BaseModel):
    speaker: str
    text: str = Field(description="Copied exactly from the article, without quotation marks")
    type: Literal["direct_quote", "paraphrase"]


class KeyMessage(BaseModel):
    message: str = Field(description="One sentence, in your own words")
    supporting_excerpt: str = Field(description="A sentence copied exactly from the article")


class OtherOrganization(BaseModel):
    name: str
    relation: Literal["competitor", "legal", "regulator", "other"]
    spokesperson: str | None


class ArticleAnalysis(BaseModel):
    coverage_type: Literal["expert_commentary", "feature", "announcement"]
    coverage_rationale: str
    gb_spokespeople: list[Spokesperson]
    gb_statements: list[Statement]
    key_messages: list[KeyMessage]
    themes: list[str]
    other_organizations: list[OtherOrganization]