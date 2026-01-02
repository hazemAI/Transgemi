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
- Start IMMEDIATELY with "Exact Meaning" for EVERY block without any introductory or headers.
- Do NOT try providing different possible meanings for the Sentence Meaning, just one translation.
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
Translate ALL Japanese text in the image into English.
Combine the entire visible japanese text into a SINGLE translation.

General above-all rules for this task:
- Start IMMEDIATELY with "Exact Meaning" without any introductory text then follow with a single "Sentence Meaning" section.
- If there is no Japanese text in the image, respond with exactly "__NO_TEXT__" without any other text because it will be handled in my end accordingly.
- You can't show any reasoning trails or alternative suggested translations in the Sentence Meaning section.
- No variations in output format is allowed, keep your output consistent and strict, don't try to variate whatever the reason is.
- For Sentence Meaning: If you feel that based on the image there will be multiple independent sentences or any type of inconsistency, no problem just provide your closest combined one translation without any unrelated-to-the-translation text.

Your main always output:

Exact Meaning:
[Group by COMPLETE WORDS, not individual characters. Each line = one word or grammatical unit.]
[Format: 日本語 (romaji) : meaning]
[CRITICAL: Every single entry MUST have a meaning. Never leave any definition blank.]
[Verb forms MUST stay together: 出てきた = one entry, NOT 出/て/き/た as four entries]
[Compound words stay together: 誰か = one entry, NOT 誰/か as two entries]
[Particles and grammar MUST have meanings: の = possessive, を = object marker, は = topic marker, etc.]

CORRECT example for "アルタゴの将来を愛している":
アルタゴ (Arutago) : Arutago (name)
の (no) : possessive
将来 (shōrai) : future
を (o) : object marker
愛している (aishiteiru) : love

CORRECT example for "誰か出てきたぞ":
誰か (dareka) : someone
出てきた (detekita) : came out
ぞ (zo) : emphasis

## Sentence Meaning:
[ONE definitive translation to English. No alternatives. No commentary. Just the translation.]

"""
