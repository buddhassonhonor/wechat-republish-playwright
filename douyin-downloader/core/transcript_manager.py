import asyncio
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import aiohttp

from config import ConfigLoader
from storage import Database, FileManager
from utils.logger import setup_logger

logger = setup_logger("TranscriptManager")


class TranscriptManager:
    def __init__(
        self,
        config: ConfigLoader,
        file_manager: FileManager,
        database: Optional[Database] = None,
    ):
        self.config = config
        self.file_manager = file_manager
        self.database = database

    def _cfg(self) -> Dict[str, Any]:
        return self.config.get("transcript", {}) or {}

    def _enabled(self) -> bool:
        return bool(self._cfg().get("enabled", False))

    def _transcription_backend(self) -> str:
        backend = str(self._cfg().get("backend", "openai_api")).strip().lower()
        if backend in {"faster_whisper", "faster_whisper_local", "local"}:
            return "faster_whisper_local"
        return "openai_api"

    def _using_local_backend(self) -> bool:
        return self._transcription_backend() == "faster_whisper_local"

    def _model(self) -> str:
        return str(self._cfg().get("model", "gpt-4o-mini-transcribe")).strip()

    def _local_model(self) -> str:
        return str(self._cfg().get("local_model", "distil-large-v3")).strip()

    def _job_model_label(self) -> str:
        if self._using_local_backend():
            return f"faster-whisper:{self._local_model()}"
        return self._model()

    def _response_formats(self) -> List[str]:
        formats = self._cfg().get("response_formats", ["txt", "json"])
        if not isinstance(formats, list):
            return ["txt", "json"]
        normalized = [str(item).strip().lower() for item in formats if str(item).strip()]
        return normalized or ["txt", "json"]

    def _local_device(self) -> str:
        return str(self._cfg().get("local_device", "cuda")).strip() or "cuda"

    def _local_compute_type(self) -> str:
        value = str(self._cfg().get("local_compute_type", "float16")).strip()
        return value or "float16"

    def _local_beam_size(self) -> int:
        try:
            value = int(self._cfg().get("local_beam_size", 5) or 5)
        except (TypeError, ValueError):
            value = 5
        return max(1, value)

    def _local_vad_filter(self) -> bool:
        return bool(self._cfg().get("local_vad_filter", True))

    def _audio_transcription_enabled(self) -> bool:
        return bool(self._cfg().get("enabled", False))

    def _audio_chunk_seconds(self) -> int:
        try:
            value = int(self._cfg().get("audio_chunk_seconds", 150) or 150)
        except (TypeError, ValueError):
            value = 150
        return max(30, value)

    def _audio_force_chunking_above_seconds(self) -> int:
        try:
            value = int(
                self._cfg().get("audio_force_chunking_above_seconds", 120) or 120
            )
        except (TypeError, ValueError):
            value = 120
        return max(30, value)

    def _audio_min_text_chars(self) -> int:
        try:
            value = int(self._cfg().get("audio_min_text_chars", 40) or 40)
        except (TypeError, ValueError):
            value = 40
        return max(1, value)

    def _ocr_enabled(self) -> bool:
        return bool(self._cfg().get("ocr_enabled", False))

    def _subtitle_enabled(self) -> bool:
        return bool(self._cfg().get("subtitle_enabled", True))

    def _ocr_frame_interval_seconds(self) -> float:
        try:
            value = float(self._cfg().get("ocr_frame_interval_seconds", 2.0) or 2.0)
        except (TypeError, ValueError):
            value = 2.0
        return max(0.5, value)

    def _ocr_max_frames(self) -> int:
        try:
            value = int(self._cfg().get("ocr_max_frames", 12) or 12)
        except (TypeError, ValueError):
            value = 12
        return max(1, value)

    def _ocr_min_text_length(self) -> int:
        try:
            value = int(self._cfg().get("ocr_min_text_length", 6) or 6)
        except (TypeError, ValueError):
            value = 6
        return max(1, value)

    def _ensure_ocr_engine(self):
        if not self._ocr_enabled():
            return None

        if hasattr(self, "_ocr_engine"):
            return self._ocr_engine

        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as exc:
            logger.warning("OCR engine unavailable: %s", exc)
            self._ocr_engine = None
            return None

        try:
            self._ocr_engine = RapidOCR()
        except Exception as exc:
            logger.warning("Failed to initialize OCR engine: %s", exc)
            self._ocr_engine = None
        return self._ocr_engine

    @staticmethod
    def _normalize_text_lines(lines: List[str]) -> str:
        cleaned: List[str] = []
        seen: set[str] = set()
        for raw_line in lines:
            line = re.sub(r"\s+", " ", str(raw_line or "")).strip()
            if not line:
                continue
            if line in seen:
                continue
            seen.add(line)
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _ensure_local_whisper_model(self):
        if not self._using_local_backend():
            return None

        if hasattr(self, "_local_whisper_model"):
            return self._local_whisper_model

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            logger.warning("Local faster-whisper backend unavailable: %s", exc)
            self._local_whisper_model = None
            return None

        try:
            self._local_whisper_model = WhisperModel(
                self._local_model(),
                device=self._local_device(),
                compute_type=self._local_compute_type(),
            )
        except Exception as exc:
            logger.warning("Failed to initialize faster-whisper model: %s", exc)
            self._local_whisper_model = None
        return self._local_whisper_model

    @staticmethod
    def _classify_audio_error(exc: Exception) -> str:
        message = str(exc).strip()
        return message or exc.__class__.__name__.lower()

    def _resolve_api_key(self) -> str:
        transcript_cfg = self._cfg()
        api_key_env = str(transcript_cfg.get("api_key_env", "OPENAI_API_KEY")).strip()
        if api_key_env:
            env_value = os.getenv(api_key_env, "").strip()
            if env_value:
                return env_value

        return str(transcript_cfg.get("api_key", "")).strip()

    def _api_url(self) -> str:
        api_url = str(
            self._cfg().get(
                "api_url", "https://api.openai.com/v1/audio/transcriptions"
            )
        ).strip()
        return api_url or "https://api.openai.com/v1/audio/transcriptions"

    def resolve_output_dir(self, video_path: Path) -> Path:
        video_path = Path(video_path)
        video_dir = video_path.parent
        output_dir = str(self._cfg().get("output_dir", "")).strip()
        if not output_dir:
            return video_dir

        output_root = Path(output_dir)
        try:
            relative_dir = video_dir.resolve().relative_to(
                self.file_manager.base_path.resolve()
            )
            return output_root / relative_dir
        except Exception:
            logger.warning(
                "Failed to mirror transcript path for video %s, fallback to video dir",
                video_path,
            )
            return video_dir

    def build_output_paths(self, video_path: Path) -> Tuple[Path, Path]:
        video_path = Path(video_path)
        output_dir = self.resolve_output_dir(video_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = video_path.stem
        return (
            output_dir / f"{stem}.transcript.txt",
            output_dir / f"{stem}.transcript.json",
        )

    async def process_video(self, video_path: Path, aweme_id: str) -> Dict[str, Any]:
        video_path = Path(video_path)

        if not self._enabled():
            return {"status": "skipped", "reason": "disabled"}

        text_path, json_path = self.build_output_paths(video_path)
        model = self._job_model_label()
        payload: Dict[str, Any] = {}
        extracted_text = ""
        source = ""
        audio_transcription_error = ""

        try:
            if self._audio_transcription_enabled():
                try:
                    if self._using_local_backend():
                        payload = await self._transcribe_local_audio_from_video(
                            video_path=video_path,
                            model=self._local_model(),
                        )
                    else:
                        api_key = self._resolve_api_key()
                        if not api_key:
                            audio_transcription_error = "missing_api_key"
                        else:
                            payload = await self._transcribe_audio_from_video(
                                api_key=api_key,
                                video_path=video_path,
                                model=self._model(),
                            )

                    if payload:
                        extracted_text = str(payload.get("text", "")).strip()
                        source = "audio"
                        min_chars = self._audio_min_text_chars()
                        duration_seconds = float(payload.get("duration_seconds") or 0)
                        if (
                            duration_seconds
                            >= self._audio_force_chunking_above_seconds()
                            and len(extracted_text) < min_chars
                        ):
                            logger.warning(
                                "Audio transcript too short for aweme %s: duration=%.2fs, chars=%s",
                                aweme_id,
                                duration_seconds,
                                len(extracted_text),
                            )
                            audio_transcription_error = "audio_transcript_too_short"
                            extracted_text = ""
                            source = ""
                except Exception as exc:
                    audio_transcription_error = self._classify_audio_error(exc)
                    logger.warning(
                        "Audio transcription unavailable for aweme %s via %s: %s",
                        aweme_id,
                        self._transcription_backend(),
                        audio_transcription_error,
                    )

            if not extracted_text and self._ocr_enabled():
                ocr_text = await self._extract_text_from_video_ocr(video_path)
                if ocr_text:
                    extracted_text = ocr_text
                    payload = {
                        "text": ocr_text,
                        "source": "ocr",
                        "aweme_id": aweme_id,
                        "audio_reason": audio_transcription_error or "audio_unavailable",
                    }
                    source = "ocr"

            if not extracted_text and self._subtitle_enabled():
                subtitle_text = await self._extract_text_from_subtitles(video_path)
                if subtitle_text:
                    extracted_text = subtitle_text
                    payload = {
                        "text": subtitle_text,
                        "source": "subtitle",
                        "aweme_id": aweme_id,
                        "audio_reason": audio_transcription_error or "audio_unavailable",
                    }
                    source = "subtitle"

            if not extracted_text:
                if not self._ocr_enabled() and not self._subtitle_enabled():
                    skip_reason = audio_transcription_error or "no_text_found"
                else:
                    skip_reason = "no_text_found"
                await self._record_job(
                    aweme_id=aweme_id,
                    video_path=video_path,
                    transcript_dir=text_path.parent,
                    text_path=text_path,
                    json_path=json_path,
                    model=model,
                    status="skipped",
                    skip_reason=skip_reason,
                    error_message=None,
                )
                logger.warning(
                    "Transcript skipped for aweme %s: %s", aweme_id, skip_reason
                )
                return {"status": "skipped", "reason": skip_reason}

            if not payload:
                payload = {
                    "text": extracted_text,
                    "source": source or "audio",
                    "aweme_id": aweme_id,
                }
            else:
                payload["aweme_id"] = aweme_id
                payload["source"] = source or str(payload.get("source", "audio"))
            await self._write_outputs(payload, text_path, json_path)
            await self._record_job(
                aweme_id=aweme_id,
                video_path=video_path,
                transcript_dir=text_path.parent,
                text_path=text_path,
                json_path=json_path,
                model=model,
                status="success",
                skip_reason=None,
                error_message=None,
            )
            return {
                "status": "success",
                "text_path": str(text_path),
                "json_path": str(json_path),
                "source": source or "audio",
            }
        except Exception as exc:
            error_message = str(exc)
            await self._record_job(
                aweme_id=aweme_id,
                video_path=video_path,
                transcript_dir=text_path.parent,
                text_path=text_path,
                json_path=json_path,
                model=model,
                status="failed",
                skip_reason=None,
                error_message=error_message,
            )
            logger.error("Transcript failed for aweme %s: %s", aweme_id, error_message)
            return {
                "status": "failed",
                "reason": "transcription_error",
                "error": error_message,
            }

    async def process_images(self, image_paths: List[Path], aweme_id: str) -> Dict[str, Any]:
        if not self._enabled():
            return {"status": "skipped", "reason": "disabled"}
        if not self._ocr_enabled():
            return {"status": "skipped", "reason": "ocr_disabled"}

        normalized_paths = [Path(path) for path in image_paths if path]
        if not normalized_paths:
            return {"status": "skipped", "reason": "no_images"}

        first_path = normalized_paths[0]
        reference_path = first_path.parent / f"{aweme_id}.jpg"
        text_path, json_path = self.build_output_paths(reference_path)
        try:
            extracted_text = await self._extract_text_from_images(normalized_paths)
            if not extracted_text:
                await self._record_job(
                    aweme_id=aweme_id,
                    video_path=reference_path,
                    transcript_dir=text_path.parent,
                    text_path=text_path,
                    json_path=json_path,
                    model=f"{self._job_model_label()}+ocr",
                    status="skipped",
                    skip_reason="no_text_found",
                    error_message=None,
                )
                logger.warning("OCR skipped for aweme %s: no_text_found", aweme_id)
                return {"status": "skipped", "reason": "no_text_found"}

            payload = {
                "text": extracted_text,
                "source": "ocr",
                "aweme_id": aweme_id,
            }
            await self._write_outputs(payload, text_path, json_path)
            await self._record_job(
                aweme_id=aweme_id,
                video_path=reference_path,
                transcript_dir=text_path.parent,
                text_path=text_path,
                json_path=json_path,
                model=f"{self._job_model_label()}+ocr",
                status="success",
                skip_reason=None,
                error_message=None,
            )
            return {
                "status": "success",
                "text_path": str(text_path),
                "json_path": str(json_path),
                "source": "ocr",
            }
        except Exception as exc:
            error_message = str(exc)
            await self._record_job(
                aweme_id=aweme_id,
                video_path=reference_path,
                transcript_dir=text_path.parent,
                text_path=text_path,
                json_path=json_path,
                model=f"{self._job_model_label()}+ocr",
                status="failed",
                skip_reason=None,
                error_message=error_message,
            )
            logger.error("OCR failed for aweme %s: %s", aweme_id, error_message)
            return {
                "status": "failed",
                "reason": "ocr_error",
                "error": error_message,
            }

    async def _write_outputs(
        self, payload: Dict[str, Any], text_path: Path, json_path: Path
    ) -> None:
        formats = set(self._response_formats())

        if "txt" in formats:
            text = str(payload.get("text", "")).strip()
            async with aiofiles.open(text_path, "w", encoding="utf-8") as f:
                await f.write(text)

        if "json" in formats:
            async with aiofiles.open(json_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(payload, ensure_ascii=False, indent=2))

    async def _call_openai_transcription(
        self, api_key: str, media_path: Path, model: str
    ) -> Dict[str, Any]:
        if not media_path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        transcript_cfg = self._cfg()
        language_hint = str(transcript_cfg.get("language_hint", "")).strip()
        api_url = self._api_url()

        form = aiohttp.FormData()
        form.add_field("model", model)
        form.add_field("response_format", "json")
        if language_hint:
            form.add_field("language", language_hint)

        content_type = self._guess_media_content_type(media_path)
        with media_path.open("rb") as f:
            form.add_field(
                "file",
                f,
                filename=media_path.name,
                content_type=content_type,
            )
            timeout = aiohttp.ClientTimeout(total=600)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    api_url,
                    data=form,
                    headers={"Authorization": f"Bearer {api_key}"},
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise RuntimeError(
                            f"OpenAI transcription failed: status={response.status}, body={body}"
                        )

                    payload = await response.json(content_type=None)
                    if not isinstance(payload, dict):
                        raise RuntimeError("OpenAI transcription returned invalid payload")
                    return payload

    async def _call_local_transcription(
        self, media_path: Path, model: str
    ) -> Dict[str, Any]:
        if not media_path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        whisper_model = self._ensure_local_whisper_model()
        if whisper_model is None:
            raise RuntimeError("local_backend_unavailable")

        transcript_cfg = self._cfg()
        language_hint = str(transcript_cfg.get("language_hint", "")).strip() or None
        beam_size = self._local_beam_size()
        vad_filter = self._local_vad_filter()

        def _run_transcribe() -> Dict[str, Any]:
            segments, info = whisper_model.transcribe(
                str(media_path),
                language=language_hint,
                beam_size=beam_size,
                vad_filter=vad_filter,
                condition_on_previous_text=False,
            )
            texts = [str(segment.text or "").strip() for segment in segments]
            return {
                "text": self._merge_transcript_texts(texts),
                "language": getattr(info, "language", language_hint),
                "source": "audio",
                "model": model,
            }

        return await asyncio.to_thread(_run_transcribe)

    async def _transcribe_audio_from_video(
        self, *, api_key: str, video_path: Path, model: str
    ) -> Dict[str, Any]:
        ffmpeg_exe = self._resolve_ffmpeg_exe()
        probe = self._probe_media(video_path, ffmpeg_exe)

        if not probe.get("has_audio"):
            raise RuntimeError("video_has_no_audio_stream")
        if not ffmpeg_exe:
            payload = await self._call_openai_transcription(api_key, video_path, model)
            payload["duration_seconds"] = float(probe.get("duration_seconds") or 0)
            payload["chunk_count"] = 1
            payload["input_type"] = "video"
            return payload

        duration_seconds = float(probe.get("duration_seconds") or 0)
        with tempfile.TemporaryDirectory(prefix="douyin_audio_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            audio_path = tmp_root / "audio.mp3"
            if not await self._extract_audio_track(video_path, audio_path, ffmpeg_exe):
                logger.warning(
                    "Audio extraction failed for %s, fallback to direct media transcription",
                    video_path,
                )
                payload = await self._call_openai_transcription(api_key, video_path, model)
                payload["duration_seconds"] = duration_seconds
                payload["chunk_count"] = 1
                payload["input_type"] = "video"
                return payload

            chunk_paths = await self._build_audio_chunks(
                audio_path=audio_path,
                duration_seconds=duration_seconds,
                ffmpeg_exe=ffmpeg_exe,
            )
            if not chunk_paths:
                chunk_paths = [audio_path]
            logger.info(
                "Transcribing audio for %s via %s chunk(s), duration=%.2fs",
                video_path.name,
                len(chunk_paths),
                duration_seconds,
            )

            payloads: List[Dict[str, Any]] = []
            for chunk_path in chunk_paths:
                payload = await self._call_openai_transcription(api_key, chunk_path, model)
                payloads.append(payload)

            merged_text = self._merge_transcript_texts(
                [str(payload.get("text", "")).strip() for payload in payloads]
            )
            return {
                "text": merged_text,
                "source": "audio",
                "chunk_count": len(chunk_paths),
                "duration_seconds": duration_seconds,
                "input_type": "audio",
            }

    async def _transcribe_local_audio_from_video(
        self, *, video_path: Path, model: str
    ) -> Dict[str, Any]:
        ffmpeg_exe = self._resolve_ffmpeg_exe()
        probe = self._probe_media(video_path, ffmpeg_exe)

        if not probe.get("has_audio"):
            raise RuntimeError("video_has_no_audio_stream")

        duration_seconds = float(probe.get("duration_seconds") or 0)
        if not ffmpeg_exe:
            payload = await self._call_local_transcription(video_path, model)
            payload["duration_seconds"] = duration_seconds
            payload["chunk_count"] = 1
            payload["input_type"] = "video"
            return payload

        with tempfile.TemporaryDirectory(prefix="douyin_audio_local_") as tmp_dir:
            tmp_root = Path(tmp_dir)
            audio_path = tmp_root / "audio.mp3"
            if not await self._extract_audio_track(video_path, audio_path, ffmpeg_exe):
                logger.warning(
                    "Audio extraction failed for %s, fallback to direct local transcription",
                    video_path,
                )
                payload = await self._call_local_transcription(video_path, model)
                payload["duration_seconds"] = duration_seconds
                payload["chunk_count"] = 1
                payload["input_type"] = "video"
                return payload

            chunk_paths = await self._build_audio_chunks(
                audio_path=audio_path,
                duration_seconds=duration_seconds,
                ffmpeg_exe=ffmpeg_exe,
            )
            if not chunk_paths:
                chunk_paths = [audio_path]
            logger.info(
                "Transcribing local audio for %s via %s chunk(s), duration=%.2fs",
                video_path.name,
                len(chunk_paths),
                duration_seconds,
            )

            payloads: List[Dict[str, Any]] = []
            for chunk_path in chunk_paths:
                payload = await self._call_local_transcription(chunk_path, model)
                payloads.append(payload)

            merged_text = self._merge_transcript_texts(
                [str(payload.get("text", "")).strip() for payload in payloads]
            )
            return {
                "text": merged_text,
                "source": "audio",
                "chunk_count": len(chunk_paths),
                "duration_seconds": duration_seconds,
                "input_type": "audio",
                "model": model,
            }

    async def _extract_audio_track(
        self, video_path: Path, audio_path: Path, ffmpeg_exe: str
    ) -> bool:
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            str(audio_path),
        ]
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return completed.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 0

    async def _build_audio_chunks(
        self, *, audio_path: Path, duration_seconds: float, ffmpeg_exe: str
    ) -> List[Path]:
        chunk_seconds = self._audio_chunk_seconds()
        if duration_seconds <= 0 or duration_seconds <= self._audio_force_chunking_above_seconds():
            return [audio_path]

        chunk_paths: List[Path] = []
        chunk_index = 0
        start_seconds = 0
        while start_seconds < duration_seconds:
            chunk_index += 1
            chunk_path = audio_path.parent / f"chunk_{chunk_index:03d}.mp3"
            cmd = [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(start_seconds),
                "-t",
                str(chunk_seconds),
                "-i",
                str(audio_path),
                "-acodec",
                "copy",
                str(chunk_path),
            ]
            completed = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            if completed.returncode == 0 and chunk_path.exists() and chunk_path.stat().st_size > 0:
                chunk_paths.append(chunk_path)
            start_seconds += chunk_seconds
        return chunk_paths

    @staticmethod
    def _merge_transcript_texts(texts: List[str]) -> str:
        merged: List[str] = []
        for text in texts:
            normalized = str(text or "").strip()
            if not normalized:
                continue
            if merged and normalized == merged[-1]:
                continue
            merged.append(normalized)
        return "\n".join(merged).strip()

    @staticmethod
    def _probe_media(video_path: Path, ffmpeg_exe: str) -> Dict[str, Any]:
        result = {"duration_seconds": 0.0, "has_audio": False}
        if not ffmpeg_exe or not Path(video_path).exists():
            return result

        cmd = [ffmpeg_exe, "-i", str(video_path), "-f", "null", "-"]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        stderr = completed.stderr or ""
        duration_match = re.search(
            r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr
        )
        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2))
            seconds = float(duration_match.group(3))
            result["duration_seconds"] = hours * 3600 + minutes * 60 + seconds
        result["has_audio"] = bool(re.search(r"Stream #.*Audio:", stderr))
        return result

    async def _extract_text_from_images(self, image_paths: List[Path]) -> str:
        engine = self._ensure_ocr_engine()
        if engine is None:
            return ""

        lines: List[str] = []
        for image_path in image_paths:
            if not image_path or not Path(image_path).exists():
                continue

            try:
                ocr_result = await asyncio.to_thread(engine, str(image_path))
            except Exception as exc:
                logger.debug("OCR failed for image %s: %s", image_path, exc)
                continue

            extracted = self._parse_ocr_result(ocr_result)
            if extracted:
                lines.extend(extracted)

        return self._normalize_text_lines(lines)

    async def _extract_text_from_video_ocr(self, video_path: Path) -> str:
        ffmpeg_exe = self._resolve_ffmpeg_exe()
        if not ffmpeg_exe:
            return ""

        interval = self._ocr_frame_interval_seconds()
        max_frames = self._ocr_max_frames()
        with tempfile.TemporaryDirectory(prefix="douyin_ocr_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_pattern = tmp_path / "frame_%03d.jpg"
            cmd = [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{interval},scale=1280:-2",
                "-frames:v",
                str(max_frames),
                str(output_pattern),
            ]
            await asyncio.to_thread(subprocess.run, cmd, check=False)
            frame_paths = sorted(tmp_path.glob("frame_*.jpg"))
            if not frame_paths:
                return ""
            return await self._extract_text_from_images(frame_paths)

    async def _extract_text_from_subtitles(self, video_path: Path) -> str:
        ffmpeg_exe = self._resolve_ffmpeg_exe()
        if not ffmpeg_exe:
            return ""

        with tempfile.TemporaryDirectory(prefix="douyin_sub_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            subtitle_path = tmp_path / "subtitle.srt"
            cmd = [
                ffmpeg_exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video_path),
                "-map",
                "0:s:0",
                "-c:s",
                "srt",
                str(subtitle_path),
            ]
            completed = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            if completed.returncode != 0 or not subtitle_path.exists():
                return ""
            try:
                raw_text = subtitle_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""
            return self._parse_srt_text(raw_text)

    @staticmethod
    def _parse_ocr_result(ocr_result: Any) -> List[str]:
        if not ocr_result:
            return []
        items = ocr_result[0] if isinstance(ocr_result, tuple) else ocr_result
        if not isinstance(items, list):
            return []

        lines: List[str] = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = str(item[1] or "").strip()
            if text:
                lines.append(text)
        return lines

    @staticmethod
    def _parse_srt_text(raw_text: str) -> str:
        lines: List[str] = []
        for raw_line in str(raw_text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.isdigit():
                continue
            if "-->" in line:
                continue
            if re.match(r"^\[.*\]$", line):
                continue
            lines.append(line)
        return TranscriptManager._normalize_text_lines(lines)

    @staticmethod
    def _resolve_ffmpeg_exe() -> str:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
        except Exception:
            return ""

        try:
            return str(get_ffmpeg_exe() or "")
        except Exception:
            return ""

    @staticmethod
    def _guess_media_content_type(video_path: Path) -> str:
        suffix = video_path.suffix.lower()
        if suffix == ".mp4":
            return "video/mp4"
        if suffix == ".m4a":
            return "audio/mp4"
        if suffix == ".wav":
            return "audio/wav"
        if suffix == ".mp3":
            return "audio/mpeg"
        return "application/octet-stream"

    async def _record_job(
        self,
        *,
        aweme_id: str,
        video_path: Path,
        transcript_dir: Path,
        text_path: Path,
        json_path: Path,
        model: str,
        status: str,
        skip_reason: Optional[str],
        error_message: Optional[str],
    ) -> None:
        if not self.database:
            return

        await self.database.upsert_transcript_job(
            {
                "aweme_id": aweme_id,
                "video_path": str(video_path),
                "transcript_dir": str(transcript_dir),
                "text_path": str(text_path),
                "json_path": str(json_path),
                "model": model,
                "status": status,
                "skip_reason": skip_reason,
                "error_message": error_message,
            }
        )
