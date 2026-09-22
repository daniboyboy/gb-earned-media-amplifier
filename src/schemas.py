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


class QuoteAttribution(BaseModel):
    id: str = Field(description="A Q item ID, for example Q3")
    speaker: str | None = Field(description="Full name of the person quoted, or null if not a person's speech")
    organization: str | None


class SentenceAttribution(BaseModel):
    id: str = Field(description="An S item ID, for example S12")
    conveys_gb_spokesperson: bool
    speaker: str | None = Field(description="Full name of the GB spokesperson when conveys_gb_spokesperson is true, otherwise null")


class KeyMessageDraft(BaseModel):
    message: str = Field(description="One sentence, in your own words")
    supporting_id: str = Field(description="The Q or S item ID that supports the message")


class AnalystSelection(BaseModel):
    gb_spokespeople: list[Spokesperson]
    quote_attributions: list[QuoteAttribution]
    sentence_attributions: list[SentenceAttribution]
    coverage_type: Literal["expert_commentary", "feature", "announcement"]
    coverage_rationale: str
    key_messages: list[KeyMessageDraft]
    themes: list[str]
    other_organizations: list[OtherOrganization]