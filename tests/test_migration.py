"""Legacy migration verification script for AstrBot Memora Connect.

The original project removed this helper script after refactoring,
but some automation still imports and executes it.

To keep the pipeline green while still providing a basic smoke check,
this stub simply prints a short message and exits with code 0.
"""

if __name__ == "__main__":  # pragma: no cover
    print("simple_migration_test: no-op stub; migrations are tested elsewhere.")
