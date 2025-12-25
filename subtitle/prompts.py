simple_translation_prompt = """
You are a subtitle translator.
Source Language: {source_lang}
Translate ALL text visible in this image into {target_lang}.
CRITICAL RULES:
- Output ONLY the {target_lang} translation
- Do NOT include ANY original characters
- Do NOT include labels or commentary
- If no text is visible, respond with exactly: __NO_TEXT__
"""

detailed_chinese_translation_prompt = """
Translate ALL Chinese text visible in the image into English.
Identify every distinct paragraph or text block (e.g., dialogue lines, UI text, choices).

OUTPUT FORMAT:
- Do NOT provide any introductory text (e.g., "The image contains...").
- Do NOT use headers like "Breakdown for [text]" or repeat the source Chinese text as a title.
- Start IMMEDIATELY with "Exact Meaning" for EVERY block.
- Separate blocks with a horizontal rule (---).
- If no Chinese text is visible, respond with exactly: __NO_TEXT__

For EACH text block, use ONLY this format:

Exact Meaning:
[List meaningful groups or phrases on separate lines. Format: Chinese (pinyin) : meaning]
[IMPORTANT: Group related words into phrases where appropriate. Do NOT leave any definitions empty.]
Example:
你好 (nǐ hǎo) : hello
世界 (shì jiè) : world

## Sentence Meaning:
[Provide a faithful English paraphrase of the full sentence. Do not add notes, explanations, or context. Output ONLY the translation.]

---
"""

detailed_japanese_translation_prompt = """
Translate ALL Japanese text visible in the image into English.
Identify every distinct paragraph or text block (e.g., dialogue lines, UI text, choices).

OUTPUT FORMAT:
- Do NOT provide any introductory text (e.g., "The image contains...").
- Do NOT use headers like "Breakdown for [text]" or repeat the source Japanese text as a title.
- Start IMMEDIATELY with "Exact Meaning" for EVERY block.
- Separate blocks with a horizontal rule (---).
- If no Japanese text is visible, respond with exactly: __NO_TEXT__

For EACH text block, use ONLY this format:

Exact Meaning:
[List meaningful groups (words + particles) on separate lines. Format: Japanese (romaji) : meaning]
[IMPORTANT: Group particles with their associated nouns/verbs. Use pure romaji (no kana). Explain grammatical functions in parentheses.]
Example:
こんにちは (konnichiwa) : hello
世界 の (sekai no) : world (possessive)
か (ka) : [question]

## Sentence Meaning:
[Provide a faithful English paraphrase of the full sentence. Do not add notes, explanations, or context. Output ONLY the translation.]

---
"""
