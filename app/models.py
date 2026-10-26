from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Theme = Literal['Dividendenqualität', 'KI & Wachstum', 'Chancen']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Mandate(StrictModel):
    owner: str = Field(default='Meine VV-GmbH', min_length=1, max_length=100)
    capital: Decimal = Field(default=Decimal('0'), ge=0, le=Decimal('1e10'))
    contribution: Decimal = Field(default=Decimal('0'), ge=0, le=Decimal('1e9'))
    interval_months: int = Field(default=6, ge=1, le=120)
    broker: str = Field(default='Trade Republic · Firmendepot', max_length=100)
    horizon: str = Field(default='Langfristiger Vermögensaufbau', max_length=200)
    risk_note: str = Field(default='Mischung aus Dividendenqualität und chancenreicheren Unternehmen. Persönliche Verlustgrenze noch nicht festgelegt.', max_length=1200)
    themes: list[Theme] = Field(default_factory=lambda: ['Dividendenqualität','KI & Wachstum','Chancen'], min_length=1, max_length=3)
    interests: str = Field(default='Weltweit; ausdrücklich chinesische KI-Unternehmen, Tencent und SpaceX / Raumfahrt.', max_length=1000)
    reserve_confirmed: bool = False

class ConnectionInput(StrictModel):
    provider: Literal['bedrock','anthropic'] = 'bedrock'
    model_id: str = Field(default='', max_length=250)
    region: str = Field(default='eu-central-1', max_length=64)
    aws_profile: str = Field(default='', max_length=100)
    brave_key: str | None = Field(default=None, max_length=500)
    anthropic_key: str | None = Field(default=None, max_length=500)
    clear_secrets: bool = False

class ResearchRequest(StrictModel):
    topic: str = Field(min_length=3, max_length=400)
    themes: list[Theme] = Field(default_factory=lambda: ['Dividendenqualität','KI & Wachstum','Chancen'], min_length=1, max_length=3)
    mode: Literal['discover','company'] = 'discover'
    max_candidates: int = Field(default=3, ge=1, le=3)
    @field_validator('topic')
    @classmethod
    def public_only(cls, v):
        import re
        if re.search(r'\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){10,30}\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}', v, re.I):
            raise ValueError('Nur öffentliche Recherchebegriffe eingeben, keine IBAN oder E-Mail-Adresse.')
        return v

class WatchItem(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    theme: Theme = 'KI & Wachstum'
    question: str = Field(default='', max_length=1200)
    instrument: str = Field(default='',max_length=100)
    broker_status: Literal['Ungeprüft','In meiner App gefunden','Nicht verfügbar'] = 'Ungeprüft'
    note: str = Field(default='',max_length=2500)

class DecisionInput(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    decision: Literal['Beobachten','Vertieft prüfen','Verwerfen','Eigene Entscheidung dokumentiert']
    note: str = Field(min_length=3,max_length=4000)
    run_id: str | None = Field(default=None,max_length=64)

class ValuationInput(StrictModel):
    instrument: str = Field(min_length=1,max_length=100)
    currency: Literal['EUR','USD','HKD','CNY','GBP','CHF','JPY']
    price: Decimal = Field(gt=0,le=Decimal('1e10'))
    as_of: datetime
    eps: Decimal | None = Field(default=None,ge=Decimal('-1e10'),le=Decimal('1e10'))
    dividend_per_share: Decimal | None = Field(default=None,ge=0,le=Decimal('1e10'))
    period: str = Field(min_length=3,max_length=150)
    source_note: str = Field(min_length=3,max_length=500)

class Fact(StrictModel):
    text: str = Field(min_length=3,max_length=650)
    source_id: str = Field(min_length=1,max_length=20)
    excerpt: str = Field(min_length=12,max_length=360)

class Candidate(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    theme: Theme
    instrument: str = Field(default='',max_length=120)
    thesis: str = Field(min_length=10,max_length=1500)
    why_now: str = Field(min_length=5,max_length=1200)
    bear_case: str = Field(min_length=10,max_length=1500)
    dividend: str = Field(min_length=5,max_length=1000)
    valuation: str = Field(min_length=5,max_length=1200)
    china_risks: list[str] = Field(default_factory=list,max_length=6)
    open_questions: list[str] = Field(min_length=1,max_length=8)
    source_ids: list[str] = Field(min_length=1,max_length=10)
    facts: list[Fact] = Field(default_factory=list,max_length=5)
    verdict: Literal['Vertieft prüfen','Beobachten','Daten fehlen','Verwerfen']

class Analysis(StrictModel):
    summary: str = Field(min_length=5,max_length=1200)
    candidates: list[Candidate] = Field(default_factory=list,max_length=3)

class Discovered(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    theme: Theme
    reason_to_research: str = Field(min_length=5,max_length=400)
    discovery_source_ids: list[str] = Field(min_length=1,max_length=5)

class Discovery(StrictModel):
    candidates: list[Discovered] = Field(default_factory=list,max_length=3)

class Challenge(StrictModel):
    name: str = Field(max_length=100)
    strongest_objection: str = Field(min_length=5,max_length=1500)
    unsupported_facts: list[int] = Field(default_factory=list,max_length=5)
    missing_checks: list[str] = Field(default_factory=list,max_length=8)
    source_ids: list[str] = Field(default_factory=list,max_length=10)

class Review(StrictModel):
    reviews: list[Challenge] = Field(default_factory=list,max_length=3)
