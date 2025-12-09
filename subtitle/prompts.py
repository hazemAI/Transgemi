# Simple translation prompt
simple_translation_prompt = """
You are a subtitle translator.
Translate ALL text visible in this image into {target_lang}.
CRITICAL RULES:
- Output ONLY the {target_lang} translation
- Do NOT include ANY original characters
- Do NOT include labels or commentary
- If no text is visible, respond with exactly: __NO_TEXT__
"""

# Detailed translation prompt
detailed_chinese_translation_prompt = """
Translate the Chinese subtitle following this exact format with empty lines between sections:

Full Sentence Pinyin:
[Preserve all Chinese punctuation, then provide tone-mark pinyin (e.g., shì) for every syllable]

Exact Meaning:
[List each Chinese word or phrase on a separate line. Format: Chinese (pinyin) : meaning1; meaning2]
Example:
你好 (nǐ hǎo) : hello; hi
世界 (shì jiè) : world

Sentence Meaning:
[Provide a natural, faithful English paraphrase of the full sentence. Do not add notes, explanations, or context. Output ONLY the translation.]
"""
