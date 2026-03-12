import re

def _clean_search_term(text: str) -> str:
    if not text:
        return text
    # Remove Youtube ID format at the end (e.g. -6kzXyhqtKuE)
    text = re.sub(r'-[A-Za-z0-9_\-]{11}$', '', text)
    # Remove any bracketed text [like this]
    text = re.sub(r'\[.*?\]', '', text)
    # Remove standalone Out Now!
    text = re.sub(r'(?i)\bout now!?\b', '', text)
    
    text = re.sub(r'\b\d{3}\s*[Kk]bps?\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(?Official(?: Music)? Video\)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(?Lyric video\)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(?video clip\)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[?HQ(?: - Exclusive)?\]?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bHD\s*1080p\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[?OUT NOW!?\]?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[\(\[]\d{4}[\]\)]', '', text)
    text = re.sub(r'^\d{2}\s*-?\s*', '', text)
    text = re.sub(r'^[A-Za-z]{1,2}-[A-Za-z]{1,2}-\s*', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+-\s*$', '', text)
    return text.strip()

print(_clean_search_term('Evaporate (Original Mix) [303 Lovers] Out Now!-6kzXyhqtKuE'))
print(_clean_search_term('[303 Lovers] Out Now!-6kzXyhqtKuE'))
