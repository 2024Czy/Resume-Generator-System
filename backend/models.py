from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PersonalInfo(BaseModel):
    name: str = ""
    age: int | None = None
    birth_date: str = ""
    phone: str = ""
    email: str = ""
    location: str = ""
    job_status: str = ""
    target_role: str = ""
    availability: str = ""


class EducationItem(BaseModel):
    period: str = ""
    school: str = ""
    major: str = ""
    degree: str = ""


class Highlight(BaseModel):
    label: str = ""
    content: str = ""


class ExperienceItem(BaseModel):
    period: str = ""
    organization: str = ""
    role: str = ""
    name: str = ""
    technologies: str = ""
    background: str = ""
    highlights: list[Highlight] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)


class SkillItem(BaseModel):
    category: str = ""
    description: str = ""


class ResumeData(BaseModel):
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ExperienceItem] = Field(default_factory=list)
    internships: list[ExperienceItem] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    summary: str = ""
    self_evaluation: str = ""
    other: dict[str, Any] = Field(default_factory=dict)
    photo_base64: str = ""
    source_filename: str = ""
    warnings: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    resume: ResumeData
    output_format: str = "docx"


class TextParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    engine: Literal["hybrid", "rules"] = "hybrid"
