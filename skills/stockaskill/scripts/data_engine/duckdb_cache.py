"""DuckDB cache module re-export for backward compatibility."""

from cache import CacheManager, DuckDBCacheManager, get_cache

__all__ = ["CacheManager", "DuckDBCacheManager", "get_cache"]
