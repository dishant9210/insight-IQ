import pandas as pd
from app.services.loaders.base import BaseLoader, LoadResult

class CsvLoader(BaseLoader):
    def load(self, file_path: str) -> LoadResult:
        warnings = []

        # Sniff encoding — handles UTF-8, latin-1, Windows-1252
        try:
            df = pd.read_csv(file_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="latin-1")
            warnings.append("Non-UTF-8 encoding detected — used latin-1 fallback")

        if len(df) > self.MAX_ROWS:
            df = df.head(self.MAX_ROWS)
            warnings.append(f"File truncated to {self.MAX_ROWS} rows")

        # Clean column names: "Sales Amount " → "sales_amount"
        df.columns = (
            df.columns.str.strip()
                      .str.lower()
                      .str.replace(r"[^\w]", "_", regex=True)
                      .str.replace(r"_+", "_", regex=True)
        )

        # Attempt datetime parsing on columns that look like dates
        for col in df.columns:
            if df[col].dtype == object:
                sample = df[col].dropna().head(10).astype(str)
                if sample.str.match(r"\d{4}[-/]\d{2}[-/]\d{2}").mean() > 0.7:
                    try:
                        df[col] = pd.to_datetime(df[col])
                        warnings.append(f"Column '{col}' parsed as datetime")
                    except Exception:
                        pass

        return LoadResult(
            df=df,
            detected_types=self._infer_types(df),
            warnings=warnings,
            row_count=len(df),
            col_count=len(df.columns),
        )