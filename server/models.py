from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from zoneinfo import ZoneInfo
from pathlib import Path
import os

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Event(Strict):
    collection_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    revlog_id: int = Field(gt=0)
    card_id: int = Field(gt=0)
    duration_ms: int = Field(ge=0, le=600_000)
    rating: int | None = Field(default=None, ge=1, le=4)
    @property
    def key(self): return f'{self.collection_id}:{self.revlog_id}:{self.card_id}'

class Events(Strict):
    events: list[Event] = Field(max_length=1000)
    device_id: str = Field(default='unknown',min_length=1,max_length=100)

class Retractions(Strict):
    ids: list[str] = Field(max_length=1000)

class Deck(Strict):
    id: str = Field(min_length=1, max_length=32, pattern=r'^\d+$')
    name: str = Field(min_length=1, max_length=512)
    new: int = Field(ge=0)
    review: int = Field(ge=0)
    learning: int = Field(ge=0)

class Snapshot(Strict):
    device_id: str = Field(min_length=1, max_length=100)
    collection_id: str = Field(default='primary', min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    applied_revision: int = Field(default=0, ge=0)
    label: str = Field(min_length=1, max_length=100)
    decks: list[Deck] = Field(max_length=10000)
    sync_status: str = Field(default='unknown',max_length=300)
    collection_synced_ms: int = Field(default=0,ge=0)

class Settings(Strict):
    revision: int = Field(ge=0)
    timezone: str = 'America/New_York'
    rollover_minute: int = Field(default=0, ge=0, le=1439)
    lesson_answers: int = Field(default=10, ge=1, le=10000)
    lesson_ms: int = Field(default=300000, ge=0, le=36000000)
    parent_deck_id: str = ''
    clearance: Literal['new_only', 'new_and_reviews'] = 'new_and_reviews'
    skin_id: str = os.environ.get('ANKI_COMPANION_SKIN') or ('eren_anki' if (Path(__file__).resolve().parents[1]/'skins/eren_anki/skin.json').exists() else 'study_companion')
    skin_version: str = '1.0.0'
    update_repository: str = Field(default='ldf97/AnkiCompanion',max_length=150,pattern=r'^(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?$')
    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try: ZoneInfo(value)
        except Exception as exc: raise ValueError('Unknown IANA timezone') from exc
        return value

class Command(Strict):
    device_id: str = Field(min_length=1, max_length=100)
    action: Literal['study', 'sync']
    deck_id: str = Field(default='', max_length=32, pattern=r'^\d*$')
)
    applied_revision: int = Field(default=0, ge=0)
    label: str = Field(min_length=1, max_length=100)
    decks: list[Deck] = Field(max_length=10000)
    sync_status: str = Field(default='unknown',max_length=300)
    collection_synced_ms: int = Field(default=0,ge=0)

class Settings(Strict):
    revision: int = Field(ge=0)
    timezone: str = 'America/New_York'
    rollover_minute: int = Field(default=0, ge=0, le=1439)
    lesson_answers: int = Field(default=10, ge=1, le=10000)
    lesson_ms: int = Field(default=300000, ge=0, le=36000000)
    parent_deck_id: str = ''
    clearance: Literal['new_only', 'new_and_reviews'] = 'new_and_reviews'
    skin_id: str = os.environ.get('ANKI_COMPANION_SKIN') or ('eren_anki' if (Path(__file__).resolve().parents[1]/'skins/eren_anki/skin.json').exists() else 'study_companion')
    skin_version: str = '1.0.0'
    update_repository: str = Field(default='ldf97/AnkiCompanion',max_length=150,pattern=r'^(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?$')
    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try: ZoneInfo(value)
        except Exception as exc: raise ValueError('Unknown IANA timezone') from exc
        return value

class Command(Strict):
    device_id: str = Field(min_length=1, max_length=100)
    action: Literal['study', 'sync']
    deck_id: str = Field(default='', max_length=32, pattern=r'^\d*$')
