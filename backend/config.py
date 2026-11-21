"""Portable database settings, independent of the process working directory."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / 'data' / 'processed')
    runtime_dir: Path = field(default_factory=lambda: PROJECT_ROOT / 'data' / 'runtime')
    memory_limit: str = '256MB'
    threads: int = 2
    max_temp_directory_size: str = '1GB'
    max_query_rows: int = 1000
    max_concurrent_queries: int = 2
    cors_origins: tuple[str, ...] = (
        'http://localhost:5173', 'http://127.0.0.1:5173',
        'http://localhost:3000', 'http://127.0.0.1:3000',
    )

    def __post_init__(self):
        object.__setattr__(self, 'data_dir', _path(self.data_dir))
        object.__setattr__(self, 'runtime_dir', _path(self.runtime_dir))
        for name in ('memory_limit', 'max_temp_directory_size'):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]*(MB|GB)', value):
                raise ValueError(f'{name} must be a positive integer followed by MB or GB')
        if type(self.threads) is not int or not 1 <= self.threads <= 32:
            raise ValueError('threads must be between 1 and 32')
        if type(self.max_query_rows) is not int or not 1 <= self.max_query_rows <= 10000:
            raise ValueError('max_query_rows must be between 1 and 10000')
        if self.runtime_dir == self.data_dir or self.data_dir in self.runtime_dir.parents:
            raise ValueError('Runtime files must be outside the immutable export directory')
        if type(self.max_concurrent_queries) is not int or not 1 <= self.max_concurrent_queries <= 8:
            raise ValueError('max_concurrent_queries must be between 1 and 8')
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ('http', 'https') or
                    parsed.hostname not in ('localhost', '127.0.0.1', '::1') or
                    parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError('CORS origins must be explicit local HTTP(S) origins')
            parsed.port  # Validate the port, including invalid numeric/range values.

    @classmethod
    def from_env(cls):
        """Relative environment paths are anchored to PROJECT_ROOT, never cwd."""
        return cls(
            data_dir=os.getenv('CROWDROUTE_DATA_DIR', 'data/processed'),
            runtime_dir=os.getenv('CROWDROUTE_RUNTIME_DIR', 'data/runtime'),
            memory_limit=os.getenv('CROWDROUTE_MEMORY_LIMIT', '256MB'),
            threads=int(os.getenv('CROWDROUTE_THREADS', '2')),
            max_temp_directory_size=os.getenv('CROWDROUTE_MAX_TEMP_SIZE', '1GB'),
            max_query_rows=int(os.getenv('CROWDROUTE_MAX_QUERY_ROWS', '1000')),
            max_concurrent_queries=int(os.getenv('CROWDROUTE_MAX_CONCURRENT_QUERIES', '2')),
            cors_origins=tuple(x.strip() for x in os.environ['CROWDROUTE_CORS_ORIGINS'].split(',') if x.strip())
                if 'CROWDROUTE_CORS_ORIGINS' in os.environ else cls.__dataclass_fields__['cors_origins'].default,
        )
