import re
import pandas as pd
from app.services.loaders.base import BaseLoader, LoadResult
from fastapi import HTTPException

# sheet names that would clash with SQL syntax if used as table names
RESERVED = {
    "all", "and", "as", "asc", "by", "case", "cast", "column", "create", "desc",
    "distinct", "else", "end", "except", "false", "from", "group", "having", "in",
    "intersect", "join", "limit", "not", "null", "offset", "on", "or", "order",
    "select", "table", "then", "to", "true", "union", "user", "using", "when",
    "where", "window", "with",
}

def _table_name(sheet: str, taken: set[str]) -> str:
    name = re.sub(r"\W+", "_", sheet.strip().lower()).strip("_") or "sheet"
    if name[0].isdigit():
        name = "sheet_" + name
    if name in RESERVED:
        name += "_sheet"
    base, i = name, 2
    while name in taken:
        name = f"{base}_{i}"
        i += 1
    taken.add(name)
    return name

class ExcelLoader(BaseLoader):
    def load(self, file_path: str) -> LoadResult:
        return self.load_all(file_path)[0]

    def load_all(self, file_path: str) -> list[LoadResult]:
        xl = pd.ExcelFile(file_path, engine="openpyxl")

        results, skipped = [], []
        # "data" stays free for the alias to the first sheet
        taken = {"data"}
        for sheet in xl.sheet_names:
            df = self._clean(pd.read_excel(xl, sheet_name=sheet, engine="openpyxl"))
            if df.empty:
                skipped.append(sheet)
                continue

            warnings = []
            if len(df) > self.MAX_ROWS:
                df = df.head(self.MAX_ROWS)
                warnings.append(f"'{sheet}' truncated to {self.MAX_ROWS} rows")

            results.append(LoadResult(
                df=df,
                detected_types=self._infer_types(df),
                warnings=warnings,
                row_count=len(df),
                col_count=len(df.columns),
                name=_table_name(sheet, taken),
                sheet=sheet,
            ))

        if not results:
            raise HTTPException(400, "Every sheet in this workbook is empty after cleanup")
        if skipped:
            results[0].warnings.append(f"Skipped empty sheets: {skipped}")
        return results

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
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
        return df
