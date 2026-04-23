import pandas as pd
from app.services.loaders.base import BaseLoader, LoadResult
from fastapi import HTTPException

class ExcelLoader(BaseLoader):
    def load(self, file_path: str) -> LoadResult:
        warnings = []

        # Read sheet names first — don't load all data yet
        xl = pd.ExcelFile(file_path, engine="openpyxl")
        sheet_names = xl.sheet_names

        if len(sheet_names) > 1:
            warnings.append(
                f"Multiple sheets: {sheet_names}. Using '{sheet_names[0]}'"
            )

        df = pd.read_excel(
            xl,
            sheet_name=sheet_names[0],
            engine="openpyxl",
        )

        # Drop completely empty rows and columns (common in Excel files)
        df = df.dropna(how="all").dropna(axis=1, how="all")

        # Excel often has unnamed columns: "Unnamed: 3" → drop them
        df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]

        # Normalise column names (same as CSV loader)
        df.columns = (
            df.columns.astype(str)
                      .str.strip()
                      .str.lower()
                      .str.replace(r"[^\w]", "_", regex=True)
        )

        if len(df) > self.MAX_ROWS:
            df = df.head(self.MAX_ROWS)
            warnings.append(f"Truncated to {self.MAX_ROWS} rows")

        if df.empty:
            raise HTTPException(400, "Excel sheet is empty after cleanup")

        return LoadResult(
            df=df,
            detected_types=self._infer_types(df),
            warnings=warnings,
            row_count=len(df),
            col_count=len(df.columns),
        )