import re


class DataCleaner:
    UNWANTED_TERMS = [
        r'INJ-T1-', r'INJ-T2-', r'INJ-T3-', r'TCN-',
        r'FEEDER_', r'FDR_', r'FEEDER', r'FDR',
        r'33KVA', r'11KVA', r'33-', r'11-', r'33KV', r'11KV',
        r'33 KV', r'11 KV', r'_', r'\|',  # Added pipe character
    ]

    _pattern = re.compile(
        r'(' + '|'.join(UNWANTED_TERMS) + r')',
        re.IGNORECASE,
    )

    def clean_feeder_name(self, feeder_name: str) -> str:
        """
        Remove technical prefixes/suffixes and normalize whitespace.
        Returns a human-readable formatted address string.
        """
        # Remove pipes and underscores first
        text = feeder_name.replace('|', ' ').replace('_', ' ')
        
        # Apply pattern-based cleaning
        text = self._pattern.sub(' ', text)
        
        # Normalize whitespace
        text = re.sub(r'[-_\s]+', ' ', text)
        text = text.strip(' -')
        
        return text.strip()
