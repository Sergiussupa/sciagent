from typing import List


SYSTEM = """Answer only from the retrieved scientific records. Cite claims inline with [arXiv:ID]. If the records are insufficient, say so."""


def answer_question(llm, question: str, rows: List, max_chars_each: int = 3000) -> str:
    chunks = []
    for row in rows:
        chunks.append(
            "[arXiv:%s]\nTITLE: %s\nSUMMARY: %s\nABSTRACT: %s\nEVIDENCE: %s" % (
                row["arxiv_id"], row["title"], row["summary"] or "", (row["abstract"] or "")[:max_chars_each], row["evidence_claims"] or ""
            )
        )
    prompt = "QUESTION:\n%s\n\nRETRIEVED RECORDS:\n\n%s" % (question, "\n\n".join(chunks))
    return llm.generate(prompt, system=SYSTEM, json_mode=False)
