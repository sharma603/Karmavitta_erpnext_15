"""Karmavritta Face Recognition Service — FastAPI + InsightFace/ArcFace + ONNX Runtime."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.face_engine import FaceEngine, get_face_engine
from app.schemas.face import (
	EmbeddingResponse,
	ErrorResponse,
	HealthResponse,
	QualityResponse,
	RegisterMatchRequest,
	RegisterMatchResponse,
	VerifyMatchRequest,
	VerifyMatchResponse,
)
from app.services import matching, quality, recognition, security
from app.utils.image import decode_upload_bytes


@asynccontextmanager
async def lifespan(app: FastAPI):
	engine = get_face_engine()
	engine.initialize_model()
	app.state.face_engine = engine
	app.state.started_at = time.time()
	yield
	engine.shutdown()


app = FastAPI(
	title="Karmavritta Face Recognition Service",
	version="1.0.0",
	lifespan=lifespan,
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.cors_origins,
	allow_credentials=True,
	allow_methods=["GET", "POST"],
	allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
	request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
	request.state.request_id = request_id
	started = time.perf_counter()
	response = await call_next(request)
	elapsed_ms = (time.perf_counter() - started) * 1000
	response.headers["X-Request-ID"] = request_id
	response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
	return response


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
	security.validate_api_key(x_api_key)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
	detail = exc.detail
	if isinstance(detail, dict):
		payload = detail
	else:
		payload = {"success": False, "matched": False, "code": "HTTP_ERROR", "message": str(detail)}
	return JSONResponse(status_code=exc.status_code, content=payload)


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> Any:
	engine: FaceEngine = request.app.state.face_engine
	info = engine.diagnostics()
	return {
		"success": True,
		"status": "ok" if info.get("ready") else "degraded",
		"model_name": info.get("model_name"),
		"model_version": info.get("model_version"),
		"embedding_dimension": info.get("embedding_dimension"),
		"onnx_providers": info.get("onnx_providers"),
		"device": info.get("device"),
		"uptime_seconds": round(time.time() - request.app.state.started_at, 1),
	}


@app.post("/face/quality", response_model=QualityResponse, dependencies=[Depends(require_api_key)])
async def face_quality(request: Request, image: UploadFile = File(...)) -> Any:
	security.check_content_type(image.content_type)
	raw = await image.read()
	security.check_payload_size(len(raw))
	engine: FaceEngine = request.app.state.face_engine
	arr = decode_upload_bytes(raw)
	result = quality.assess_image(engine, arr)
	return result


@app.post("/face/embedding", response_model=EmbeddingResponse, dependencies=[Depends(require_api_key)])
async def face_embedding(
	request: Request,
	image: UploadFile = File(...),
	allow_multiple: bool = Form(False),
) -> Any:
	security.check_content_type(image.content_type)
	raw = await image.read()
	security.check_payload_size(len(raw))
	engine: FaceEngine = request.app.state.face_engine
	arr = decode_upload_bytes(raw)
	result = recognition.embed_from_image(engine, arr, allow_multiple=allow_multiple)
	# Never return embedding in logs; response is intentional for ERPNext store
	return result


@app.post("/face/register", response_model=RegisterMatchResponse, dependencies=[Depends(require_api_key)])
async def face_register(
	request: Request,
	image: UploadFile = File(...),
	templates_json: str = Form(...),
	exclude_employee: str | None = Form(None),
	company: str | None = Form(None),
) -> Any:
	"""Generate ArcFace embedding and check duplicates against provided active templates.

	ERPNext supplies the authorized template population (company-scoped).
	"""
	security.check_content_type(image.content_type)
	raw = await image.read()
	security.check_payload_size(len(raw))
	engine: FaceEngine = request.app.state.face_engine
	arr = decode_upload_bytes(raw)
	embed = recognition.embed_from_image(engine, arr, allow_multiple=False)
	if not embed.get("success"):
		raise HTTPException(status_code=400, detail=embed)

	templates = matching.parse_templates_json(templates_json, company=company)
	dup = matching.find_duplicate(
		embed["embedding"],
		templates,
		threshold=settings.face_duplicate_threshold,
		exclude_employee=exclude_employee,
		required_model=settings.model_name,
		required_version=settings.model_version,
		required_dim=settings.embedding_dimension,
	)
	if dup:
		return {
			"success": False,
			"code": "DUPLICATE_FACE",
			"message": (
				"This face is already registered with another employee. "
				"Please contact your administrator."
			),
			"score": dup["score"],
			"model_name": settings.model_name,
			"model_version": settings.model_version,
			"embedding_dimension": settings.embedding_dimension,
			# Embedding returned only on success path for storage
		}

	return {
		"success": True,
		"code": "OK",
		"message": "Face embedding ready for registration",
		"embedding": embed["embedding"],
		"model_name": settings.model_name,
		"model_version": settings.model_version,
		"embedding_dimension": settings.embedding_dimension,
		"template_version": settings.template_version,
		"quality": embed.get("quality"),
	}


@app.post("/face/verify", response_model=VerifyMatchResponse, dependencies=[Depends(require_api_key)])
async def face_verify(
	request: Request,
	image: UploadFile = File(...),
	templates_json: str = Form(...),
	company: str | None = Form(None),
) -> Any:
	"""1:N identify employee from image. Identity from top-1 match only."""
	security.check_content_type(image.content_type)
	raw = await image.read()
	security.check_payload_size(len(raw))
	engine: FaceEngine = request.app.state.face_engine
	arr = decode_upload_bytes(raw)
	embed = recognition.embed_from_image(engine, arr, allow_multiple=False)
	if not embed.get("success"):
		raise HTTPException(status_code=400, detail=embed)

	templates = matching.parse_templates_json(templates_json, company=company)
	match = matching.identify(
		embed["embedding"],
		templates,
		match_threshold=settings.face_match_threshold,
		margin=settings.face_match_margin,
		required_model=settings.model_name,
		required_version=settings.model_version,
		required_dim=settings.embedding_dimension,
	)
	if not match.get("matched"):
		return {
			"success": False,
			"matched": False,
			"code": match.get("code") or "NO_MATCH",
			"message": match.get("message") or "Face could not be verified.",
			"score": match.get("score"),
			"model_name": settings.model_name,
			"model_version": settings.model_version,
		}

	return {
		"success": True,
		"matched": True,
		"employee": match["employee"],
		"score": match["score"],
		"margin": match.get("margin"),
		"code": "OK",
		"message": "Face verified",
		"model_name": settings.model_name,
		"model_version": settings.model_version,
		"embedding_dimension": settings.embedding_dimension,
		# Do not echo embedding on verify by default
	}


@app.post("/face/match-embedding", response_model=VerifyMatchResponse, dependencies=[Depends(require_api_key)])
async def match_embedding(payload: VerifyMatchRequest) -> Any:
	"""1:N identify from a precomputed ArcFace embedding (same model only)."""
	match = matching.identify(
		payload.embedding,
		[t.model_dump() for t in payload.templates],
		match_threshold=settings.face_match_threshold,
		margin=settings.face_match_margin,
		required_model=settings.model_name,
		required_version=settings.model_version,
		required_dim=settings.embedding_dimension,
		company=payload.company,
	)
	if not match.get("matched"):
		return {
			"success": False,
			"matched": False,
			"code": match.get("code") or "NO_MATCH",
			"message": match.get("message") or "Face could not be verified.",
			"score": match.get("score"),
		}
	return {
		"success": True,
		"matched": True,
		"employee": match["employee"],
		"score": match["score"],
		"margin": match.get("margin"),
		"code": "OK",
		"message": "Face verified",
	}


@app.get("/diagnostics", dependencies=[Depends(require_api_key)])
def diagnostics(request: Request) -> Any:
	engine: FaceEngine = request.app.state.face_engine
	info = engine.diagnostics()
	return {
		"success": True,
		**info,
		"face_match_threshold": settings.face_match_threshold,
		"face_duplicate_threshold": settings.face_duplicate_threshold,
		"face_match_margin": settings.face_match_margin,
		"max_image_bytes": settings.max_image_bytes,
		# Never include embeddings
	}
