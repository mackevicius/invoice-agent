from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol

from fastembed import TextEmbedding


class TextEmbeddings(Protocol):
    @property
    def model_name(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbeddings:
    def __init__(self) -> None:
        self._model: TextEmbedding | None = None
        self._lock = Lock()

    @property
    def model_name(self) -> str:
        return "sentence-transformers/all-MiniLM-L6-v2"

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if self._model is None:
                self._model = TextEmbedding(model_name=self.model_name, threads=1)
            return [
                [float(value) for value in vector]
                for vector in self._model.embed(texts)
            ]


@dataclass
class ScriptedEmbeddings:
    vectors: dict[str, list[float]] = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        return "scripted"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors.get(text, [1.0] + [0.0] * 383) for text in texts]
