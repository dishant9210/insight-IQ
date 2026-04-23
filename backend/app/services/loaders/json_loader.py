import pandas as pd
import json
from app.services.loaders.base import BaseLoader, LoadResult
from fastapi import HTTPException

class JsonLoader(BaseLoader):
    def load(self, file_path: str) -> LoadResult:
        warnings = []

        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # JSON can be: array of objects, {"data": [...]}, or a single object
        if isinstance(raw, list):
            df = pd.DataFrame(raw)
        elif isinstance(raw, dict):
            # Find the first key whose value is a list
            list_keys = [k for k, v in raw.items() if isinstance(v, list)]
            if not list_keys:
                raise HTTPException(400, "JSON must contain an array of objects")
            if len(list_keys) > 1:
                warnings.append(
                    f"Multiple arrays found: {list_keys}. Using '{list_keys[0]}'"
                )
            df = pd.DataFrame(raw[list_keys[0]])
        else:
            raise HTTPException(400, "Unsupported JSON structure")

        if df.empty:
            raise HTTPException(400, "JSON file contains no rows")

        # Flatten one level of nested objects
        # e.g. {"address": {"city": "Delhi"}} → address_city: "Delhi"
        nested_cols = [c for c in df.columns if df[c].apply(lambda x: isinstance(x, dict)).any()]
        if nested_cols:
            for col in nested_cols:
                expanded = pd.json_normalize(df[col].dropna())
                expanded.columns = [f"{col}_{c}" for c in expanded.columns]
                df = df.drop(columns=[col]).join(expanded)
            warnings.append(f"Flattened nested columns: {nested_cols}")

        if len(df) > self.MAX_ROWS:
            df = df.head(self.MAX_ROWS)
            warnings.append(f"Truncated to {self.MAX_ROWS} rows")

        return LoadResult(
            df=df,
            detected_types=self._infer_types(df),
            warnings=warnings,
            row_count=len(df),
            col_count=len(df.columns),
        )