from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd

@dataclass
class LoadResult:
    df: pd.DataFrame
    detected_types: dict[str, str]    # col → "numeric" | "datetime" | "categorical" | "text"
    warnings: list[str]               # e.g. "3 rows had unparseable dates"
    row_count: int
    col_count: int

class BaseLoader(ABC):
    MAX_ROWS = 500_000   # safety limit — raise HTTPException above this

    @abstractmethod
    def load(self, file_path: str) -> LoadResult:
        """Parse the file and return a normalised LoadResult."""
        ...

    def _infer_types(self, df: pd.DataFrame) -> dict[str, str]:
        """Classify each column for the schema prompt and chart hints."""
        types = {}
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                types[col] = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                types[col] = "datetime"
            elif df[col].nunique() / len(df) < 0.05:
                types[col] = "categorical"   # <5% unique → low cardinality
            else:
                types[col] = "text"
        return types