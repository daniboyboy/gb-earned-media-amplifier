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


class LinkedInPost(BaseModel):
    channel: Literal["company_page", "spokesperson", "employee_advocacy"]
    angle: str = Field(description="One line: what this post emphasises")
    body: str = Field(description="Post text without any URL or hashtags")
    quote_used: str | None = Field(description="Exact QUOTABLE text used inside quotation marks, or null")
    hashtags: list[str]


class AmplificationPlan(BaseModel):
    primary_angle: str
    rationale: str
    posts: list[LinkedInPost]


class PublishablePost(BaseModel):
    channel: str
    angle: str
    text: str
    quote_used: str | None
    character_count: int


class AmplificationKit(BaseModel):
    article_url: str
    outlet: str | None
    title: str | None
    primary_angle: str
    rationale: str
    posts: list[PublishablePost]


class JudgedClaim(BaseModel):
    phrase: str = Field(description="A short, exact substring copied from the draft")
    verdict: Literal["supported", "unsupported", "distorted", "misattributed"]
    evidence: str | None = Field(description="The article sentence that supports or contradicts the claim, or null if none")
    explanation: str


class FidelityVerdict(BaseModel):
    claims: list[JudgedClaim]


class RuleCheck(BaseModel):
    rule_id: str
    passed: bool
    phrase: str | None = Field(description="If the rule fails, a short exact substring from the draft that breaks it; otherwise null")
    explanation: str


class VoiceChecklist(BaseModel):
    checks: list[RuleCheck]


class ReviewIssue(BaseModel):
    phrase: str
    category: str
    severity: Literal["blocker", "warning"]
    explanation: str
    source: Literal["rule", "judge"]


class PostReview(BaseModel):
    channel: str
    approved: bool
    issues: list[ReviewIssue]


class KitReview(BaseModel):
    title: str | None
    posts: list[PostReview]
