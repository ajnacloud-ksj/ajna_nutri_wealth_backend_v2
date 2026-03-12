"""
Backward-compatible IbexDB client alias.

All code should use OptimizedIbexClient from lib.ibex_client_optimized.
This module re-exports it as IbexClient for scripts and legacy imports.
"""

from lib.ibex_client_optimized import OptimizedIbexClient as IbexClient

__all__ = ['IbexClient']
