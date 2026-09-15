"""Pydantic schemas — never include raw images."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TemplateItem(BaseModel):
	employee: str
	embedding: list[float]
	model_name: str | None = None
	model_version: str | None = None
	embedding_dimension: int | None = None
	company: str | None = None
	enabled: bool = True


class VerifyMatchRequest(BaseModel):
	embedding: list[float]
	templates: list[TemplateItem]
	company: str | None = None


class RegisterMatchRequest(BaseModel):
	embedding: list[float]
	templates: list[TemplateItem]
	exclude_employee: str | None = None
	company: str | None = None


class HealthResponse(BaseModel):
	success: bool
	status: str
	model_name: str | None = None
	model_version: str | None = None
	embedding_dimension: int | None = None
	onnx_providers: list[str] | None = None
	device: str | None = None
	uptime_seconds: float | None = None


class QualityResponse(BaseModel):
	success: bool
	code: str
	message: str
	face_count: int | None = None
	quality: dict[str, Any] | None = None


class EmbeddingResponse(BaseModel):
	success: bool
	code: str
	message: str
	embedding: list[float] | None = None
	model_name: str | None = None
	model_version: str | None = None
	embedding_dimension: int | None = None
	quality: dict[str, Any] | None = None


class RegisterMatchResponse(BaseModel):
	success: bool
	code: str
	message: str
	embedding: list[float] | None = None
	score: float | None = None
	model_name: str | None = None
	model_version: str | None = None
	embedding_dimension: int | None = None
	template_version: str | None = None
	quality: dict[str, Any] | None = None


class VerifyMatchResponse(BaseModel):
	success: bool
	matched: bool = False
	employee: str | None = None
	score: float | None = None
	margin: float | None = None
	code: str | None = None
	message: str | None = None
	model_name: str | None = None
	model_version: str | None = None
	embedding_dimension: int | None = None


class ErrorResponse(BaseModel):
	success: bool = False
	matched: bool = False
	code: str
	message: str
