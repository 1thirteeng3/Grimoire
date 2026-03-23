import logging
import threading
from pathlib import Path

import frontmatter
import tiktoken

from app.config import settings

logger = logging.getLogger("grimoire.jit")

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # pragma: no cover - fallback for minimal environments
    class FileSystemEventHandler:  # type: ignore[no-redef]
        pass

    class Observer:  # type: ignore[no-redef]
        def schedule(self, *args, **kwargs):
            return None

        def start(self):
            return None

        def stop(self):
            return None

        def join(self):
            return None


class PromptBloatError(Exception):
    def __init__(self, current_tokens: int, limit: int, domain: str):
        self.current_tokens = current_tokens
        self.limit = limit
        self.domain = domain
        super().__init__(
            f"Saturação Epistémica: {current_tokens} tokens "
            f"({limit} permitidos) — domínio: {domain}"
        )


class DogmasCache:
    def __init__(self):
        self._cache: dict[str, list[dict]] = {}
        self._lock = threading.RLock()

    def update(self, filepath: Path) -> None:
        try:
            post = frontmatter.load(str(filepath))
            domain = post.metadata.get("dominio", "generic")
            active = post.metadata.get("ativa", True)
            if not active:
                self.remove(filepath)
                return
            entry = {
                "filepath": str(filepath),
                "domain": domain,
                "body": post.content,
                "tags": post.metadata.get("tags", []),
            }
            with self._lock:
                existing = [e for e in self._cache.get(domain, []) if e["filepath"] != str(filepath)]
                existing.append(entry)
                self._cache[domain] = existing
        except Exception as exc:
            logger.error("Erro ao carregar dogma %s: %s", filepath, exc)

    def remove(self, filepath: Path) -> None:
        with self._lock:
            for domain in list(self._cache.keys()):
                self._cache[domain] = [
                    e for e in self._cache[domain] if e["filepath"] != str(filepath)
                ]

    def get_for_domains(self, domains: list[str]) -> list[dict]:
        with self._lock:
            result: list[dict] = []
            for domain in domains:
                result.extend(self._cache.get(domain, []))
            return result


_cache = DogmasCache()


class DogmasWatcher:
    def __init__(self, dogmas_path: Path):
        self.path = dogmas_path
        self.path.mkdir(parents=True, exist_ok=True)
        self.observer = Observer()

    def start(self) -> None:
        for md_file in self.path.glob("*.md"):
            _cache.update(md_file)
        handler = _DogmasEventHandler()
        self.observer.schedule(handler, str(self.path), recursive=False)
        self.observer.start()
        logger.info("Dogmas Watcher iniciado: %s", self.path)

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join()


class _DogmasEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            _cache.update(Path(event.src_path))
            logger.info("Dogma atualizado: %s", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            _cache.remove(Path(event.src_path))
            logger.info(
                "Dogma removido do contexto (remoção de regra — não un-learning): %s",
                event.src_path,
            )

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            _cache.update(Path(event.src_path))


def compile_constitution(domains: list[str], model_name: str = "cl100k_base") -> str:
    dogmas = _cache.get_for_domains(domains)
    if not dogmas:
        return ""

    blocks = [f'<lei source="{d["filepath"]}">{d["body"]}</lei>' for d in dogmas]
    constitution = "<leis_ativas>\n" + "\n".join(blocks) + "\n</leis_ativas>"
    enc = tiktoken.get_encoding(model_name)
    token_count = len(enc.encode(constitution))
    if token_count > settings.max_constitution_tokens:
        domain_str = ", ".join(domains)
        raise PromptBloatError(token_count, settings.max_constitution_tokens, domain_str)
    return constitution
