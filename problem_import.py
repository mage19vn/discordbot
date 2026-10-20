"""Validate problem JSON before an atomic import into SQLite."""

import json
import re

MAX_JSON_BYTES = 256 * 1024
MAX_PROBLEMS = 20
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_FIELDS = {"question", "statement", "solution", "gen_test", "checker", "category",
           "fixed_tests", "test_count", "time_limit", "memory_limit", "published"}
_LEGACY_CACHE = {"page_url", "page_hash"}
_STATEMENT_FIELDS = {"title", "description", "input", "output", "constraints",
                     "examples", "notes"}


def _text_part(value, label, max_bytes=16 * 1024, required=False, strip=True):
    if (not isinstance(value, str) or len(value.encode("utf-8")) > max_bytes or
            (required and not value.strip())):
        raise ValueError(f"{label} phải là chuỗi {'có nội dung, ' if required else ''}tối đa {max_bytes // 1024} KiB.")
    return value.strip() if strip else value


def _statement_question(name, statement):
    if not isinstance(statement, dict):
        raise ValueError(f"Bài {name}: statement phải là object JSON.")
    unknown = set(statement) - _STATEMENT_FIELDS
    if unknown:
        raise ValueError(f"Bài {name}: mục statement không hỗ trợ: {', '.join(sorted(unknown))}.")
    title = _text_part(statement.get("title", ""), "title", 200, required=True)
    description = _text_part(statement.get("description", ""), "description", required=True)
    inp = _text_part(statement.get("input", ""), "input", required=True)
    out = _text_part(statement.get("output", ""), "output", required=True)
    constraints = _text_part(statement.get("constraints", ""), "constraints")
    notes = _text_part(statement.get("notes", ""), "notes")
    examples = statement.get("examples", [])
    if not isinstance(examples, list) or len(examples) > 5:
        raise ValueError(f"Bài {name}: examples phải là mảng tối đa 5 ví dụ.")
    sections = [f"# **{title}**", description, f"**Input**\n{inp}", f"**Output**\n{out}"]
    if constraints:
        sections.append(f"**Điều kiện**\n{constraints}")
    for index, example in enumerate(examples, 1):
        if not isinstance(example, dict) or set(example) - {"input", "output", "explanation"}:
            raise ValueError(f"Bài {name}: ví dụ {index} có trường không hợp lệ.")
        if "input" not in example or "output" not in example:
            raise ValueError(f"Bài {name}: ví dụ {index} cần input và output.")
        ex_input = _text_part(example["input"], "example input", 4096, strip=False)
        ex_output = _text_part(example["output"], "example output", 4096, strip=False)
        explanation = _text_part(example.get("explanation", ""), "explanation", 4096)
        if "```" in ex_input or "```" in ex_output:
            raise ValueError(f"Bài {name}: input/output ví dụ không được chứa dấu ```.")
        shown_input, shown_output = ex_input.rstrip("\n"), ex_output.rstrip("\n")
        block = (f"**Ví dụ {index}**\n\n*Input:*\n```\n{shown_input}\n```\n\n"
                 f"*Output:*\n```\n{shown_output}\n```")
        if explanation:
            block += f"\n\n*Giải thích:*\n{explanation}"
        sections.append(block)
    if notes:
        sections.append(f"**Ghi chú**\n{notes}")
    question = "\n\n".join(sections)
    if len(question.encode("utf-8")) > 64 * 1024:
        raise ValueError(f"Bài {name}: đề sau khi ghép vượt quá 64 KiB.")
    return question


def parse_problem_json(data: bytes, *, require_full=False):
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("File JSON vượt quá 256 KiB.")
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("File phải là JSON UTF-8 hợp lệ.") from exc

    if isinstance(payload, dict) and "de" in payload:
        if not isinstance(payload["de"], dict):
            raise ValueError("Trường de phải là object chứa tên bài và nội dung.")
        entries = [{**body, "name": name} if isinstance(body, dict) else body
                   for name, body in payload["de"].items()]
    elif isinstance(payload, dict) and "problems" in payload:
        entries = payload["problems"]
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = [payload]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PROBLEMS:
        raise ValueError("File phải chứa 1–20 bài (một bài, mảng, problems hoặc de).")

    parsed = []
    seen = set()
    for index, item in enumerate(entries, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Bài thứ {index} phải là object JSON.")
        name = item.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError(f"Bài thứ {index}: name chỉ gồm chữ Latin, số, _ hoặc -, tối đa 64 ký tự.")
        if name in seen:
            raise ValueError(f"Tên bài {name} xuất hiện nhiều lần trong file.")
        seen.add(name)
        if require_full:
            required = {"category", "solution", "gen_test", "checker", "fixed_tests",
                        "test_count", "time_limit", "memory_limit", "published"}
            missing = required - set(item)
            if "statement" not in item and "question" not in item:
                missing.add("statement hoặc question")
            if missing:
                raise ValueError(f"Bài {name}: file cập nhật thiếu {', '.join(sorted(missing))}.")
        unknown = set(item) - _FIELDS - _LEGACY_CACHE - {"name"}
        if unknown:
            raise ValueError(f"Bài {name}: trường không hỗ trợ: {', '.join(sorted(unknown))}.")
        if "statement" in item and "question" in item:
            raise ValueError(f"Bài {name}: dùng statement hoặc question, không dùng cả hai.")
        body = {}
        for field in ("question", "solution", "gen_test", "checker"):
            value = (_statement_question(name, item["statement"])
                     if field == "question" and "statement" in item else item.get(field, ""))
            if not isinstance(value, str) or len(value.encode("utf-8")) > 64 * 1024:
                raise ValueError(f"Bài {name}: {field} phải là chuỗi tối đa 64 KiB.")
            body[field] = value
        category = item.get("category", "Chưa phân loại")
        if not isinstance(category, str) or not category.strip() or len(category) > 100:
            raise ValueError(f"Bài {name}: category phải là chuỗi 1–100 ký tự.")
        body["category"] = category
        tests = item.get("fixed_tests", [])
        if (not isinstance(tests, list) or len(tests) > 10 or
                any(not isinstance(value, str) or not value.strip() or
                    len(value.encode("utf-8")) > 4096 for value in tests)):
            raise ValueError(f"Bài {name}: fixed_tests cần tối đa 10 input, mỗi input 1–4096 byte.")
        body["fixed_tests"] = tests
        for field, low, high, default in (("test_count", 1, 10, 10),
                                           ("time_limit", 1, 2, 2),
                                           ("memory_limit", 64, 128, 128)):
            value = item.get(field, default)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Bài {name}: {field} phải là số nguyên từ {low} đến {high}.")
            body[field] = value
        if len(tests) > body["test_count"]:
            raise ValueError(f"Bài {name}: số test cố định vượt test_count.")
        published = item.get("published", False)
        if type(published) is not bool:
            raise ValueError(f"Bài {name}: published phải là true hoặc false.")
        if published and (not body["question"].strip() or
                          not body["solution"].strip() or
                          (len(tests) < body["test_count"] and not body["gen_test"].strip())):
            raise ValueError(f"Bài {name}: cần đề, solution và đủ test/generator trước khi công bố.")
        body["published"] = published
        parsed.append((name, body))
    return parsed
