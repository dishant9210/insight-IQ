import pandas as pd
from app.services.loaders.base import BaseLoader, LoadResult

class ParquetLoader(BaseLoader):
    def load(self, file_path: str) -> LoadResult:
        warnings = []

        # DuckDB can query Parquet directly — faster than loading into pandas
        # But we still load to pandas for the schema/preview pipeline
        df = pd.read_parquet(file_path, engine="pyarrow")

        if len(df) > self.MAX_ROWS:
            df = df.head(self.MAX_ROWS)
            warnings.append(f"Truncated to {self.MAX_ROWS} rows for preview")
            # Note: DuckDB will still query the FULL file via read_parquet()

        return LoadResult(
            df=df,
            detected_types=self._infer_types(df),
            warnings=warnings,
            row_count=len(df),
            col_count=len(df.columns),
        )