"""Small public-domain language sample; no production cache or site writes."""
import json
import os
from fetch import LearnerLanguage, LEARNER_GEMINI_API_KEY_ENV

language = LearnerLanguage(os.environ[LEARNER_GEMINI_API_KEY_ENV])
language.cache = {"pronunciations": {}, "glossaries": {}}
language.save = lambda: None
sentences = [
    "Glory be to the Father, and to the Son, and to the Holy Spirit.",
    "Lord, open my lips, and my mouth will proclaim your praise.",
    "Have mercy on us and forgive us our sins.",
    "Let us give thanks to the Lord our God.",
]
print(json.dumps({"model": language.model, "ipa": language.pronunciations(sentences),
                  "glossary": language.glossary("Morning Prayer", " ".join(sentences))},
                 ensure_ascii=False, indent=2))
