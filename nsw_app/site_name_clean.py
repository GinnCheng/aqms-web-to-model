import re
import pandas as pd

def clean_name(x):
    if pd.isna(x):
        return ""

    x = str(x).upper()

    # remove extra spaces
    x = x.strip()

    # remove brackets content
    x = re.sub(r"\(.*?\)", "", x)

    # remove special chars
    x = re.sub(r"[^A-Z0-9 ]", "", x)

    # collapse spaces
    x = re.sub(r"\s+", " ", x)

    return x